"""Web interface: token auth, streamed turns, approvals in the browser, one turn at a time."""

from __future__ import annotations

import http.client
import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from jarvis import web
from jarvis.agent import Jarvis
from jarvis.tools import ToolContext
from test_voice import FakeMessages


def tool_then_text(path: str, text: str) -> list:
    call = SimpleNamespace(type="tool_use", id="w1", name="write_file", input={"repo": "acme/rocket", "path": path, "content": "hi"})
    return [SimpleNamespace(stop_reason="tool_use", content=[SimpleNamespace(type="text", text="Writing it."), call]),
            SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=text)])]


@pytest.fixture
def server(tmp_path: Path):
    (tmp_path / "acme" / "rocket" / ".git").mkdir(parents=True)
    fake = FakeMessages([])
    responses: list = []
    fake.create = lambda **kw: (fake.calls.append(kw), responses.pop(0))[1]
    jarvis = Jarvis(ctx=ToolContext(workspace=tmp_path, approve=lambda q: False),
                    client=SimpleNamespace(beta=SimpleNamespace(messages=fake)))
    session = web.WebSession(jarvis)
    httpd, token = web.serve(session, "127.0.0.1", 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield SimpleNamespace(port=httpd.server_address[1], token=token, responses=responses, root=tmp_path, session=session)
    httpd.shutdown()


def post(port: int, path: str, body: dict, token: str | None) -> http.client.HTTPResponse:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Jarvis-Token"] = token
    conn.request("POST", path, json.dumps(body), headers)
    return conn.getresponse()


def test_requires_the_token(server) -> None:
    assert post(server.port, "/api/chat", {"message": "hi"}, None).status == 401
    assert post(server.port, "/api/chat", {"message": "hi"}, "wrong").status == 401
    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=10)
    conn.request("GET", "/")
    assert conn.getresponse().status == 401
    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=10)
    conn.request("GET", f"/?token={server.token}")
    page = conn.getresponse()
    assert page.status == 200 and b"<title>Jarvis</title>" in page.read()
    assert page.getheader("Referrer-Policy") == "no-referrer"


def test_streamed_turn_with_approval_from_the_browser(server) -> None:
    server.responses.extend(tool_then_text("notes.txt", "Done, sir."))
    res = post(server.port, "/api/chat", {"message": "write a note"}, server.token)
    assert res.status == 200 and res.getheader("Content-Type") == "application/x-ndjson"
    events = []
    for line in res:
        event = json.loads(line)
        events.append(event)
        if event["type"] == "approval":
            assert "notes.txt" in event["question"]
            # A second request while the turn runs is refused...
            assert post(server.port, "/api/chat", {"message": "again"}, server.token).status == 409
            # ...and the approval arrives on its own connection, like a browser button click.
            assert post(server.port, "/api/approve", {"id": event["id"], "approved": True}, server.token).status == 200
    kinds = [e["type"] for e in events]
    assert kinds[0] == "delta" and "approval" in kinds and "tool" in kinds and kinds[-1] == "done"
    assert "".join(e["text"] for e in events if e["type"] == "delta") == "Writing it.Done, sir."
    assert events[-1]["reply"] == "Done, sir."
    assert (server.root / "acme/rocket/notes.txt").read_text() == "hi"  # approved write happened


def test_declined_approval_and_reset(server) -> None:
    server.responses.extend(tool_then_text("nope.txt", "Understood."))
    res = post(server.port, "/api/chat", {"message": "write"}, server.token)
    for line in res:
        event = json.loads(line)
        if event["type"] == "approval":
            post(server.port, "/api/approve", {"id": event["id"], "approved": False}, server.token)
    assert not (server.root / "acme/rocket/nope.txt").exists()
    assert post(server.port, "/api/approve", {"id": "unknown", "approved": True}, server.token).status == 404
    assert post(server.port, "/api/reset", {}, server.token).status == 200
    assert server.session.jarvis.messages == []


def test_bad_requests(server) -> None:
    assert post(server.port, "/api/chat", {"message": "  "}, server.token).status == 400
    assert post(server.port, "/api/nothing", {}, server.token).status == 404


def test_auto_approve_still_asks_for_screenshots(tmp_path: Path) -> None:
    jarvis = Jarvis(ctx=ToolContext(workspace=tmp_path, approve=lambda q: False), client=SimpleNamespace())
    session = web.WebSession(jarvis, auto_approve=True)
    assert session.approve_tool("Run tests?") is True
    assert session.confirm_private("Take a screenshot?") is False  # no browser attached: declined
