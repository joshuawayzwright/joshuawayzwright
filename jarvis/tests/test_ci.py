"""CI diagnosis, repository activity and the morning briefing."""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from jarvis import cli, github
from jarvis.tools import ToolContext, execute


def test_failure_excerpt_shows_output_before_the_error() -> None:
    log = "\n".join(
        ["2026-11-15T10:00:00.0000000Z setup"] * 200
        + ["\x1b[36;1mpytest -q\x1b[0m", "FAILED test_x.py::test_y - AssertionError", "warn", "warn", "warn",
           "##[error]Process completed with exit code 1.", "Post job cleanup."] + ["cleanup noise"] * 50
    )
    excerpt = github.failure_excerpt(log, before=10)
    assert "FAILED test_x.py::test_y" in excerpt and "pytest -q" in excerpt
    assert "\x1b[" not in excerpt and "2026-11-15T" not in excerpt
    assert "(previous line repeated 2 more times)" in excerpt
    assert excerpt.count("cleanup noise") <= 5


def run(id_: int, wf: int, conclusion: str, sha: str, tree: str, created: str, branch: str = "main",
        event: str = "push", name: str = "CI") -> dict:
    return {"id": id_, "workflow_id": wf, "name": name, "status": "completed", "conclusion": conclusion,
            "head_sha": sha, "head_branch": branch, "event": event, "created_at": created, "html_url": f"u{id_}",
            "head_commit": {"message": "Break things\n\nbody", "tree_id": tree}}


def test_ci_failure_finds_latest_failed_run(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list = []
    failing = run(5, 1, "failure", "merge5", "treeA", "2026-11-15T10:00:00Z")
    history = [failing, run(4, 1, "success", "pr4", "treeA", "2026-11-15T09:00:00Z", branch="feature", event="pull_request")]

    def fake_get(path, params=None, accept=""):
        calls.append((path, params))
        if path.endswith("/actions/runs"):
            return {"workflow_runs": [failing, run(6, 2, "success", "merge5", "treeA", "2026-11-15T10:00:00Z", name="Lint")]}
        if "/workflows/" in path:
            return {"workflow_runs": history}
        return {"jobs": [
            {"id": 1, "name": "test", "conclusion": "failure", "steps": [{"name": "Run tests", "conclusion": "failure"}]},
            {"id": 2, "name": "lint", "conclusion": "success", "steps": []},
        ]}

    monkeypatch.setattr(github, "api_get", fake_get)
    monkeypatch.setattr(github, "api_get_text", lambda path: "E   assert 1 == 2\n##[error]exit 1")
    out, err = execute(ToolContext(workspace=Path("."), approve=lambda _q: True), "get_ci_failure",
                       {"repo": "acme/api", "branch": "main"})
    assert not err
    assert "Run 5 (CI) on main: failure" in out and "Commit: merge5 Break things" in out
    assert "CURRENT:" in out
    assert "INTERMITTENT: identical code passed in run 4" in out  # same tree as the passing PR commit
    assert "Job 'test' failed at step(s): Run tests" in out and "assert 1 == 2" in out and "lint" not in out
    assert calls[0] == ("/repos/acme/api/actions/runs", {"branch": "main", "per_page": 50})


def test_ci_failure_reports_all_green_and_already_fixed(monkeypatch: pytest.MonkeyPatch) -> None:
    old = run(1, 1, "failure", "a", "t1", "2026-10-01T00:00:00Z")
    newer = run(2, 1, "success", "b", "t2", "2026-10-02T00:00:00Z")

    def fake_get(path, params=None, accept=""):
        if path.endswith("/actions/runs/1"):
            return old
        if "/workflows/" in path:
            return {"workflow_runs": [newer, old]}
        if path.endswith("/actions/runs"):
            return {"workflow_runs": [old] if params.get("status") == "failure" else [newer, old]}
        if path.endswith("/jobs"):
            return {"jobs": []}
        return {"default_branch": "main"}

    monkeypatch.setattr(github, "api_get", fake_get)
    out = github.ci_failure("acme/api")
    assert out.startswith("All workflows on main in acme/api currently pass.") and "run 1" in out
    assert "ALREADY FIXED" in github.ci_failure("acme/api", run_id=1)


def test_latest_per_workflow() -> None:
    runs = [run(3, 1, "failure", "c", "t", "3"), {"id": 9, "workflow_id": 2, "status": "in_progress"},
            run(2, 1, "success", "b", "t", "2"), run(1, 2, "success", "a", "t", "1")]
    assert [r["id"] for r in github.latest_per_workflow(runs)] == [3, 1]


def test_activity_separates_issues_from_pull_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(path, params=None, accept=""):
        if path.endswith("/pulls"):
            return [{"number": 3, "title": "Add X", "user": {"login": "ana"}, "draft": False}]
        if path.endswith("/issues"):
            return [{"number": 3, "title": "Add X", "pull_request": {}}, {"number": 4, "title": "Bug", "labels": [{"name": "bug"}]}]
        if path.endswith("/actions/runs"):
            return {"workflow_runs": [{"id": 9, "workflow_id": 1, "name": "CI", "status": "completed", "conclusion": "success"}]}
        if path == "/repos/acme/api":
            return {"default_branch": "main"}
        return [{"sha": "abcdef123", "commit": {"message": "Fix\n\nmore", "author": {"name": "ana"}}}]

    monkeypatch.setattr(github, "api_get", fake_get)
    data = github.activity("acme/api")
    assert [i["number"] for i in data["open_issues"]] == [4] and data["open_issues"][0]["labels"] == ["bug"]
    assert data["open_pull_requests"][0]["author"] == "ana"
    assert data["recent_commits"][0] == {"sha": "abcdef1", "message": ["Fix"], "author": "ana", "date": None}
    assert data["default_branch_ci"][0]["workflow"] == "CI" and data["default_branch_ci"][0]["conclusion"] == "success"


def test_log_download_never_forwards_the_token(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, str | None] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            seen[self.path] = self.headers.get("Authorization")
            if self.path.startswith("/repos/"):
                self.send_response(302)
                self.send_header("Location", f"http://127.0.0.1:{self.server.server_port}/blob/log.txt?sig=1")
                self.end_headers()
            else:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"line 1\n##[error]boom\n")

        def log_message(self, *args: object) -> None:
            return None

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        monkeypatch.setattr(github, "API_ROOT", f"http://127.0.0.1:{server.server_port}")
        monkeypatch.setenv("GITHUB_TOKEN", "secret-token")
        assert "##[error]boom" in github.api_get_text("/repos/a/b/actions/jobs/1/logs")
    finally:
        server.shutdown()
    assert seen["/repos/a/b/actions/jobs/1/logs"] == "Bearer secret-token"
    assert seen["/blob/log.txt?sig=1"] is None  # the storage host never sees the token


def test_briefing_prompt_names_owner_and_tools() -> None:
    prompt = cli.briefing_prompt("octocat")
    for needle in ("octocat", "list_user_repos", "github_activity", "get_ci_failure"):
        assert needle in prompt
