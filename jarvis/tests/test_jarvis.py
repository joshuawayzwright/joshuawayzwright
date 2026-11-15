"""Offline tests: tool handlers against a real local git repo, and the agent loop with a fake Claude client."""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from jarvis import github, tools
from jarvis.agent import Jarvis
from jarvis.tools import ToolContext, execute


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    repo = tmp_path / "repos" / "acme" / "rocket"
    repo.mkdir(parents=True)
    (repo / "src").mkdir()
    (repo / "src" / "engine.py").write_text("def ignite():\n    return 'whoosh'\n\nTHRUST = 9000\n")
    (repo / "README.md").write_text("# Rocket\n")
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com"]
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run([*git, "commit", "-qm", "Initial engine"], cwd=repo, check=True)
    return tmp_path / "repos"


def ctx(workspace: Path, approve: bool = False) -> ToolContext:
    return ToolContext(workspace=workspace, approve=lambda _q: approve)


def test_validate_repo_accepts_urls_and_rejects_traversal() -> None:
    assert github.validate_repo("https://github.com/acme/rocket.git") == "acme/rocket"
    for bad in ("acme", "../etc/passwd", "acme/..", "a/b/c", "acme/rocket; rm -rf /"):
        with pytest.raises(github.GitHubError):
            github.validate_repo(bad)


def test_pull_repo_rejects_option_injection_ref(workspace: Path) -> None:
    with pytest.raises(github.GitHubError):
        github.pull_repo(workspace, "acme/rocket", "--upload-pack=evil")


def test_list_read_search_and_log(workspace: Path) -> None:
    c = ctx(workspace)
    assert execute(c, "list_local_repos", {}) == ("acme/rocket", False)

    listing, err = execute(c, "list_files", {"repo": "acme/rocket", "glob": "*.py"})
    assert not err and "src/engine.py" in listing and "README.md" not in listing

    content, err = execute(c, "read_file", {"repo": "acme/rocket", "path": "src/engine.py", "start_line": 4})
    assert not err and "THRUST = 9000" in content and "ignite" not in content

    hits, err = execute(c, "search_code", {"repo": "acme/rocket", "pattern": "def \\w+"})
    assert not err and "src/engine.py:1:def ignite" in hits

    log, err = execute(c, "git_log", {"repo": "acme/rocket"})
    assert not err and "Initial engine" in log


def test_errors_are_reported_not_raised(workspace: Path) -> None:
    c = ctx(workspace)
    out, err = execute(c, "read_file", {"repo": "acme/rocket", "path": "../../../etc/passwd"})
    assert err and "outside the repository" in out
    out, err = execute(c, "read_file", {"repo": "acme/missing", "path": "x"})
    assert err and "pull_repo first" in out
    out, err = execute(c, "read_file", {"repo": "acme/rocket"})
    assert err and "Missing required field 'path'" in out
    out, err = execute(c, "git_log", {"repo": "acme/rocket", "limit": "5"})
    assert err and "must be of type integer" in out
    out, err = execute(c, "nope", {})
    assert err and "Unknown tool" in out


def test_write_and_run_require_approval(workspace: Path) -> None:
    target = workspace / "acme" / "rocket" / "notes.txt"
    out, _ = execute(ctx(workspace, approve=False), "write_file", {"repo": "acme/rocket", "path": "notes.txt", "content": "hi"})
    assert "declined" in out and not target.exists()

    out, err = execute(ctx(workspace, approve=True), "write_file", {"repo": "acme/rocket", "path": "notes.txt", "content": "hi"})
    assert not err and target.read_text() == "hi"

    out, err = execute(ctx(workspace, approve=True), "write_file", {"repo": "acme/rocket", "path": ".git/config", "content": "x"})
    assert err

    out, _ = execute(ctx(workspace, approve=False), "run_command", {"repo": "acme/rocket", "command": "echo hi"})
    assert "declined" in out
    out, err = execute(ctx(workspace, approve=True), "run_command", {"repo": "acme/rocket", "command": "echo hi"})
    assert not err and "exit code 0" in out and "hi" in out


def test_pull_repo_updates_existing_clone(tmp_path: Path, workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Clone the fixture repo locally under acme/clone, then pull again after a new upstream commit.
    upstream = workspace / "acme" / "rocket"
    clone = workspace / "acme" / "clone"
    subprocess.run(["git", "clone", "-q", str(upstream), str(clone)], check=True)
    (upstream / "new.txt").write_text("new")
    subprocess.run(["git", "add", "."], cwd=upstream, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-qm", "Add new"], cwd=upstream, check=True)

    summary = github.pull_repo(workspace, "acme/clone")
    assert summary.startswith("Updated acme/clone") and "Add new" in summary


# ---- Agent loop with a fake Claude client -------------------------------------------------


def block(**kw: object) -> SimpleNamespace:
    return SimpleNamespace(**kw)


class FakeMessages:
    def __init__(self, responses: list[SimpleNamespace]) -> None:
        self.responses = responses
        self.calls: list[dict] = []

    def create(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})  # type: ignore[arg-type]
        return self.responses.pop(0)


def test_agent_runs_tools_and_returns_answer(workspace: Path) -> None:
    fake = FakeMessages(
        [
            SimpleNamespace(
                stop_reason="tool_use",
                content=[
                    block(type="thinking", thinking=""),
                    block(type="text", text="Searching the engine."),
                    block(type="tool_use", id="t1", name="search_code", input={"repo": "acme/rocket", "pattern": "THRUST"}),
                    block(type="tool_use", id="t2", name="read_file", input={"repo": "acme/rocket", "path": "nope.py"}),
                ],
            ),
            SimpleNamespace(stop_reason="end_turn", content=[block(type="text", text="Thrust is 9000 (src/engine.py:4).")]),
        ]
    )
    client = SimpleNamespace(beta=SimpleNamespace(messages=fake))
    out: list[str] = []
    jarvis = Jarvis(ctx=ctx(workspace), client=client, on_text=out.append, on_tool=lambda _l: None)

    answer = jarvis.ask("What's the thrust?")

    assert answer == "Thrust is 9000 (src/engine.py:4)."
    first = fake.calls[0]
    assert first["model"] == "claude-opus-5-5"
    assert first["thinking"] == {"type": "adaptive"} and first["fallbacks"] == "default"
    # Both tool results return together in one user message, with the failure flagged.
    results = fake.calls[1]["messages"][-1]["content"]
    assert [r["tool_use_id"] for r in results] == ["t1", "t2"]
    assert results[0]["is_error"] is False and "engine.py:4" in results[0]["content"]
    assert results[1]["is_error"] is True
    # The assistant turn is appended unchanged, thinking block included.
    assert fake.calls[1]["messages"][1]["content"][0].type == "thinking"


def test_agent_stops_on_refusal(workspace: Path) -> None:
    fake = FakeMessages([SimpleNamespace(stop_reason="refusal", content=[])])
    out: list[str] = []
    jarvis = Jarvis(ctx=ctx(workspace), client=SimpleNamespace(beta=SimpleNamespace(messages=fake)), on_text=out.append, on_tool=lambda _l: None)
    jarvis.ask("hi")
    assert "declined" in out[-1]


def test_tool_schemas_have_handlers() -> None:
    assert {s["name"] for s in tools.TOOL_SCHEMAS} == set(tools.HANDLERS)
