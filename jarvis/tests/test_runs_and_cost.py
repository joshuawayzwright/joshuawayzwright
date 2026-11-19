"""Cost estimates, run summaries written by RunLog, and the dashboard's run history."""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from jarvis import cli, pricing
from jarvis.dashboard import Dashboard
from test_dashboard import make_jarvis


def test_estimate_cost_uses_list_prices() -> None:
    usage = {"input_tokens": 1_000_000, "output_tokens": 100_000, "cache_read_input_tokens": 2_000_000,
             "cache_creation_input_tokens": 200_000, "requests": 9}
    # Opus 5.5: $4 in, $20 out, $0.20 cache read, $5 cache write per million tokens.
    assert pricing.estimate_cost("claude-opus-5-5", usage) == pytest.approx(4 + 2 + 0.4 + 1)
    assert pricing.estimate_cost("claude-sonnet-5-5", {"output_tokens": 1_000_000}) == pytest.approx(10)
    assert pricing.estimate_cost("claude-unknown", usage) is None
    assert pricing.estimate_cost("claude-opus-5-5", {}) == 0


def test_run_log_writes_a_summary_with_pull_requests_and_cost(tmp_path: Path) -> None:
    jarvis = make_jarvis(tmp_path)
    jarvis.usage["output_tokens"] = 500  # from before the run: not counted
    log = cli.RunLog(tmp_path / "runs", jarvis)
    assert list((tmp_path / "runs").glob("*.json")) == []  # no goal yet, nothing listed
    log.goal("Fix CI on acme/rocket")
    log.tool("get_ci_failure repo=acme/rocket")
    log.result("get_ci_failure", "Error: boom", True)
    log.tool("push_and_open_pr repo=acme/rocket")
    log.result("push_and_open_pr", "Opened draft PR #7: https://github.com/acme/rocket/pull/7", False)
    summary = json.loads(log.summary_path.read_text())
    assert summary["status"] == "running" and summary["steps"] == 2 and summary["errors"] == 1
    assert summary["pull_requests"] == ["https://github.com/acme/rocket/pull/7"]

    jarvis.usage["output_tokens"] += 1_000_000
    log.finish(True, "Done. See https://github.com/acme/rocket/pull/7 and https://github.com/acme/rocket/pull/8")
    summary = json.loads(log.summary_path.read_text())
    assert summary["status"] == "done" and summary["model"] == "claude-opus-5-5"
    assert summary["usage"]["output_tokens"] == 1_000_000 and summary["cost_usd"] == pytest.approx(20)
    assert summary["pull_requests"][-1].endswith("/pull/8") and len(summary["pull_requests"]) == 2
    assert "## Outcome" in log.path.read_text()

    first = log.path
    log.goal("Second fix")  # a new goal in the same session gets its own files
    assert log.path != first and json.loads(log.summary_path.read_text())["goal"] == "Second fix"
    log.finish(False)
    assert json.loads(log.summary_path.read_text())["status"] == "failed"


def test_dashboard_lists_recent_runs_newest_first(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    runs.mkdir()
    for i in range(12):
        path = runs / f"2026111{i:02d}.json"
        path.write_text(json.dumps({"goal": f"goal {i}", "status": "done", "started": i, "steps": i,
                                    "pull_requests": ["https://github.com/a/b/pull/1", 5], "cost_usd": 0.5}))

        os.utime(path, (i, i))
    (runs / "broken.json").write_text("{not json")
    dash = Dashboard(make_jarvis(tmp_path), runs_dir=runs)
    listed = dash.snapshot()["runs"]
    assert len(listed) == 10 and listed[0]["goal"] == "goal 11" and listed[-1]["goal"] == "goal 2"
    assert listed[0]["pull_requests"] == ["https://github.com/a/b/pull/1"]  # non-strings dropped
    assert listed[0]["log"] == "202611111.md"
    assert Dashboard(make_jarvis(tmp_path)).snapshot()["runs"] == []
    assert Dashboard(make_jarvis(tmp_path), runs_dir=tmp_path / "missing").snapshot()["runs"] == []


def test_session_cost_in_snapshot(tmp_path: Path) -> None:
    jarvis = make_jarvis(tmp_path)
    jarvis._add_usage(SimpleNamespace(input_tokens=1_000_000, output_tokens=0, cache_read_input_tokens=0,
                                      cache_creation_input_tokens=0))
    assert Dashboard(jarvis).snapshot()["session"]["cost_usd"] == pytest.approx(4)
    jarvis.model = "some-other-model"
    assert Dashboard(jarvis).snapshot()["session"]["cost_usd"] is None
