"""Watch mode: keep an eye on your repositories and speak up when a default-branch build breaks."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from . import github
from .github import GitHubError

ACTIVE_DAYS = 30  # with an owner, watch repositories pushed in the last month
HISTORY_RUNS = 10  # recent results kept per workflow for the dashboard


def workflow_history(runs: list[dict[str, Any]], limit: int = HISTORY_RUNS) -> dict[object, list[str]]:
    """Recent completed results of each workflow, oldest first: "passing", "failing" or "other" (cancelled, skipped)."""
    history: dict[object, list[str]] = {}
    for run in runs:  # newest first
        if run.get("status") != "completed":
            continue
        results = history.setdefault(run.get("workflow_id"), [])
        if len(results) < limit:
            conclusion = run.get("conclusion")
            results.append("failing" if conclusion in github.FAILED else "passing" if conclusion == "success" else "other")
    return {workflow: results[::-1] for workflow, results in history.items()}


@dataclass(frozen=True)
class Alert:
    repo: str
    workflow: str
    kind: str  # "failing" (newly failing, or failing when watching starts) or "recovered"
    run_id: object
    url: object
    commit: str

    def message(self) -> str:
        if self.kind == "recovered":
            return f"{self.repo}: {self.workflow} is passing again."
        return f"{self.repo}: {self.workflow} is failing on commit {self.commit}. {self.url}"


class Watcher:
    """Tracks the latest result of every workflow on each repository's default branch."""

    def __init__(self, repos: list[str], owners: list[str], api: Any = github) -> None:
        self.repos = [github.validate_repo(r) for r in repos]
        self.owners = owners
        self.api = api
        self.state: dict[tuple[str, object], str] = {}
        self.default_branches: dict[str, str] = {}
        self.errors: list[str] = []
        # The latest completed run of each workflow, for the web dashboard.
        self.runs: dict[tuple[str, object], dict[str, Any]] = {}

    def targets(self) -> list[str]:
        found = list(self.repos)
        cutoff = datetime.now(timezone.utc) - timedelta(days=ACTIVE_DAYS)
        for owner in self.owners:
            try:
                listed = self.api.list_user_repos(owner, 100)
            except GitHubError as err:
                self.errors.append(f"Couldn't list repositories of {owner}: {err}")
                continue
            for info in listed:
                pushed = str(info.get("pushed_at") or "")
                if info.get("repo") and pushed and datetime.fromisoformat(pushed.replace("Z", "+00:00")) >= cutoff:
                    found.append(str(info["repo"]))
        return sorted(set(found))

    def _branch(self, repo: str) -> str:
        if repo not in self.default_branches:
            self.default_branches[repo] = str(self.api.repo_info(repo).get("default_branch") or "main")
        return self.default_branches[repo]

    def poll(self) -> list[Alert]:
        """Check every repository once. The first poll reports what is already failing; later polls
        report only changes: newly failing or recovered workflows."""
        alerts: list[Alert] = []
        self.errors = []
        for repo in self.targets():
            try:
                runs = self.api.api_get(f"/repos/{repo}/actions/runs", {"branch": self._branch(repo), "per_page": 50})
            except GitHubError as err:
                self.errors.append(f"{repo}: {err}")
                continue
            history = workflow_history(runs.get("workflow_runs", []))
            for run in self.api.latest_per_workflow(runs.get("workflow_runs", [])):
                key = (repo, run.get("workflow_id"))
                failing = run.get("conclusion") in github.FAILED
                status = "failing" if failing else "passing"
                previous = self.state.get(key)
                self.state[key] = status
                self.runs[key] = {
                    "workflow": str(run.get("name")), "status": status, "conclusion": run.get("conclusion"),
                    "run_id": run.get("id"), "url": run.get("html_url"), "commit": str(run.get("head_sha"))[:7],
                    "updated_at": run.get("updated_at") or run.get("created_at"),
                    "history": history.get(run.get("workflow_id"), []),
                }
                if status == previous or (previous is None and not failing):
                    continue
                alerts.append(Alert(
                    repo=repo,
                    workflow=str(run.get("name")),
                    kind="failing" if failing else "recovered",
                    run_id=run.get("id"),
                    url=run.get("html_url"),
                    commit=str(run.get("head_sha"))[:7],
                ))
        return alerts


def fix_prompt(alert: Alert) -> str:
    return (
        f"The {alert.workflow} workflow is failing on the default branch of {alert.repo} (run {alert.run_id}). "
        "Use get_ci_failure to diagnose it. If it is already fixed, say so and stop. If it is intermittent, make "
        "the failure diagnosable and address the most likely cause. Otherwise fix the root cause. Then open a draft "
        "pull request and report what you did."
    )


def watch_loop(
    watcher: Watcher,
    announce: Callable[[Alert], None],
    report: Callable[[str], None] = print,
    interval_s: float = 300,
    on_failure: Callable[[Alert], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    max_polls: int | None = None,
) -> None:
    """Poll forever (or max_polls times). Each alert is announced; failures can trigger on_failure."""
    polls = 0
    while max_polls is None or polls < max_polls:
        alerts = watcher.poll()
        polls += 1
        for error in watcher.errors:
            report(error)
        if polls == 1:
            failing = [a for a in alerts if a.kind == "failing"]
            report(f"Watching {len({repo for repo, _ in watcher.state})} repositories. "
                   f"{len(failing)} workflow(s) failing right now.")
        for alert in alerts:
            announce(alert)
            if alert.kind == "failing" and on_failure is not None:
                on_failure(alert)
        if max_polls is not None and polls >= max_polls:
            break
        sleep(interval_s)
