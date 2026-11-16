"""Token budget, the live crew panel in the web interface, and the --selftest run."""

from __future__ import annotations

import http.client
import json
import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from jarvis import cli, selftest, team, web
from jarvis.agent import Budget, Jarvis, parse_tokens
from jarvis.tools import ToolContext
from test_team import CrewMessages, chief, delegate, text, tool_turn, with_usage

# ---- Budget ---------------------------------------------------------------------------------


@pytest.mark.parametrize(("given", "expected"), [("500000", 500_000), ("500k", 500_000), ("2M", 2_000_000), ("1.5m", 1_500_000), ("1,000", 1_000)])
def test_parse_tokens(given: str, expected: int) -> None:
    assert parse_tokens(given) == expected


@pytest.mark.parametrize("bad", ["lots", "0", "-5k", "k"])
def test_parse_tokens_rejects_bad_values(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_tokens(bad)


def test_budget_counts_every_token_type_and_stops_the_chief(tmp_path: Path) -> None:
    fake = CrewMessages({"chief": [with_usage(tool_turn(("r1", "list_local_repos", {})), 400, 100, cached=600)]})
    out: list[str] = []
    jarvis, _ = chief(tmp_path, fake, budget=Budget(1_000))
    jarvis.on_text = out.append
    reply = jarvis.ask("go")
    assert jarvis.budget is not None and jarvis.budget.used == 1_100  # 400 + 100 + 600 cache reads
    assert len(fake.requests("chief")) == 1  # the second request never went out
    assert "token budget is spent" in reply and "1,100 of 1,000" in out[-1]


def test_specialists_share_the_chiefs_budget(tmp_path: Path) -> None:
    fake = CrewMessages(
        {
            "chief": [with_usage(tool_turn(delegate("d1", "scout", "research")), 100, 10)],
            "scout": [with_usage(tool_turn(("s1", "search_github_repos", {"query": "x"})), 900, 50)],
        }
    )
    jarvis, _ = chief(tmp_path, fake, budget=Budget(1_000))
    reply = jarvis.ask("go")
    member = jarvis.team.members["scout"]  # type: ignore[union-attr]
    assert member.budget is jarvis.budget
    # Scout spent the budget mid-assignment and stopped; then the chief stopped before its next request.
    assert len(fake.requests("scout")) == 1 and len(fake.requests("chief")) == 1
    assert "token budget is spent" in reply
    assert "Budget: 1,060 of 1,000 tokens used." in jarvis.team.status()  # type: ignore[union-attr]


def test_budget_flag_and_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seen: dict[str, object] = {}
    monkeypatch.setattr(cli, "run", lambda args, *_: seen.update(budget=args.budget) or 0)
    cli.main(["--budget", "750k", "--no-mcp", "--workspace", str(tmp_path / "r"), "hi"])
    assert seen["budget"] == 750_000
    monkeypatch.setenv("JARVIS_BUDGET", "2M")
    cli.main(["--no-mcp", "--workspace", str(tmp_path / "r"), "hi"])
    assert seen["budget"] == 2_000_000
    with pytest.raises(SystemExit):
        cli.main(["--budget", "lots", "--no-mcp", "--workspace", str(tmp_path / "r"), "hi"])


# ---- Live crew state and the web panel --------------------------------------------------------


def test_snapshot_tracks_working_done_and_error(tmp_path: Path) -> None:
    started, release = threading.Event(), threading.Event()

    class Slow(CrewMessages):
        def stream(self, **kwargs: object):  # type: ignore[no-untyped-def]
            who = self.who(str(kwargs["system"]))
            if who == "medic":
                raise ConnectionError("down")
            if who == "architect":
                started.set()
                release.wait(5)
            return super().stream(**kwargs)

    fake = Slow({"chief": [tool_turn(delegate("d1", "architect", "Plan the work\nsecond line")), text("ok"),
                           tool_turn(delegate("d2", "medic", "CI?")), text("ok")],
                 "architect": [text("## Plan\n1. Edit a.py\nVERDICT: PASS")]})
    jarvis, _ = chief(tmp_path, fake, budget=Budget(10_000))
    crew = jarvis.team
    assert crew is not None
    worker = threading.Thread(target=jarvis.ask, args=("plan",))
    worker.start()
    assert started.wait(5)
    architect = next(a for a in crew.snapshot()["agents"] if a["key"] == "architect")
    assert architect["status"] == "working" and architect["last"] == "Working: Plan the work"
    release.set()
    worker.join(5)

    jarvis.ask("ci")
    snap = crew.snapshot()
    by_key = {a["key"]: a for a in snap["agents"]}
    assert [a["name"] for a in snap["agents"]][0] == "Jarvis" and len(snap["agents"]) == 7
    assert by_key["architect"]["status"] == "done" and by_key["architect"]["last"].startswith("VERDICT: PASS · 1. Edit a.py")
    assert by_key["medic"]["status"] == "error" and by_key["medic"]["last"] == "Error: ConnectionError"
    assert by_key["forge"]["status"] == "idle" and by_key["forge"]["tasks"] == 0
    assert snap["budget"] == {"limit": 10_000, "used": 0} and snap["gate"] == team.CLEAN
    json.dumps(snap)  # JSON-ready


def _get(port: int, path: str) -> tuple[int, bytes]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request("GET", path)
    response = conn.getresponse()
    return response.status, response.read()


@pytest.mark.parametrize("team_mode", [True, False])
def test_web_team_endpoint(tmp_path: Path, team_mode: bool) -> None:
    jarvis = Jarvis(ctx=ToolContext(workspace=tmp_path, approve=lambda _q: False), client=object(), team_mode=team_mode)
    httpd, token = web.serve(web.WebSession(jarvis), "127.0.0.1", 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        port = httpd.server_address[1]
        assert _get(port, "/api/team")[0] == 401
        status, body = _get(port, f"/api/team?token={token}")
        data = json.loads(body)
        assert status == 200 and data["enabled"] is team_mode
        if team_mode:
            assert [a["name"] for a in data["agents"]][1:] == [r.name for r in team.ROLES.values()]
        status, page = _get(port, f"/?token={token}")
        assert status == 200 and b'id="crew"' in page and b"/api/team" in page
    finally:
        httpd.shutdown()


# ---- Self-test ------------------------------------------------------------------------------

FIX = selftest.CODE.replace(
    "    return ordered[middle]\n",
    "    if len(ordered) % 2:\n        return ordered[middle]\n    return (ordered[middle - 1] + ordered[middle]) / 2\n",
)


def test_fixture_starts_broken_and_verify_catches_shortcuts(tmp_path: Path) -> None:
    repo = selftest.build_fixture(tmp_path)
    assert not all(c.ok for c in selftest.verify(repo))
    with pytest.raises(FileExistsError):
        selftest.build_fixture(tmp_path)
    # Shortcut: delete the failing test and commit on a branch. The suite passes; the original tests don't.
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@e"]
    subprocess.run(["git", "checkout", "-qb", "cheat"], cwd=repo, check=True)
    tests = (repo / "test_stats.py").read_text()
    start = tests.index("    def test_median_even")
    (repo / "test_stats.py").write_text(tests[:start] + tests[tests.index("    def test_spread"):])
    subprocess.run([*git, "commit", "-qam", "Drop flaky test"], cwd=repo, check=True)
    checks = {c.name: c.ok for c in selftest.verify(repo)}
    assert checks["Suite passes on the branch"] is True
    assert checks["Original tests pass on the new code"] is False


def test_selftest_end_to_end_with_a_scripted_crew(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    workspace = tmp_path / "repos"
    repo = selftest.build_fixture(workspace)
    fake = CrewMessages(
        {
            "chief": [
                tool_turn(delegate("c1", "architect", "Plan the fix")),
                tool_turn(delegate("c2", "forge", "Fix median")),
                tool_turn(delegate("c3", "sentinel", "Verify")),
                tool_turn(delegate("c4", "herald", "Commit")),
                text("Done: median fixed and committed."),
            ],
            "architect": [text("## Plan\n1. stats.py: average the two middle values for even lengths.")],
            "forge": [tool_turn(("f1", "write_file", {"repo": selftest.REPO, "path": "stats.py", "content": FIX})),
                      text("## Changed\nstats.py")],
            "sentinel": [tool_turn(("s1", "run_command", {"repo": selftest.REPO, "command": "python3 -m unittest -q"})),
                         text("## Checks\nunittest: OK\n\nVERDICT: PASS")],
            "herald": [tool_turn(("h1", "commit_changes", {"repo": selftest.REPO, "message": "Fix median for even-length input"})),
                       text("## Shipped\nCommitted.")],
        }
    )
    jarvis, _ = chief(workspace, fake, autonomous=True, budget=Budget(selftest.DEFAULT_BUDGET))
    jarvis.ask(selftest.GOAL)

    sentinel_run = fake.requests("sentinel")[1]["messages"][-1]["content"][0]
    assert "OK" in sentinel_run["content"], sentinel_run
    log = cli.RunLog(tmp_path / "runs")
    assert cli.finish_selftest(repo, jarvis, log) == 0
    out = capsys.readouterr().out
    assert "SELF-TEST PASSED (6/6 checks)" in out and "forge → sentinel → herald" in out
    assert "## Self-test" in log.path.read_text()


def test_selftest_flag_sets_up_an_isolated_team_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seen: dict[str, object] = {}
    monkeypatch.setenv("JARVIS_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(cli, "run", lambda args, *_: seen.update(vars(args)) or 0)
    cli.main(["--selftest", "--no-mcp"])
    assert seen["auto"] and seen["team"] and seen["budget"] == selftest.DEFAULT_BUDGET
    assert seen["prompt"] == [selftest.GOAL]
    repo = Path(str(seen["selftest_repo"]))
    assert repo.is_relative_to(tmp_path / "home" / "selftest") and (repo / "stats.py").exists()
    with pytest.raises(SystemExit):
        cli.main(["--selftest", "--no-mcp", "fix", "something"])
