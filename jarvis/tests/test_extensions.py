"""Tests for long-term memory and MCP server support."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

from fakes import stream_from

import pytest

from jarvis import mcp_bridge
from jarvis.agent import Jarvis
from jarvis.memory import Memory
from jarvis.tools import ToolContext, execute

FIXTURES = Path(__file__).parent / "fixtures"


# ---- Memory -------------------------------------------------------------------------------


def test_memory_remember_forget_and_prompt(tmp_path: Path) -> None:
    memory = Memory(tmp_path / "memory.md")
    c = ToolContext(workspace=tmp_path, approve=lambda _q: True, memory=memory)

    assert execute(c, "remember", {"note": "Prefers  pytest\nover unittest"})[0].startswith("Remembered")
    assert execute(c, "remember", {"note": "Main site repo: joshuawayzwright/wrightwayz-website"})[0].startswith("Remembered")
    assert execute(c, "remember", {"note": "prefers pytest"})[0] == "Already remembered."
    assert len(memory.notes()) == 2 and memory.notes()[0].startswith("Prefers pytest over unittest (")

    section = memory.prompt_section()
    assert "earlier sessions" in section and "wrightwayz-website" in section

    out, _ = execute(c, "forget", {"text": "pytest"})
    assert out.startswith("Forgot") and len(memory.notes()) == 1
    assert "No note contains" in execute(c, "forget", {"text": "nothing like this"})[0]


def test_memory_file_is_human_editable(tmp_path: Path) -> None:
    path = tmp_path / "memory.md"
    path.write_text("# My notes\n\nsome prose\n- Uses Vercel for hosting\n-\n")
    assert Memory(path).notes() == ["Uses Vercel for hosting"]


def test_memory_off(tmp_path: Path) -> None:
    out, err = execute(ToolContext(workspace=tmp_path, approve=lambda _q: True), "remember", {"note": "x"})
    assert err and "turned off" in out


def test_memory_is_loaded_into_system_prompt_once(tmp_path: Path) -> None:
    memory = Memory(tmp_path / "memory.md")
    memory.remember("Deploys with Vercel")
    calls: list[dict] = []
    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(stream=stream_from(lambda **kw: (
        calls.append(kw), SimpleNamespace(stop_reason="end_turn", content=[]))[1]))))
    jarvis = Jarvis(ctx=ToolContext(workspace=tmp_path, approve=lambda _q: True, memory=memory), client=client, on_text=lambda _t: None)
    memory.remember("Added mid-session")
    jarvis.ask("hi")
    assert "Deploys with Vercel" in calls[0]["system"]
    assert "Added mid-session" not in calls[0]["system"]  # stable prompt prefix for caching


# ---- MCP config and results ---------------------------------------------------------------


def test_load_config_standard_format(tmp_path: Path) -> None:
    path = tmp_path / "mcp.json"
    path.write_text(json.dumps({"mcpServers": {
        "playwright": {"command": "npx", "args": ["@playwright/mcp@latest"]},
        "docs": {"command": "npx", "args": ["-y", "@upstash/context7-mcp"], "env": {"X": "1"}},
        "off": {"command": "x", "disabled": True},
        "hosted": {"url": "https://example.com/mcp"},
        "bad name!": {"command": "x"},
    }}))
    servers, warnings = mcp_bridge.load_config(path)
    assert [s.name for s in servers] == ["playwright", "docs", "hosted"]
    assert servers[1].env == {"X": "1"} and servers[2].url == "https://example.com/mcp"
    assert len(warnings) == 1  # only the invalid name
    assert mcp_bridge.load_config(tmp_path / "missing.json") == ([], [])
    (tmp_path / "broken.json").write_text("{nope")
    with pytest.raises(mcp_bridge.MCPUnavailable):
        mcp_bridge.load_config(tmp_path / "broken.json")


def test_tool_names_are_api_safe() -> None:
    assert mcp_bridge.tool_name("browser", "navigate.to") == "mcp__browser__navigate_to"
    assert len(mcp_bridge.tool_name("s" * 30, "t" * 80)) == 64


def test_format_result_handles_sdk_1_and_2_shapes() -> None:
    text = SimpleNamespace(type="text", text="hello")
    image = SimpleNamespace(type="image", mime_type="image/png")
    assert mcp_bridge.format_result(SimpleNamespace(content=[text, image], is_error=False)) == ("hello\n[image: image/png]", False)
    v1 = SimpleNamespace(content=[], structuredContent={"a": 1}, isError=True)
    out, err = mcp_bridge.format_result(v1)
    assert err and json.loads(out) == {"a": 1}


# ---- Agent dispatch to MCP tools ------------------------------------------------------------


class FakeMCP:
    def __init__(self) -> None:
        self.called: list[tuple[str, dict]] = []

    def schemas(self) -> list[dict]:
        return [{"name": "mcp__web__read", "description": "", "input_schema": {"type": "object"}},
                {"name": "mcp__web__click", "description": "", "input_schema": {"type": "object"}}]

    def handles(self, name: str) -> bool:
        return name.startswith("mcp__")

    def is_read_only(self, name: str) -> bool:
        return name == "mcp__web__read"

    def call(self, name: str, args: dict) -> tuple[str, bool]:
        self.called.append((name, args))
        return f"ran {name}", False


def test_mcp_tools_are_offered_and_side_effects_need_approval(tmp_path: Path) -> None:
    mcp = FakeMCP()
    asked: list[str] = []
    ctx = ToolContext(workspace=tmp_path, approve=lambda q: asked.append(q) or False)
    jarvis = Jarvis(ctx=ctx, client=SimpleNamespace(), mcp=mcp, on_text=lambda _t: None)

    assert {"mcp__web__read", "mcp__web__click"} <= {t["name"] for t in jarvis._tools}
    assert jarvis._dispatch("mcp__web__read", {"url": "x"}) == ("ran mcp__web__read", False)  # read-only: no prompt
    assert jarvis._dispatch("mcp__web__click", {"ref": "b1"}) == ("The user declined this tool call.", False)
    assert len(asked) == 1 and "mcp__web__click" in asked[0]
    assert mcp.called == [("mcp__web__read", {"url": "x"})]


# ---- A real MCP server over stdio -----------------------------------------------------------


def test_real_mcp_server_round_trip(tmp_path: Path) -> None:
    pytest.importorskip("mcp.server.mcpserver")  # MCP Python SDK 2.x
    server = mcp_bridge.ServerConfig("echo", sys.executable, [str(FIXTURES / "echo_mcp_server.py")])
    broken = mcp_bridge.ServerConfig("broken", "definitely-not-a-command-jarvis")
    manager = mcp_bridge.MCPManager([server, broken], log_dir=tmp_path / "logs")
    manager.start()
    try:
        assert len(manager.errors) == 1 and "broken" in manager.errors[0]
        assert manager.summary() == "echo (2 tools)"
        assert manager.is_read_only("mcp__echo__shout") and not manager.is_read_only("mcp__echo__fail")
        assert manager.call("mcp__echo__shout", {"text": "next level"}) == ("NEXT LEVEL", False)
        out, err = manager.call("mcp__echo__fail", {"reason": "boom"})
        assert err and "fail" in out
    finally:
        manager.close()
    assert "boom" in (tmp_path / "logs" / "mcp-echo.log").read_text()  # tracebacks go to the log, not the terminal


# ---- Remote MCP servers ----------------------------------------------------------------------


def test_load_config_remote_servers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENTRY_TOKEN", "abc")
    monkeypatch.delenv("MISSING_TOKEN", raising=False)
    path = tmp_path / "mcp.json"
    path.write_text(json.dumps({"mcpServers": {
        "sentry": {"type": "http", "url": "https://mcp.sentry.dev/mcp", "headers": {"Authorization": "Bearer ${SENTRY_TOKEN}"}},
        "local": {"url": "http://localhost:8080/mcp"},
        "insecure": {"url": "http://example.com/mcp"},
        "legacy": {"type": "sse", "url": "https://example.com/sse"},
        "nokey": {"url": "https://example.com/mcp", "headers": {"Authorization": "Bearer ${MISSING_TOKEN}"}},
        "neither": {"args": []},
    }}))
    servers, warnings = mcp_bridge.load_config(path)
    assert [s.name for s in servers] == ["sentry", "local"]
    assert servers[0].headers == {"Authorization": "Bearer abc"} and servers[0].url == "https://mcp.sentry.dev/mcp"
    joined = " ".join(warnings)
    assert "https://" in joined and "SSE" in joined and "MISSING_TOKEN is not set" in joined and "command or a url" in joined


def _free_port() -> int:
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_real_remote_mcp_server_with_auth_header(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("mcp.server.mcpserver")
    pytest.importorskip("uvicorn")
    import socket
    import subprocess
    import time

    port = _free_port()
    proc = subprocess.Popen([sys.executable, str(FIXTURES / "http_mcp_server.py"), str(port), "s3cret"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.1)
        monkeypatch.setenv("JARVIS_TEST_TOKEN", "s3cret")
        config = tmp_path / "mcp.json"
        config.write_text(json.dumps({"mcpServers": {
            "remote": {"url": f"http://127.0.0.1:{port}/mcp", "headers": {"Authorization": "Bearer ${JARVIS_TEST_TOKEN}"}},
            "wrongkey": {"url": f"http://127.0.0.1:{port}/mcp", "headers": {"Authorization": "Bearer nope"}},
        }}))
        servers, _ = mcp_bridge.load_config(config)
        manager = mcp_bridge.MCPManager(servers, log_dir=tmp_path / "logs")
        manager.start()
        try:
            assert manager.summary() == "remote (1 tools)"
            assert manager.call("mcp__remote__shout", {"text": "over http"}) == ("OVER HTTP", False)
            assert len(manager.errors) == 1 and "wrongkey" in manager.errors[0]  # bad token is rejected
        finally:
            manager.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)
