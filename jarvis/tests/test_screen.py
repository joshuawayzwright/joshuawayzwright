"""Screen vision: capture, downscale, encode, approval, and passing images to Claude."""

from __future__ import annotations

import base64
import io
from pathlib import Path
from types import SimpleNamespace

import pytest

from jarvis import screen
from jarvis.agent import Jarvis
from jarvis.tools import ToolContext, execute
from test_voice import FakeMessages

Image = pytest.importorskip("PIL.Image")


def test_encode_downscales_large_screens() -> None:
    data, media_type, size = screen.encode(Image.new("RGB", (3840, 2160), "white"))
    assert media_type == "image/png" and size == (1568, 882)
    assert Image.open(io.BytesIO(base64.b64decode(data))).size == (1568, 882)


def test_encode_falls_back_to_jpeg_for_busy_screens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(screen, "MAX_BYTES", 10)
    _, media_type, _ = screen.encode(Image.new("RGB", (100, 100), "red"))
    assert media_type == "image/jpeg"


def test_look_at_screen_needs_approval(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(screen, "_grab", lambda monitor: Image.new("RGB", (800, 600), "blue"))
    asked: list[str] = []
    out, err = execute(ToolContext(workspace=Path("."), approve=lambda q: asked.append(q) or True), "look_at_screen", {})
    assert not err and [b["type"] for b in out] == ["image", "text"] and asked
    assert out[0]["source"]["media_type"] == "image/png" and "800x600" in out[1]["text"]
    out, err = execute(ToolContext(workspace=Path("."), approve=lambda q: False), "look_at_screen", {"monitor": 2})
    assert out == "The user declined the screenshot." and not err


def test_screenshots_ask_even_when_tools_are_auto_approved(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(screen, "_grab", lambda monitor: Image.new("RGB", (10, 10)))
    ctx = ToolContext(workspace=Path("."), approve=lambda q: True, confirm_private=lambda q: False)
    assert execute(ctx, "look_at_screen", {}) == ("The user declined the screenshot.", False)


def test_capture_errors_are_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_display(monitor: int):
        raise screen.ScreenUnavailable("Couldn't capture the screen: no display")

    monkeypatch.setattr(screen, "_grab", no_display)
    out, err = execute(ToolContext(workspace=Path("."), approve=lambda q: True), "look_at_screen", {})
    assert err and "no display" in out


def test_screenshot_reaches_claude_as_an_image_block(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(screen, "_grab", lambda monitor: Image.new("RGB", (64, 64), "red"))
    tool_call = SimpleNamespace(type="tool_use", id="t1", name="look_at_screen", input={})
    fake = FakeMessages([])
    fake.replies = [None, "I can see a red square."]  # first reply replaced below by a tool call
    responses = [SimpleNamespace(stop_reason="tool_use", content=[tool_call]),
                 SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text="I can see a red square.")])]
    fake.create = lambda **kw: (fake.calls.append({**kw, "messages": list(kw["messages"])}), responses.pop(0))[1]
    jarvis = Jarvis(ctx=ToolContext(workspace=tmp_path, approve=lambda q: True),
                    client=SimpleNamespace(beta=SimpleNamespace(messages=fake)), on_text=lambda _t: None, on_tool=lambda _l: None)

    assert jarvis.ask("what's on my screen?") == "I can see a red square."
    result = fake.calls[1]["messages"][-1]["content"][0]
    assert result["type"] == "tool_result" and result["content"][0]["type"] == "image"
