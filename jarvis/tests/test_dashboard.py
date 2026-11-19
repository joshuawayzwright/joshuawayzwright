"""Web dashboard: CI snapshot from the watcher, alerts, session stats, token usage and the HTTP routes."""

from __future__ import annotations

import http.client
import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from jarvis import github, watch, web
from jarvis.agent import Jarvis
from jarvis.dashboard import Dashboard
from jarvis.memory import Memory
from jarvis.tools import ToolContext
from test_watch import watcher_for


def make_jarvis(tmp_path: Path, memory: bool = True) -> Jarvis:
    ctx = ToolContext(workspace=tmp_path, approve=lambda q: False,
                      memory=Memory(tmp_path / "memory.md") if memory else None)
    return Jarvis(ctx=ctx, client=SimpleNamespace())


def test_snapshot_lists_failing_first_with_a_fix_prompt_and_records_alerts(tmp_path: Path) -> None:
    watcher, _ = watcher_for([
        {"acme/api": [(1, "CI", "success"), (2, "Lint", "success")], "acme/web": [(3, "Deploy", "success")]},
        {"acme/api": [(1, "CI", "success"), (2, "Lint", "success")], "acme/web": [(3, "Deploy", "failure")]},
        {"acme/api": [(1, "CI", "success"), (2, "Lint", "success")], "acme/web": [(3, "Deploy", "success")]},
    ])
    now = [1000.0]
    dash = Dashboard(make_jarvis(tmp_path), watcher, interval_s=300, clock=lambda: now[0])
    dash.poll_once()
    ci = dash.snapshot()["ci"]
    assert ci["totals"] == {"repos": 2, "workflows": 3, "failing": 0, "passing": 3}
    assert ci["alerts"] == [] and ci["last_checked"] == 1000.0 and ci["next_check"] == 1300.0

    now[0] = 1300.0
    dash.poll_once()
    ci = dash.snapshot()["ci"]
    assert ci["totals"]["failing"] == 1
    assert [r["repo"] for r in ci["repos"]] == ["acme/web", "acme/api"]  # failing repositories first
    deploy = ci["repos"][0]["workflows"][0]
    assert deploy["status"] == "failing" and deploy["url"] == "https://x/0" and deploy["commit"] == "sha0"
    assert "get_ci_failure" in deploy["fix_prompt"] and "acme/web" in deploy["fix_prompt"]
    assert "fix_prompt" not in ci["repos"][1]["workflows"][0]
    assert [(a["repo"], a["kind"], a["time"]) for a in ci["alerts"]] == [("acme/web", "failing", 1300.0)]

    dash.poll_once()
    assert [a["kind"] for a in dash.snapshot()["ci"]["alerts"]] == ["recovered", "failing"]  # newest first


def test_poll_errors_are_reported_not_raised(tmp_path: Path) -> None:
    def explode() -> list:
        raise OSError("network down")

    watcher = SimpleNamespace(poll=explode, errors=[], runs={}, repos=[], api=None)
    dash = Dashboard(make_jarvis(tmp_path), watcher)  # type: ignore[arg-type]
    dash.poll_once()
    ci = dash.snapshot()["ci"]
    assert ci["errors"] == ["Check failed: OSError: network down"] and ci["checking"] is False


def test_session_stats_usage_and_memory(tmp_path: Path) -> None:
    jarvis = make_jarvis(tmp_path)
    jarvis.ctx.memory.remember("Prefers draft PRs")
    jarvis.messages.extend([{"role": "user", "content": "hi"}, {"role": "assistant", "content": []},
                            {"role": "user", "content": [{"type": "tool_result"}]}])
    jarvis._add_usage(SimpleNamespace(input_tokens=100, output_tokens=20, cache_read_input_tokens=50,
                                      cache_creation_input_tokens=None))
    jarvis._add_usage(None)  # a response without usage still counts as a request
    snap = Dashboard(jarvis, auto_approve=True).snapshot(busy=True)
    assert snap["ci"] == {"enabled": False}
    s = snap["session"]
    assert s["busy"] and s["auto_approve"] and s["turns"] == 1 and s["tools"] > 0
    assert s["usage"] == {"requests": 2, "input_tokens": 100, "output_tokens": 20,
                          "cache_read_input_tokens": 50, "cache_creation_input_tokens": 0}
    assert s["memory"]["count"] == 1 and s["memory"]["recent"][0].startswith("Prefers draft PRs")
    assert Dashboard(make_jarvis(tmp_path, memory=False)).snapshot()["session"]["memory"]["enabled"] is False


def test_refresh_wakes_the_poller(tmp_path: Path) -> None:
    watcher, _ = watcher_for([{"acme/api": [(1, "CI", "success")]}, {"acme/api": [(1, "CI", "failure")]}])
    dash = Dashboard(make_jarvis(tmp_path), watcher, interval_s=3600)
    assert Dashboard(make_jarvis(tmp_path)).refresh() is False  # nothing watched
    dash.start()
    try:
        for _ in range(200):
            if dash.last_checked:
                break
            threading.Event().wait(0.01)
        assert dash.refresh() is True
        for _ in range(200):
            if dash.snapshot()["ci"]["totals"]["failing"]:
                break
            threading.Event().wait(0.01)
        assert dash.snapshot()["ci"]["totals"]["failing"] == 1  # second poll happened long before the hour
    finally:
        dash.stop()


@pytest.fixture
def served(tmp_path: Path):
    watcher, _ = watcher_for([{"acme/api": [(1, "CI", "failure")]}])
    jarvis = make_jarvis(tmp_path)
    session = web.WebSession(jarvis)
    dash = Dashboard(jarvis, watcher)
    dash.poll_once()
    httpd, token = web.serve(session, "127.0.0.1", 0, dashboard=dash)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield SimpleNamespace(port=httpd.server_address[1], token=token, session=session)
    httpd.shutdown()


def request(port: int, method: str, path: str, token: str | None = None) -> http.client.HTTPResponse:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request(method, path, "{}" if method == "POST" else None, {"X-Jarvis-Token": token} if token else {})
    return conn.getresponse()


def test_dashboard_routes_need_the_token(served) -> None:
    assert request(served.port, "GET", "/dashboard").status == 401
    assert request(served.port, "GET", "/api/dashboard", "wrong").status == 401
    assert request(served.port, "POST", "/api/dashboard/refresh").status == 401
    page = request(served.port, "GET", f"/dashboard?token={served.token}")
    assert page.status == 200 and b"<title>Jarvis Dashboard</title>" in page.read()
    assert page.getheader("Referrer-Policy") == "no-referrer"
    chat = request(served.port, "GET", f"/?token={served.token}").read()
    assert b'id="dash"' in chat and b"#ask=" not in chat.split(b"<script>")[0]


def test_dashboard_api_and_refresh(served) -> None:
    res = request(served.port, "GET", "/api/dashboard", served.token)
    data = json.loads(res.read())
    assert res.status == 200 and data["ci"]["totals"]["failing"] == 1
    assert data["session"]["busy"] is False
    assert request(served.port, "POST", "/api/dashboard/refresh", served.token).status == 200


def test_refresh_without_watch_is_a_conflict(tmp_path: Path) -> None:
    session = web.WebSession(make_jarvis(tmp_path))
    httpd, token = web.serve(session, "127.0.0.1", 0)  # default dashboard: no CI watch
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        port = httpd.server_address[1]
        assert request(port, "POST", "/api/dashboard/refresh", token).status == 409
        assert json.loads(request(port, "GET", "/api/dashboard", token).read())["ci"] == {"enabled": False}
    finally:
        httpd.shutdown()


def test_workflow_history_is_oldest_first_and_capped() -> None:
    runs = [  # newest first, as GitHub returns them
        {"workflow_id": 1, "status": "completed", "conclusion": "failure"},
        {"workflow_id": 1, "status": "in_progress", "conclusion": None},
        {"workflow_id": 2, "status": "completed", "conclusion": "success"},
        {"workflow_id": 1, "status": "completed", "conclusion": "cancelled"},
        {"workflow_id": 1, "status": "completed", "conclusion": "success"},
    ]
    assert watch.workflow_history(runs) == {1: ["passing", "other", "failing"], 2: ["passing"]}
    assert watch.workflow_history(runs, limit=2) == {1: ["other", "failing"], 2: ["passing"]}


class PullsAPI:
    """Workflow runs for acme/api and acme/web; open pull requests for acme/api; listing fails for acme/web."""

    FAILED = github.FAILED
    latest_per_workflow = staticmethod(github.latest_per_workflow)

    def repo_info(self, repo: str) -> dict:
        return {"default_branch": "main"}

    def api_get(self, path: str, params: dict) -> object:
        if path.endswith("/actions/runs"):
            return {"workflow_runs": [
                {"id": 2, "workflow_id": 7, "name": "CI", "status": "completed", "conclusion": "failure", "head_sha": "b" * 40},
                {"id": 1, "workflow_id": 7, "name": "CI", "status": "completed", "conclusion": "success", "head_sha": "a" * 40},
            ]}
        if path == "/repos/acme/web/pulls":
            raise github.GitHubError("403 rate limited")
        return [{"number": 12, "title": "Add dark mode", "html_url": "https://github.com/acme/api/pull/12",
                 "user": {"login": "octo"}, "draft": True, "updated_at": "2026-11-16T10:00:00Z"}]


def test_pulls_history_and_activity_in_snapshot(tmp_path: Path) -> None:
    dash = Dashboard(make_jarvis(tmp_path), watch.Watcher(["acme/api", "acme/web"], [], api=PullsAPI()))
    dash.poll_once()
    snap = dash.snapshot(activity=[{"time": 1.0, "kind": "tool", "text": "pull_repo repo=acme/api"}], waiting=1)
    ci = snap["ci"]
    assert ci["repos"][0]["workflows"][0]["history"] == ["passing", "failing"]
    assert ci["pulls"] == [{"repo": "acme/api", "number": 12, "title": "Add dark mode", "draft": True, "author": "octo",
                            "url": "https://github.com/acme/api/pull/12", "updated_at": "2026-11-16T10:00:00Z"}]
    assert ci["errors"] == ["acme/web: couldn't list pull requests: 403 rate limited"]
    assert snap["session"]["waiting_for_approval"] == 1
    assert snap["session"]["activity"][0]["kind"] == "tool"


def test_web_session_records_activity(tmp_path: Path) -> None:
    session = web.WebSession(make_jarvis(tmp_path))
    session.jarvis.on_tool("read_file repo=acme/api path=" + "x" * 300)
    session._record("ask", "  fix   the\nbuild  ")
    activity = session.recent_activity()
    assert [a["kind"] for a in activity] == ["ask", "tool"]  # newest first
    assert activity[0]["text"] == "fix the build"
    assert len(activity[1]["text"]) == web.ACTIVITY_TEXT + 1 and activity[1]["text"].endswith("…")
