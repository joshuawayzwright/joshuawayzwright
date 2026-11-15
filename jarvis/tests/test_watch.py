"""Watch mode: baseline, change detection, no repeat alerts, owners, and auto-fix hooks."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from jarvis import github, watch


class FakeAPI:
    """Serves scripted workflow results per poll."""

    FAILED = github.FAILED
    latest_per_workflow = staticmethod(github.latest_per_workflow)

    def __init__(self, polls: list[dict[str, list[tuple[int, str, str]]]], owner_repos: list[dict] | None = None,
                 owner_error: bool = False) -> None:
        self.polls = polls
        self.poll = -1
        self.owner_repos = owner_repos or []
        self.owner_error = owner_error
        self.repo_info_calls = 0

    def list_user_repos(self, owner: str, limit: int) -> list[dict]:
        if self.owner_error:
            raise github.GitHubError("listing blocked")
        self.poll += 1  # listing happens at the start of each poll when owners are watched
        return self.owner_repos

    def repo_info(self, repo: str) -> dict:
        self.repo_info_calls += 1
        return {"default_branch": "main"}

    def api_get(self, path: str, params: dict) -> dict:
        repo = path.split("/repos/")[1].split("/actions")[0]
        results = self.polls[self.poll].get(repo, [])
        return {"workflow_runs": [
            {"id": i * 100 + wf, "workflow_id": wf, "name": name, "status": "completed", "conclusion": conclusion,
             "head_sha": f"sha{i}", "html_url": f"https://x/{i}"}
            for i, (wf, name, conclusion) in enumerate(results)
        ]}


def watcher_for(polls: list[dict]) -> tuple[watch.Watcher, FakeAPI]:
    api = FakeAPI(polls)
    w = watch.Watcher(["acme/api", "acme/web"], [], api=api)
    original = w.poll

    def poll() -> list[watch.Alert]:
        api.poll += 1
        return original()

    w.poll = poll  # type: ignore[method-assign]
    return w, api


def test_first_poll_reports_current_failures_then_only_changes() -> None:
    w, api = watcher_for([
        {"acme/api": [(1, "CI", "failure"), (2, "Lint", "success")], "acme/web": [(3, "Deploy", "success")]},
        {"acme/api": [(1, "CI", "failure"), (2, "Lint", "success")], "acme/web": [(3, "Deploy", "success")]},
        {"acme/api": [(1, "CI", "success"), (2, "Lint", "failure")], "acme/web": [(3, "Deploy", "success")]},
    ])
    first = w.poll()
    assert [(a.repo, a.workflow, a.kind) for a in first] == [("acme/api", "CI", "failing")]
    assert w.poll() == []  # still failing: no repeat alert
    third = w.poll()
    assert {(a.workflow, a.kind) for a in third} == {("CI", "recovered"), ("Lint", "failing")}
    assert api.repo_info_calls == 2  # default branches are cached per repository


def test_watch_loop_announces_and_triggers_fixes() -> None:
    w, _ = watcher_for([
        {"acme/api": [(1, "CI", "success")]},
        {"acme/api": [(1, "CI", "failure")]},
    ])
    announced, fixed, reports, sleeps = [], [], [], []
    watch.watch_loop(w, announce=announced.append, report=reports.append, interval_s=60,
                     on_failure=fixed.append, sleep=sleeps.append, max_polls=2)
    assert reports[0] == "Watching 1 repositories. 0 workflow(s) failing right now."
    assert [a.kind for a in announced] == ["failing"] and fixed == announced
    assert sleeps == [60]
    assert "acme/api: CI is failing on commit sha0" in announced[0].message()
    assert "(run 1)" in watch.fix_prompt(announced[0]) and "get_ci_failure" in watch.fix_prompt(announced[0])


def test_owners_watch_recently_active_repos_and_survive_errors() -> None:
    now = datetime.now(timezone.utc)
    api = FakeAPI([{"acme/new": [(1, "CI", "failure")]}], owner_repos=[
        {"repo": "acme/new", "pushed_at": (now - timedelta(days=2)).isoformat().replace("+00:00", "Z")},
        {"repo": "acme/stale", "pushed_at": (now - timedelta(days=200)).isoformat().replace("+00:00", "Z")},
    ])
    w = watch.Watcher([], ["acme"], api=api)
    assert [a.repo for a in w.poll()] == ["acme/new"]

    blocked = watch.Watcher(["acme/api"], ["acme"], api=FakeAPI([{"acme/api": []}], owner_error=True))
    blocked.api.poll = 0
    assert blocked.poll() == [] and "listing blocked" in blocked.errors[0]
