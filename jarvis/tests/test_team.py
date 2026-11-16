"""Offline tests for team mode: Jarvis as chief, six specialists, parallel delegation and the quality gate."""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace

from fakes import FakeStream

import pytest

from jarvis import cli, team
from jarvis.agent import Jarvis
from jarvis.tools import ToolContext


def block(**kw: object) -> SimpleNamespace:
    return SimpleNamespace(**kw)


def text(reply: str) -> SimpleNamespace:
    return SimpleNamespace(stop_reason="end_turn", content=[block(type="text", text=reply)])


def tool_turn(*calls: tuple[str, str, dict]) -> SimpleNamespace:
    return SimpleNamespace(
        stop_reason="tool_use",
        content=[block(type="tool_use", id=cid, name=name, input=data) for cid, name, data in calls],
    )


def delegate(cid: str, agent: str, task: str, **extra: object) -> tuple[str, str, dict]:
    return (cid, "delegate", {"agent": agent, "task": task, **extra})


class CrewMessages:
    """A fake Claude client whose replies are scripted per agent, recognised by its system prompt."""

    def __init__(self, scripts: dict[str, list[SimpleNamespace]], barrier: threading.Barrier | None = None,
                 meet: frozenset[str] = frozenset()) -> None:
        self.scripts = scripts
        self.calls: list[tuple[str, dict]] = []
        self.barrier = barrier
        self.meet = meet  # agents that must be in flight at the same moment
        self._lock = threading.Lock()

    @staticmethod
    def who(system: str) -> str:
        for role in team.ROLES.values():
            if system.startswith(f"You are {role.name},"):
                return role.key
        return "chief"

    def stream(self, **kwargs: object) -> FakeStream:
        agent = self.who(str(kwargs["system"]))
        if self.barrier is not None and agent in self.meet and not any(a == agent for a, _ in self.calls):
            self.barrier.wait()  # raises BrokenBarrierError if the other agent never runs concurrently
        with self._lock:
            self.calls.append((agent, {**kwargs, "messages": list(kwargs["messages"])}))  # type: ignore[arg-type]
            return FakeStream(self.scripts[agent].pop(0))

    def requests(self, agent: str) -> list[dict]:
        return [kw for a, kw in self.calls if a == agent]


def chief(tmp_path: Path, fake: CrewMessages, approve=lambda _q: True, **kw: object) -> tuple[Jarvis, list[str]]:
    lines: list[str] = []
    jarvis = Jarvis(
        ctx=ToolContext(workspace=tmp_path, approve=approve),
        client=SimpleNamespace(beta=SimpleNamespace(messages=fake)),
        team_mode=True,
        on_text=lambda _t: None,
        on_tool=lines.append,
        **kw,
    )
    return jarvis, lines


def tool_names(jarvis: Jarvis) -> set[str]:
    return {str(s["name"]) for s in jarvis._tools}


def last_results(request: dict) -> list[dict]:
    return request["messages"][-1]["content"]


# ---- Roster and tool boundaries ------------------------------------------------------------


def test_team_has_six_specialists_with_distinct_names() -> None:
    assert len(team.ROLES) == 6
    assert [r.name for r in team.ROLES.values()] == ["Scout", "Architect", "Medic", "Forge", "Sentinel", "Herald"]
    assert all(r.tools for r in team.ROLES.values())


def test_chief_delegates_and_does_not_write_or_ship(tmp_path: Path) -> None:
    jarvis, _ = chief(tmp_path, CrewMessages({}))
    names = tool_names(jarvis)
    assert "delegate" in names and "read_file" in names and "remember" in names
    assert not names & {"write_file", "edit_file", "run_command", "commit_changes", "push_and_open_pr"}
    prompt = jarvis.system_prompt()
    assert "Team mode is on" in prompt and all(r.name in prompt for r in team.ROLES.values())
    assert "Autonomous team mode" not in prompt


def test_autonomous_chief_gets_the_team_playbook_not_the_solo_one(tmp_path: Path) -> None:
    jarvis, _ = chief(tmp_path, CrewMessages({}), autonomous=True)
    prompt = jarvis.system_prompt()
    assert "Autonomous team mode" in prompt and "1. Understand: pull the target" not in prompt


def test_specialist_tool_sets_follow_their_roles(tmp_path: Path) -> None:
    jarvis, _ = chief(tmp_path, CrewMessages({}))
    crew = jarvis.team
    assert crew is not None
    scout = tool_names(crew.member(team.ROLES["scout"]))
    forge = tool_names(crew.member(team.ROLES["forge"]))
    herald = tool_names(crew.member(team.ROLES["herald"]))
    assert scout == team.READ_REMOTE
    assert {"write_file", "run_command"} <= forge and not forge & team.SHIP
    assert team.SHIP <= herald and "run_command" not in herald
    for key, member in crew.members.items():
        assert "delegate" not in tool_names(member)  # only the chief delegates
        assert member.system_prompt().startswith(f"You are {team.ROLES[key].name}, the ")


def test_default_jarvis_is_unchanged(tmp_path: Path) -> None:
    solo = Jarvis(ctx=ToolContext(workspace=tmp_path, approve=lambda _q: True), client=object())
    assert solo.team is None and "delegate" not in tool_names(solo) and "commit_changes" in tool_names(solo)


# ---- Delegation -----------------------------------------------------------------------------


def test_read_only_specialists_run_in_parallel_and_reports_return_in_order(tmp_path: Path) -> None:
    fake = CrewMessages(
        {
            "chief": [
                tool_turn(delegate("d1", "scout", "Find rate limiters"), delegate("d2", "architect", "Plan acme/api")),
                text("Plan settled."),
            ],
            "scout": [text("Use a token bucket (octo/rl, MIT).")],
            "architect": [text("1. Add limiter.py")],
        },
        barrier=threading.Barrier(2, timeout=5),
        meet=frozenset({"scout", "architect"}),
    )
    jarvis, lines = chief(tmp_path, fake)

    assert jarvis.ask("Add rate limiting to acme/api") == "Plan settled."

    results = last_results(fake.requests("chief")[1])
    assert [r["tool_use_id"] for r in results] == ["d1", "d2"]
    assert "Scout report" in results[0]["content"] and "token bucket" in results[0]["content"]
    assert "Architect report" in results[1]["content"] and not results[1]["is_error"]
    # The specialist received the chief's assignment as its own user turn.
    assert fake.requests("scout")[0]["messages"][0]["content"] == "Find rate limiters"
    assert sum(line.startswith("delegate ") for line in lines) == 2


def test_specialist_cannot_use_tools_outside_its_role(tmp_path: Path) -> None:
    fake = CrewMessages(
        {
            "chief": [tool_turn(delegate("d1", "scout", "Patch it")), text("ok")],
            "scout": [
                tool_turn(("s1", "write_file", {"repo": "a/b", "path": "x", "content": "y"})),
                text("I can't write files; route to Forge."),
            ],
        }
    )
    jarvis, lines = chief(tmp_path, fake)
    jarvis.ask("go")
    refused = last_results(fake.requests("scout")[1])[0]
    assert refused["is_error"] and "not available" in refused["content"]
    assert any(line.startswith("Scout ▸ write_file") for line in lines)
    assert not (tmp_path / "a").exists()


@pytest.mark.parametrize(
    ("data", "error"),
    [
        ({"agent": "ghost", "task": "x"}, "unknown agent"),
        ({"agent": "scout", "task": "  "}, "non-empty"),
        ({"agent": "scout", "task": "x", "fresh": "yes"}, "boolean"),
        ({"agent": "scout", "task": "x", "extra": 1}, "unexpected field"),
        ("scout", "JSON object"),
    ],
)
def test_bad_delegations_are_reported_to_the_chief(tmp_path: Path, data: object, error: str) -> None:
    jarvis, _ = chief(tmp_path, CrewMessages({}))
    assert jarvis.team is not None
    content, is_error = jarvis.team.delegate(data)
    assert is_error and error in content


def test_specialist_api_failure_is_reported_not_raised(tmp_path: Path) -> None:
    class Broken(CrewMessages):
        def stream(self, **kwargs: object) -> FakeStream:
            if self.who(str(kwargs["system"])) == "medic":
                raise ConnectionError("network down")
            return super().stream(**kwargs)

    fake = Broken({"chief": [tool_turn(delegate("d1", "medic", "Check CI")), text("Medic is unreachable.")]})
    jarvis, _ = chief(tmp_path, fake)
    assert jarvis.ask("CI?") == "Medic is unreachable."
    result = last_results(fake.requests("chief")[1])[0]
    assert result["is_error"] and "network down" in result["content"]


def test_specialists_keep_context_until_fresh_or_reset(tmp_path: Path) -> None:
    fake = CrewMessages(
        {
            "chief": [
                tool_turn(delegate("d1", "architect", "Plan A")), text("a"),
                tool_turn(delegate("d2", "architect", "And B?")), text("b"),
                tool_turn(delegate("d3", "architect", "Start over", fresh=True)), text("c"),
            ],
            "architect": [text("plan A"), text("plan B"), text("plan C")],
        }
    )
    jarvis, _ = chief(tmp_path, fake)
    for prompt in ("1", "2", "3"):
        jarvis.ask(prompt)
    seen = [len(r["messages"]) for r in fake.requests("architect")]
    assert seen == [1, 3, 1]  # follow-up remembers; fresh=true starts over
    jarvis.reset()
    assert all(not m.messages for m in jarvis.team.members.values())  # type: ignore[union-attr]


def test_specialist_approvals_name_the_specialist(tmp_path: Path) -> None:
    asked: list[str] = []
    fake = CrewMessages(
        {
            "chief": [tool_turn(delegate("d1", "forge", "Build it")), text("done")],
            "forge": [
                tool_turn(("f1", "write_file", {"repo": "acme/app", "path": "a.txt", "content": "hi"})),
                text("Wrote a.txt"),
            ],
        }
    )
    (tmp_path / "acme" / "app").mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path / "acme" / "app", check=True)
    jarvis, _ = chief(tmp_path, fake, approve=lambda q: asked.append(q) or False)
    jarvis.ask("go")
    assert asked and asked[0].startswith("[Forge] ")
    assert not (tmp_path / "acme/app/a.txt").exists()  # declined


def test_web_style_approver_swap_reaches_specialists(tmp_path: Path) -> None:
    jarvis, _ = chief(tmp_path, CrewMessages({}), approve=lambda _q: False)
    forge = jarvis.team.member(team.ROLES["forge"])  # type: ignore[union-attr]
    jarvis.ctx.approve = lambda _q: True  # the web interface replaces the approver after start-up
    assert forge.ctx.approve("write?") is True


# ---- Quality gate ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("report", "expected"),
    [
        ("All good.\nVERDICT: PASS", "PASS"),
        ("Issues found.\n**VERDICT: FAIL**", "FAIL"),
        ("verdict: pass\nlater...\nVERDICT: FAIL", "FAIL"),
        ("I think it should PASS", None),
    ],
)
def test_verdict_parsing(report: str, expected: str | None) -> None:
    assert team.verdict(report) == expected


def herald_ships() -> list[SimpleNamespace]:
    return [
        tool_turn(("h1", "push_and_open_pr", {"repo": "acme/app", "title": "t", "body": "b"})),
        text("Tried to ship."),
    ]


def herald_result(fake: CrewMessages, index: int) -> dict:
    return last_results(fake.requests("herald")[index])[0]


def test_quality_gate_blocks_shipping_until_sentinel_passes(tmp_path: Path) -> None:
    fake = CrewMessages(
        {
            "chief": [
                tool_turn(delegate("c1", "forge", "Build")), text("built"),
                tool_turn(delegate("c2", "herald", "Ship")), text("blocked"),
                tool_turn(delegate("c3", "sentinel", "Verify")), text("failed"),
                tool_turn(delegate("c4", "herald", "Ship")), text("still blocked"),
                tool_turn(delegate("c5", "forge", "Fix")), tool_turn(delegate("c6", "sentinel", "Verify")), text("passed"),
                tool_turn(delegate("c7", "herald", "Ship")), text("shipped"),
            ],
            "forge": [text("Built it."), text("Fixed it.")],
            "sentinel": [text("Bug at a.py:3\nVERDICT: FAIL"), text("Clean.\nVERDICT: PASS")],
            "herald": herald_ships() + herald_ships() + herald_ships(),
        }
    )
    jarvis, _ = chief(tmp_path, fake)
    crew = jarvis.team
    assert crew is not None and crew.gate == team.CLEAN

    jarvis.ask("build")
    assert crew.gate == team.UNVERIFIED
    assert "Sentinel must pass" in last_results(fake.requests("chief")[1])[0]["content"]

    jarvis.ask("ship")
    blocked = herald_result(fake, 1)
    assert blocked["is_error"] and "Quality gate" in blocked["content"]

    jarvis.ask("verify")
    assert crew.gate == team.FAILED
    jarvis.ask("ship")
    assert "Sentinel failed" in herald_result(fake, 3)["content"]

    jarvis.ask("fix and verify")  # one chief turn: Forge fixes, then Sentinel passes it
    assert crew.gate == team.PASSED

    jarvis.ask("ship")
    allowed = herald_result(fake, 5)
    assert "Quality gate" not in allowed["content"]  # reaches the real tool (which fails: no such repo)
    assert crew.gate == team.CLEAN
    assert [k for k, _ in crew.history] == ["forge", "herald", "sentinel", "herald", "forge", "sentinel", "herald"]


def test_docs_only_work_ships_without_a_gate(tmp_path: Path) -> None:
    fake = CrewMessages({"chief": [tool_turn(delegate("c1", "herald", "Ship docs")), text("ok")], "herald": herald_ships()})
    jarvis, _ = chief(tmp_path, fake)
    jarvis.ask("ship the docs")
    assert "Quality gate" not in herald_result(fake, 1)["content"]


# ---- CLI ------------------------------------------------------------------------------------


def test_team_command_in_chat(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    jarvis, _ = chief(tmp_path, CrewMessages({}))
    replies = iter(["/team", "/exit"])
    assert cli.chat_loop(jarvis, None, tmp_path, read=lambda _p: next(replies)) == 0
    out = capsys.readouterr().out
    assert "/team" in out and "Quality gate: clean" in out
    assert all(r.name in out for r in team.ROLES.values())


def test_team_flag_and_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_run(args, io, listener, mcp):  # type: ignore[no-untyped-def]
        captured["team"] = args.team
        return 0

    monkeypatch.setattr(cli, "run", fake_run)
    cli.main(["--team", "--no-mcp", "--workspace", str(tmp_path / "repos"), "hi"])
    assert captured["team"] is True
    monkeypatch.setenv("JARVIS_TEAM", "1")
    cli.main(["--no-mcp", "--workspace", str(tmp_path / "repos"), "hi"])
    assert captured["team"] is True
