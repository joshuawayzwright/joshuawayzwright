"""Spending limit, run log viewer, and the files that let a phone add Jarvis to its home screen."""

from __future__ import annotations

import http.client
import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from jarvis import cli, icons, web
from jarvis.agent import Jarvis
from jarvis.dashboard import MAX_LOG_BYTES, Dashboard
from jarvis.tools import ToolContext
from test_voice import FakeStream


def usage(output_tokens: int) -> SimpleNamespace:
    return SimpleNamespace(input_tokens=0, output_tokens=output_tokens, cache_read_input_tokens=0,
                           cache_creation_input_tokens=0)


def tool_step(i: int, output_tokens: int) -> SimpleNamespace:
    call = SimpleNamespace(type="tool_use", id=f"t{i}", name="list_local_repos", input={})
    return SimpleNamespace(stop_reason="tool_use", content=[call], usage=usage(output_tokens))


def budgeted(tmp_path: Path, responses: list, budget: float | None) -> tuple[Jarvis, list[str], list[dict]]:
    calls: list[dict] = []
    notices: list[str] = []
    messages = SimpleNamespace(stream=lambda **kw: (calls.append(kw), FakeStream(responses.pop(0)))[1])
    jarvis = Jarvis(ctx=ToolContext(workspace=tmp_path, approve=lambda q: False),
                    client=SimpleNamespace(beta=SimpleNamespace(messages=messages)),
                    on_text=lambda t: None, on_tool=lambda t: None, on_notice=notices.append, budget_usd=budget)
    return jarvis, notices, calls


def test_budget_warns_then_stops_and_rolls_back_the_unfinished_turn(tmp_path: Path) -> None:
    # Opus 5.5 output costs $20 per million tokens: 45,000 tokens = $0.90, 60,000 more = $2.10 in total.
    responses = [SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text="Hello")], usage=usage(45_000)),
                 tool_step(1, 60_000), tool_step(2, 1)]
    jarvis, notices, calls = budgeted(tmp_path, responses, budget=1.00)
    assert jarvis.ask("hi") == "Hello"
    assert notices == []  # warnings happen before a request, once the session is near the limit
    assert len(jarvis.messages) == 2

    jarvis.ask("list my repos")
    assert len(calls) == 2  # the warning let one more request through; then the limit stopped the turn
    assert "Heads up" in notices[0] and "$0.90 of its $1.00" in notices[0]
    assert "Stopped" in notices[1] and "$1.00 spending limit" in notices[1]
    assert len(jarvis.messages) == 2  # the unfinished turn was rolled back; the conversation stays valid
    assert jarvis.over_budget()

    jarvis.ask("anything else")  # already over: refused without calling the API
    assert len(calls) == 2 and "Stopped" in notices[-1]


def test_no_budget_means_no_limit_and_unknown_models_cannot_have_one(tmp_path: Path) -> None:
    jarvis, notices, _ = budgeted(tmp_path, [tool_step(1, 10_000_000), SimpleNamespace(
        stop_reason="end_turn", content=[], usage=usage(0))], budget=None)
    jarvis.ask("go")
    assert notices == [] and not jarvis.over_budget() and jarvis.cost_usd() == pytest.approx(200)
    with pytest.raises(ValueError, match="No price is known"):
        Jarvis(ctx=ToolContext(workspace=tmp_path, approve=lambda q: False), client=SimpleNamespace(),
               model="claude-something-else", budget_usd=5)


def test_run_status_records_a_budget_stop(tmp_path: Path) -> None:
    jarvis, _, _ = budgeted(tmp_path, [], budget=0.5)
    jarvis.usage["output_tokens"] = 1_000_000
    log = cli.RunLog(tmp_path / "runs", jarvis)
    log.goal("Big refactor")
    log.finish(True, "")
    assert json.loads(log.summary_path.read_text())["status"] == "over budget"


def test_cli_rejects_a_non_positive_budget() -> None:
    with pytest.raises(SystemExit):
        cli.main(["--budget", "0", "hi"])


def test_read_run_log_only_serves_logs_in_the_runs_folder(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    runs.mkdir()
    (runs / "20261118-0900.md").write_text("# Jarvis run\n\n## Goal\n\nFix CI\n")
    (runs / "big.md").write_text("x" * (MAX_LOG_BYTES + 10) + "THE END")
    (tmp_path / "secret.md").write_text("private")
    dash = Dashboard(SimpleNamespace(), runs_dir=runs)  # type: ignore[arg-type]
    log = dash.read_run_log("20261118-0900.md")
    assert log == {"name": "20261118-0900.md", "text": "# Jarvis run\n\n## Goal\n\nFix CI\n", "truncated": False}
    big = dash.read_run_log("big.md")
    assert big["truncated"] and big["text"].endswith("THE END") and len(big["text"]) == MAX_LOG_BYTES
    for bad in ["../secret.md", "..%2Fsecret.md", "sub/x.md", "20261118-0900.json", "missing.md", "", ".md"]:
        assert dash.read_run_log(bad) is None, bad
    assert Dashboard(SimpleNamespace()).read_run_log("20261118-0900.md") is None  # type: ignore[arg-type]


def test_icons_are_valid_pngs() -> None:
    for size in (180, 192):
        data = icons.png(size)
        assert data.startswith(b"\x89PNG\r\n\x1a\n")
        width, height = int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
        assert (width, height) == (size, size)


@pytest.fixture
def app(tmp_path: Path):
    runs = tmp_path / "runs"
    runs.mkdir()
    (runs / "20261118-0900.md").write_text("# Jarvis run\n")
    jarvis = Jarvis(ctx=ToolContext(workspace=tmp_path, approve=lambda q: False), client=SimpleNamespace(), budget_usd=3)
    session = web.WebSession(jarvis)
    httpd, token = web.serve(session, "127.0.0.1", 0, dashboard=Dashboard(jarvis, runs_dir=runs))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield SimpleNamespace(port=httpd.server_address[1], token=token, session=session)
    httpd.shutdown()


def get(port: int, path: str, token: str | None = None) -> http.client.HTTPResponse:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request("GET", path, headers={"X-Jarvis-Token": token} if token else {})
    return conn.getresponse()


def test_web_routes_for_logs_manifest_and_icons(app) -> None:
    assert get(app.port, "/api/runs/20261118-0900.md").status == 401
    res = get(app.port, "/api/runs/20261118-0900.md", app.token)
    assert res.status == 200 and json.loads(res.read())["text"] == "# Jarvis run\n"
    assert get(app.port, "/api/runs/..%2F..%2Fetc%2Fpasswd", app.token).status == 404

    assert get(app.port, "/manifest.webmanifest").status == 401
    manifest = get(app.port, f"/manifest.webmanifest?token={app.token}")
    assert manifest.getheader("Content-Type") == "application/manifest+json"
    data = json.loads(manifest.read())
    assert data["start_url"] == f"/dashboard?token={app.token}" and data["display"] == "standalone"

    icon = get(app.port, "/icon-192.png")  # public: phones fetch icons without the token
    assert icon.status == 200 and icon.getheader("Content-Type") == "image/png" and icon.read().startswith(b"\x89PNG")
    assert get(app.port, "/icon.svg").read().startswith(b"<svg")
    page = get(app.port, f"/dashboard?token={app.token}").read()
    assert b'rel="apple-touch-icon"' in page and b"manifest.webmanifest" in page

    snap = json.loads(get(app.port, "/api/dashboard", app.token).read())
    assert snap["session"]["budget_usd"] == 3


def test_notices_reach_the_browser_and_the_activity_feed(app) -> None:
    import queue
    app.session.events = queue.Queue()
    app.session.jarvis._notice("[Stopped: limit]")
    assert app.session.events.get_nowait() == {"type": "notice", "text": "[Stopped: limit]"}
    assert app.session.recent_activity()[0]["kind"] == "notice"
