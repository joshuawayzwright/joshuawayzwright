"""Dashboard state for the web interface: CI health across watched repositories, alerts and session stats.

A background thread polls the Watcher every interval (or at once when the page asks for a refresh). The
browser reads a JSON snapshot; nothing here talks to Claude, so viewing the dashboard costs no tokens.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from typing import Any

from . import watch
from .agent import Jarvis

MAX_ALERTS = 50
MAX_MEMORY_NOTES = 5
MAX_PULLS_PER_REPO = 20


class Dashboard:
    def __init__(self, jarvis: Jarvis, watcher: watch.Watcher | None = None, interval_s: float = 300,
                 clock: Callable[[], float] = time.time, auto_approve: bool = False) -> None:
        self.jarvis = jarvis
        self.watcher = watcher
        self.interval_s = interval_s
        self.clock = clock
        self.auto_approve = auto_approve
        self.started_at = clock()
        self.lock = threading.Lock()
        self.alerts: deque[dict[str, Any]] = deque(maxlen=MAX_ALERTS)
        self.errors: list[str] = []
        self.pulls: dict[str, list[dict[str, Any]]] = {}
        self.last_checked: float | None = None
        self.next_check: float | None = None
        self.checking = False
        self._wake = threading.Event()
        self._stop = threading.Event()

    # Polling

    def poll_once(self) -> None:
        if self.watcher is None:
            return
        with self.lock:
            self.checking = True
        try:
            alerts = self.watcher.poll()
            errors = list(self.watcher.errors)
        except Exception as err:  # noqa: BLE001 - a network blip must not kill the poller
            alerts, errors = [], [f"Check failed: {type(err).__name__}: {err}"]
        pulls, pull_errors = self._fetch_pulls()
        now = self.clock()
        with self.lock:
            self.pulls = pulls
            errors += pull_errors
            for alert in alerts:
                self.alerts.appendleft({
                    "time": now, "repo": alert.repo, "workflow": alert.workflow, "kind": alert.kind,
                    "commit": alert.commit, "url": alert.url, "message": alert.message(),
                })
            self.errors = errors
            self.last_checked = now
            self.next_check = now + self.interval_s
            self.checking = False

    def _fetch_pulls(self) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
        """Open pull requests of every repository the watcher has seen; one request per repository."""
        assert self.watcher is not None
        repos = sorted({repo for repo, _ in self.watcher.runs} | set(self.watcher.repos))
        pulls: dict[str, list[dict[str, Any]]] = {}
        errors: list[str] = []
        for repo in repos:
            try:
                listed = self.watcher.api.api_get(f"/repos/{repo}/pulls", {"state": "open", "per_page": MAX_PULLS_PER_REPO,
                                                                          "sort": "updated", "direction": "desc"})
            except Exception as err:  # noqa: BLE001 - pull requests are extra; CI status still shows
                errors.append(f"{repo}: couldn't list pull requests: {err}")
                continue
            if isinstance(listed, list):
                pulls[repo] = [{
                    "number": p.get("number"), "title": str(p.get("title") or ""), "url": p.get("html_url"),
                    "author": (p.get("user") or {}).get("login"), "draft": bool(p.get("draft")),
                    "updated_at": p.get("updated_at"),
                } for p in listed]
        return pulls, errors

    def refresh(self) -> bool:
        """Ask the poller to check now. False when no repositories are being watched."""
        if self.watcher is None:
            return False
        self._wake.set()
        return True

    def start(self) -> None:
        if self.watcher is None:
            return

        def loop() -> None:
            while not self._stop.is_set():
                self.poll_once()
                self._wake.wait(self.interval_s)
                self._wake.clear()

        threading.Thread(target=loop, name="jarvis-dashboard", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    # Snapshot

    def _repos(self) -> list[dict[str, Any]]:
        assert self.watcher is not None
        grouped: dict[str, list[dict[str, Any]]] = {}
        for (repo, _), run in self.watcher.runs.items():
            item = dict(run)
            if item["status"] == "failing":
                item["fix_prompt"] = watch.fix_prompt(watch.Alert(
                    repo=repo, workflow=item["workflow"], kind="failing", run_id=item["run_id"],
                    url=item["url"], commit=item["commit"]))
            grouped.setdefault(repo, []).append(item)
        repos = []
        for repo, workflows in grouped.items():
            workflows.sort(key=lambda w: (w["status"] != "failing", w["workflow"].lower()))
            failing = sum(w["status"] == "failing" for w in workflows)
            repos.append({"repo": repo, "failing": failing, "workflows": workflows})
        repos.sort(key=lambda r: (-r["failing"], r["repo"].lower()))
        return repos

    def snapshot(self, busy: bool = False, activity: list[dict[str, Any]] | None = None, waiting: int = 0) -> dict[str, Any]:
        jarvis = self.jarvis
        memory = jarvis.ctx.memory
        notes = memory.notes() if memory is not None else []
        mcp = jarvis.mcp
        with self.lock:
            ci: dict[str, Any] = {"enabled": self.watcher is not None}
            if self.watcher is not None:
                repos = self._repos()
                workflows = [w for r in repos for w in r["workflows"]]
                ci.update({
                    "repos": repos,
                    "totals": {
                        "repos": len(repos),
                        "workflows": len(workflows),
                        "failing": sum(w["status"] == "failing" for w in workflows),
                        "passing": sum(w["status"] == "passing" for w in workflows),
                    },
                    "alerts": list(self.alerts),
                    "pulls": [dict(pull, repo=repo) for repo, items in self.pulls.items() for pull in items],
                    "errors": list(self.errors),
                    "last_checked": self.last_checked,
                    "next_check": self.next_check,
                    "checking": self.checking,
                    "interval_s": self.interval_s,
                })
            return {
                "now": self.clock(),
                "ci": ci,
                "session": {
                    "model": jarvis.model,
                    "effort": jarvis.effort,
                    "autonomous": jarvis.autonomous,
                    "auto_approve": self.auto_approve,
                    "busy": busy,
                    "waiting_for_approval": waiting,
                    "activity": activity or [],
                    "started_at": self.started_at,
                    "turns": sum(1 for m in jarvis.messages if m.get("role") == "user" and isinstance(m.get("content"), str)),
                    "usage": dict(jarvis.usage),
                    "tools": len(jarvis._tools),
                    "mcp": mcp.summary() if mcp is not None else None,
                    "memory": {"enabled": memory is not None, "count": len(notes), "recent": notes[-MAX_MEMORY_NOTES:][::-1]},
                },
            }
