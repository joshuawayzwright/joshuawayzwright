"""Sandboxed run_command: flags and failure handling offline, and real containers when Docker is available."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from jarvis import sandbox, team
from jarvis.agent import Jarvis
from jarvis.tools import ToolContext, execute
from test_team import CrewMessages, delegate, text, tool_turn

TEST_IMAGE = "busybox:1.37"


def make_repo(root: Path) -> Path:
    repo = root / "acme" / "app"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    return repo


class FakeRunner:
    def __init__(self, results: list[object]) -> None:
        self.results = results
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str], **kwargs: object) -> object:
        self.calls.append(args)
        result = self.results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


def done(code: int = 0, out: str = "", err: str = "") -> SimpleNamespace:
    return SimpleNamespace(returncode=code, stdout=out, stderr=err)


# ---- Offline -------------------------------------------------------------------------------


def test_container_is_locked_down(tmp_path: Path) -> None:
    box = sandbox.Sandbox(home_root=tmp_path / "homes", network="none")
    args = box.command_line(tmp_path / "repo", "acme/app", "make test", "jarvis-x")
    joined = " ".join(args)
    for flag in ("--rm", "--cap-drop ALL", "--security-opt no-new-privileges", "--network none",
                 "--pids-limit 512", "--memory 4g", "-w /work", "-e HOME=/home/jarvis", "--init"):
        assert flag in joined, flag
    assert args[-4:] == [sandbox.DEFAULT_IMAGE, "sh", "-c", "make test"]
    assert f"{(tmp_path / 'homes' / 'acme__app').resolve()}:/home/jarvis" in args
    assert "-e" in args and not any(a.startswith(("GITHUB_TOKEN", "ANTHROPIC_API_KEY")) for a in args)
    if hasattr(os, "getuid"):
        assert f"{os.getuid()}:{os.getgid()}" in args


@pytest.mark.parametrize(("kwargs", "error"), [({"network": "host"}, "Unknown sandbox network"),
                                               ({"image": "evil; rm -rf /"}, "not a valid image")])
def test_bad_settings_are_refused(tmp_path: Path, kwargs: dict, error: str) -> None:
    with pytest.raises(sandbox.SandboxError, match=error):
        sandbox.Sandbox(home_root=tmp_path, **kwargs)


def test_timeout_kills_the_container(tmp_path: Path) -> None:
    runner = FakeRunner([subprocess.TimeoutExpired("docker", 10), done()])
    box = sandbox.Sandbox(home_root=tmp_path, runner=runner)
    with pytest.raises(subprocess.TimeoutExpired):
        box.run(tmp_path, "acme/app", "sleep 99", timeout=10)
    name = runner.calls[0][runner.calls[0].index("--name") + 1]
    assert runner.calls[1] == ["docker", "kill", name]


def test_check_reports_missing_docker_and_pulls_missing_images(tmp_path: Path) -> None:
    with pytest.raises(sandbox.SandboxError, match="isn't available"):
        sandbox.Sandbox(home_root=tmp_path, runner=FakeRunner([FileNotFoundError("docker")])).check()
    with pytest.raises(sandbox.SandboxError, match="isn't running"):
        sandbox.Sandbox(home_root=tmp_path, runner=FakeRunner([done(1, err="Cannot connect")])).check()
    runner = FakeRunner([done(0, "29.9"), done(1), done(0)])
    assert "Docker 29.9" in sandbox.Sandbox(home_root=tmp_path, runner=runner).check()
    assert runner.calls[2][:2] == ["docker", "pull"]
    with pytest.raises(sandbox.SandboxError, match="Couldn't pull"):
        sandbox.Sandbox(home_root=tmp_path, runner=FakeRunner([done(0, "29"), done(1), done(1, err="denied")])).check()


def test_run_command_goes_through_the_sandbox_and_says_so(tmp_path: Path) -> None:
    make_repo(tmp_path)
    runner = FakeRunner([done(3, "boxed", "")])
    asked: list[str] = []
    ctx = ToolContext(workspace=tmp_path, approve=lambda q: asked.append(q) or True,
                      sandbox=sandbox.Sandbox(home_root=tmp_path / "h", runner=runner))
    out, err = execute(ctx, "run_command", {"repo": "acme/app", "command": "make"})
    assert not err and out.startswith("exit code 3") and "boxed" in out
    assert asked == [f"Run in acme/app (sandbox: {sandbox.DEFAULT_IMAGE}): make"]
    assert runner.calls[0][:2] == ["docker", "run"]
    out, err = execute(ctx, "run_command", {"repo": "acme/app", "command": "sudo rm -rf /"})
    assert err and "Blocked" in out and len(runner.calls) == 1  # the host-side guard still applies first


def test_specialists_inherit_the_sandbox(tmp_path: Path) -> None:
    box = sandbox.Sandbox(home_root=tmp_path / "h")
    jarvis = Jarvis(ctx=ToolContext(workspace=tmp_path, approve=lambda _q: True, sandbox=box),
                    client=SimpleNamespace(beta=SimpleNamespace(messages=CrewMessages({}))), team_mode=True)
    for role in team.ROLES.values():
        assert jarvis.team.member(role).ctx.sandbox is box  # type: ignore[union-attr]


# ---- Real containers ---------------------------------------------------------------------------


def docker_ready() -> bool:
    if not shutil.which("docker"):
        return False
    try:
        info = subprocess.run(["docker", "info"], capture_output=True, timeout=20)
        image = subprocess.run(["docker", "image", "inspect", TEST_IMAGE], capture_output=True, timeout=20)
        if info.returncode == 0 and image.returncode != 0:
            image = subprocess.run(["docker", "pull", "-q", TEST_IMAGE], capture_output=True, timeout=300)
        return info.returncode == 0 and image.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


needs_docker = pytest.mark.skipif(not docker_ready(), reason="Docker isn't available")


@needs_docker
def test_real_container_isolation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = make_repo(tmp_path)
    (repo / "in.txt").write_text("from host")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_should_not_leak")
    box = sandbox.Sandbox(home_root=tmp_path / "homes", image=TEST_IMAGE, network="none")
    ctx = ToolContext(workspace=tmp_path, approve=lambda _q: True, sandbox=box)

    script = ('cat in.txt; echo made > out.txt; echo "token=[$GITHUB_TOKEN]"; echo "home=$HOME"; '
              'echo cache > $HOME/c.txt; ls /root 2>&1 | head -1; wget -q -T 3 -O- http://1.1.1.1 >/dev/null 2>&1 && echo NET || echo NONET; exit 4')
    out, err = execute(ctx, "run_command", {"repo": "acme/app", "command": script})
    assert not err, out
    assert out.startswith("exit code 4") and "from host" in out
    assert "token=[]" in out and "home=/home/jarvis" in out and "NONET" in out
    assert (repo / "out.txt").read_text().strip() == "made"
    assert (tmp_path / "homes" / "acme__app" / "c.txt").exists()  # the per-repo home persists between commands
    if hasattr(os, "getuid"):
        assert (repo / "out.txt").stat().st_uid == os.getuid()  # files belong to the user, not root


@needs_docker
def test_real_timeout_leaves_no_container(tmp_path: Path) -> None:
    make_repo(tmp_path)
    box = sandbox.Sandbox(home_root=tmp_path / "homes", image=TEST_IMAGE, network="none")
    ctx = ToolContext(workspace=tmp_path, approve=lambda _q: True, sandbox=box)
    out, _ = execute(ctx, "run_command", {"repo": "acme/app", "command": "sleep 60", "timeout_seconds": 10})
    assert "timed out after 10 seconds" in out
    listing = subprocess.run(["docker", "ps", "-q", "--filter", "name=jarvis-"], capture_output=True, text=True)
    assert listing.stdout.strip() == ""
