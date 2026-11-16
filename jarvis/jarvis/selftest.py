"""A live end-to-end check of team mode on a small local repository with a planted bug.

`jarvis --selftest` builds the repository, hands the whole crew one autonomous goal, then checks the
outcome itself rather than trusting the agents' reports:

- the original tests pass against the new code (so a weakened test can't fake a pass),
- the fix is committed on a feature branch, and main is untouched,
- the quality gate saw Sentinel's PASS before Herald shipped.

Nothing leaves the machine except the Claude API calls: the repository has no remote, so there is
nothing to push to.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

REPO = "selftest/stats"
DEFAULT_BUDGET = 2_000_000

CODE = '''"""Small statistics helpers."""


def mean(values: list[float]) -> float:
    if not values:
        raise ValueError("mean() needs at least one value")
    return sum(values) / len(values)


def median(values: list[float]) -> float:
    if not values:
        raise ValueError("median() needs at least one value")
    ordered = sorted(values)
    middle = len(ordered) // 2
    return ordered[middle]


def spread(values: list[float]) -> float:
    """Difference between the largest and smallest value."""
    if not values:
        raise ValueError("spread() needs at least one value")
    return max(values) - min(values)
'''

TESTS = '''import unittest

from stats import mean, median, spread


class StatsTest(unittest.TestCase):
    def test_mean(self):
        self.assertEqual(mean([1, 2, 3, 4]), 2.5)

    def test_median_odd(self):
        self.assertEqual(median([5, 1, 3]), 3)

    def test_median_even(self):
        self.assertEqual(median([4, 1, 3, 2]), 2.5)

    def test_spread(self):
        self.assertEqual(spread([3, 9, 4]), 6)

    def test_empty_raises(self):
        for fn in (mean, median, spread):
            with self.assertRaises(ValueError):
                fn([])


if __name__ == "__main__":
    unittest.main()
'''

README = """# stats

Small statistics helpers. Run the tests with `python3 -m unittest -v`.
"""

TEST_COMMAND = [sys.executable, "-m", "unittest", "-q"]

GOAL = f"""Self-test of the crew. The repository {REPO} is already in the local workspace; it is local-only with no remote, so do not call pull_repo, and do not push or open a pull request.

Its test suite fails. Find the bug, fix it in the application code, and verify with `python3 -m unittest -v` in the repository. Then commit the fix on a feature branch (not main). Do not change or weaken the existing tests; adding a test is fine.

Use the crew the normal way: recon, build with Forge, verify with Sentinel, then have Herald commit (commit only, no push). Finish with a short report of what each specialist did."""

GIT = ["git", "-c", "user.name=Jarvis selftest", "-c", "user.email=selftest@example.invalid"]


@dataclass
class Check:
    name: str
    ok: bool
    detail: str

    def line(self) -> str:
        return f"{'PASS' if self.ok else 'FAIL'}  {self.name}: {self.detail}"


def build_fixture(workspace: Path) -> Path:
    """Create the buggy repository in the workspace and return its path."""
    repo = workspace / REPO
    if repo.exists():
        raise FileExistsError(f"{repo} already exists; use a fresh workspace.")
    repo.mkdir(parents=True)
    (repo / "stats.py").write_text(CODE)
    (repo / "test_stats.py").write_text(TESTS)
    (repo / "README.md").write_text(README)
    (repo / ".gitignore").write_text("__pycache__/\n*.pyc\n")
    for args in (["git", "init", "-q", "-b", "main"], ["git", "add", "."], [*GIT, "commit", "-qm", "Initial import"]):
        subprocess.run(args, cwd=repo, check=True, capture_output=True)
    return repo


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()


def _tests_pass(directory: Path) -> tuple[bool, str]:
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    run = subprocess.run(TEST_COMMAND, cwd=directory, capture_output=True, text=True, timeout=120, env=env)
    tail = (run.stderr or run.stdout).strip().splitlines()
    return run.returncode == 0, tail[-1] if tail else f"exit {run.returncode}"


def verify(repo: Path, gate_history: list[tuple[str, str]] | None = None) -> list[Check]:
    """Check the outcome directly in the repository."""
    checks: list[Check] = []
    branch = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    ahead = int(_git(repo, "rev-list", "--count", "main..HEAD") or 0)
    checks.append(Check("Committed on a feature branch", branch != "main" and ahead > 0,
                        f"branch {branch}, {ahead} commit(s) ahead of main"))
    main_head = _git(repo, "log", "-1", "--format=%s", "main")
    checks.append(Check("main untouched", main_head == "Initial import" and _git(repo, "rev-list", "--count", "main") == "1",
                        f"main's latest commit: {main_head!r}"))
    dirty = _git(repo, "status", "--porcelain")
    checks.append(Check("Working tree clean", not dirty, "nothing uncommitted" if not dirty else f"uncommitted: {dirty[:120]}"))

    ok, detail = _tests_pass(repo)
    checks.append(Check("Suite passes on the branch", ok, detail))
    # Run the ORIGINAL tests against the new code, so a weakened or deleted test can't fake a pass.
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "stats.py").write_text((repo / "stats.py").read_text())
        (Path(tmp) / "test_stats.py").write_text(TESTS)
        ok, detail = _tests_pass(Path(tmp))
    checks.append(Check("Original tests pass on the new code", ok, detail))

    if gate_history is not None:
        order = [key for key, outcome in gate_history if outcome == "done"]
        sentinel_before_ship = "herald" in order and "sentinel" in order[: order.index("herald")]
        forge_used = "forge" in order
        checks.append(Check("Crew followed the gate", forge_used and sentinel_before_ship,
                            "order: " + " → ".join(order) if order else "no specialist finished an assignment"))
    return checks


def report(checks: list[Check]) -> str:
    passed = sum(c.ok for c in checks)
    verdict = "SELF-TEST PASSED" if passed == len(checks) else "SELF-TEST FAILED"
    return "\n".join([f"{verdict} ({passed}/{len(checks)} checks)", *("  " + c.line() for c in checks)])
