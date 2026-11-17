"""What makes the quality gate hard to fool: content fingerprints, path scopes and real checks.

The gate doesn't trust *who said what*. It trusts the code itself:

- A **fingerprint** hashes every non-documentation file in a repository's working tree (tracked and
  untracked, honouring .gitignore). It is the same whether or not the files are committed, so it
  follows the code through Herald's commit and push.
- Herald may ship a repository only when its fingerprint equals the default branch's (only docs
  changed) or one that Sentinel verified. Code changed after verification, by any route (a sed in
  run_command, an MCP tool, a crashed run, a reset), no longer matches.
- Sentinel's PASS is accepted only when a recognised test or check command exited 0 *and* the code
  it ran against is exactly the code present when Sentinel finished.
"""

from __future__ import annotations

import fnmatch
import hashlib
import os
import posixpath
import re
import subprocess
import tempfile
from pathlib import Path

# ---- Paths ----------------------------------------------------------------------------------

DOC_SUFFIXES = (".md", ".mdx", ".markdown", ".rst", ".adoc")
DOC_NAMES = ("README", "CHANGELOG", "CHANGES", "HISTORY", "CONTRIBUTING", "AUTHORS", "NOTICE", "CODE_OF_CONDUCT")
DOC_NAME_SUFFIXES = ("", ".txt") + DOC_SUFFIXES  # README, README.txt, CHANGELOG.md ...
DOC_DIR_SUFFIXES = DOC_SUFFIXES + (".txt", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")
TEST_PATTERNS = ("test_*", "*_test.*", "*_tests.*", "*.test.*", "*.spec.*", "conftest.py")
TEST_DIRS = ("test", "tests", "__tests__", "spec", "specs", "testdata")


def normalise(path: str) -> str | None:
    """A repository-relative POSIX path, or None if it is absolute or climbs out ('..')."""
    raw = path.replace("\\", "/").strip()
    if not raw or raw.startswith("/") or re.match(r"^[A-Za-z]:", raw):
        return None
    clean = posixpath.normpath(raw)
    if clean in (".", "") or clean == ".." or clean.startswith("../"):
        return None
    return clean


def _split(path: str) -> tuple[str, str]:
    name = path.rsplit("/", 1)[-1]
    stem, dot, suffix = name.partition(".")
    return stem, (dot + suffix).lower() if dot else ""


def is_doc(path: str) -> bool:
    """README/CHANGELOG-style files, Markdown/RST/AsciiDoc anywhere, and text or images under docs/."""
    clean = normalise(path)
    if clean is None:
        return False
    parts = clean.split("/")
    name = parts[-1]
    lower = name.lower()
    if lower.endswith(DOC_SUFFIXES):
        return True
    stem, suffix = _split(clean)
    if stem.upper() in DOC_NAMES and suffix in DOC_NAME_SUFFIXES:
        return True
    return parts[0].lower() in ("docs", "doc") and len(parts) > 1 and lower.endswith(DOC_DIR_SUFFIXES)


def is_test(path: str) -> bool:
    clean = normalise(path)
    if clean is None:
        return False
    parts = clean.split("/")
    return (any(fnmatch.fnmatch(parts[-1].lower(), pattern) for pattern in TEST_PATTERNS)
            or any(part.lower() in TEST_DIRS for part in parts[:-1]))


# ---- Commands -------------------------------------------------------------------------------

_GIT_OPTS = r"(?:\s+(?:-[cC]\s+\S+|--?[\w-]+(?:=\S+)?))*"
GIT_HISTORY = re.compile(
    r"\bgit\b" + _GIT_OPTS + r"\s+(commit|push|merge|rebase|reset|cherry-pick|am|revert|tag|update-ref|commit-tree|filter-branch)\b"
)
_INSTALL = re.compile(r"\b(pip3?|python3?\s+-m\s+pip|npm|pnpm|yarn|bun|apt(-get)?|brew|gem|go|cargo|poetry|uv)\s+(install|add|i|get|sync|ci)\b")
_CHECK = re.compile(
    r"\b(pytest|py\.test|unittest|nose2|tox|nox|test|tests|check|spec|specs|jest|vitest|mocha|ava|karma|playwright|cypress|"
    r"rspec|minitest|phpunit|pest|ctest|lint|eslint|ruff|flake8|pylint|mypy|pyright|tsc|clippy|golangci-lint|vet)\b"
)


def rewrites_history(command: str) -> bool:
    """git commit, push, reset and friends: only Herald's tools may change history in team mode."""
    return bool(GIT_HISTORY.search(command))


_SHELL_TEST = re.compile(r"^\s*(test|\[)\s")  # the shell's own `test -f x` / `[ ... ]`
_SEPARATORS = re.compile(r"(&&|\|\||[;&|\n])")


def is_check_command(command: str) -> bool:
    """A command whose exit code is a test, lint or type-check result.

    The check must be the last command, joined to anything before it only by `&&`, because the shell
    reports the last command's exit code: in `pytest; true`, `pytest || true` or `pytest | tee log` a
    failing run still exits 0. Installs ('pip install pytest') and the shell's `test` builtin don't count.
    """
    pieces = _SEPARATORS.split(command)
    segments, operators = pieces[0::2], pieces[1::2]
    if any(op != "&&" for op in operators):
        return False
    last = segments[-1].strip() if segments else ""
    return bool(last) and bool(_CHECK.search(last)) and not _INSTALL.search(last) and not _SHELL_TEST.match(last)


# ---- Fingerprints ---------------------------------------------------------------------------


def _git(repo: Path, *args: str, env: dict[str, str] | None = None) -> str:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True, env=env, timeout=120).stdout


def _digest(entries: list[tuple[str, str, str]]) -> str:
    """entries: (mode, blob sha, path). Documentation is left out."""
    kept = sorted(f"{mode} {sha} {path}" for mode, sha, path in entries if not is_doc(path))
    return hashlib.sha256("\n".join(kept).encode()).hexdigest()[:16]


def fingerprint(repo: Path) -> str:
    """Hash of the working tree's non-doc files, committed or not, using a throwaway git index."""
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(tmp) / "index")}
        _git(repo, "add", "-A", ".", env=env)
        listing = _git(repo, "ls-files", "-s", "-z", env=env)
    entries = []
    for record in filter(None, listing.split("\0")):
        meta, _, path = record.partition("\t")
        mode, sha, _stage = meta.split()
        entries.append((mode, sha, path))
    return _digest(entries)


def base_fingerprint(repo: Path, branch: str) -> str:
    """Fingerprint of the default branch (origin's copy if there is one). An empty tree if neither exists."""
    for ref in (f"origin/{branch}", branch):
        try:
            listing = _git(repo, "ls-tree", "-r", "-z", ref)
        except subprocess.CalledProcessError:
            continue
        entries = []
        for record in filter(None, listing.split("\0")):
            meta, _, path = record.partition("\t")
            mode, _type, sha = meta.split()
            entries.append((mode, sha, path))
        return _digest(entries)
    return _digest([])
