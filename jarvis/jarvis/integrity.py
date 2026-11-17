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
import shlex
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

# ---- Paths ----------------------------------------------------------------------------------

DOC_SUFFIXES = (".md", ".markdown", ".rst", ".adoc")  # not .mdx: MDX is executable JSX
DOC_NAMES = ("README", "CHANGELOG", "CHANGES", "HISTORY", "CONTRIBUTING", "AUTHORS", "NOTICE", "CODE_OF_CONDUCT")
DOC_NAME_SUFFIXES = ("", ".txt") + DOC_SUFFIXES  # README, README.txt, CHANGELOG.md ...
DOC_DIR_SUFFIXES = DOC_SUFFIXES + (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")  # not .txt: docs/requirements.txt
# Test files only, by name. Test infrastructure (conftest.py, helpers, fixtures, scripts in tests/) is code:
# it can change what a test run reports, so Sentinel can't edit it and the gate fingerprints it.
TEST_PATTERNS = ("test_*.py", "*_test.py", "*_test.go", "*.test.*", "*.spec.*", "*_spec.rb", "*Test.java",
                 "*Tests.java", "*Test.kt", "*Tests.cs", "*_test.rs")


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
    name = clean.split("/")[-1]
    return any(fnmatch.fnmatchcase(name, pattern) or fnmatch.fnmatchcase(name.lower(), pattern.lower())
               for pattern in TEST_PATTERNS)


# ---- Commands -------------------------------------------------------------------------------

_GIT_OPTS = r"(?:\s+(?:-[cC]\s+\S+|--?[\w-]+(?:=\S+)?))*"
GIT_HISTORY = re.compile(
    r"\bgit\b" + _GIT_OPTS + r"\s+(commit|push|merge|rebase|reset|cherry-pick|am|revert|tag|update-ref|commit-tree|"
    r"filter-branch|stash|fetch|pull|branch|symbolic-ref|switch|checkout|restore|worktree|replace|notes)\b"
)


def rewrites_history(command: str) -> bool:
    """git commands that move refs or rewrite files from history. A speed bump, not the security
    boundary: the gate pins the base and checks the pushed content, so a disguised command gains nothing."""
    return bool(GIT_HISTORY.search(command))


RUNNERS = frozenset({
    "pytest", "py.test", "tox", "nox", "nose2", "jest", "vitest", "mocha", "ava", "karma", "rspec", "phpunit",
    "pest", "ctest", "eslint", "ruff", "flake8", "pylint", "mypy", "pyright", "tsc", "golangci-lint", "stylelint",
    "biome", "shellcheck", "hadolint", "rubocop", "standard", "xo", "prettier",
})
PY_MODULES = frozenset({"pytest", "unittest", "mypy", "ruff", "flake8", "pylint", "tox", "nox", "nose2", "doctest"})
WRAPPERS = {  # leading words that just run the next command
    ("npx",), ("bunx",), ("pnpm", "exec"), ("pnpm", "dlx"), ("yarn", "dlx"), ("bundle", "exec"), ("uv", "run"),
    ("poetry", "run"), ("pipenv", "run"), ("hatch", "run"), ("pdm", "run"), ("rye", "run"), ("timeout",), ("env",),
}
SUBCOMMANDS = {
    "go": {"test", "vet"}, "cargo": {"test", "clippy", "check", "nextest"}, "dotnet": {"test"},
    "mvn": {"test", "verify"}, "./mvnw": {"test", "verify"}, "gradle": {"test", "check"}, "./gradlew": {"test", "check"},
    "deno": {"test", "lint", "check"}, "bun": {"test"}, "swift": {"test"}, "mix": {"test"}, "flutter": {"test"},
    "playwright": {"test"}, "cypress": {"run"}, "rake": {"test", "spec"}, "elixir": set(),
}
NOT_A_RUN = frozenset({"--version", "-V", "--help", "-h", "help", "--collect-only", "--co", "--if-present",
                       "--list", "--list-tests", "--listTests", "--dry-run", "--showconfig", "--show-config",
                       "--passWithNoTests", "--pass-with-no-tests", "--no-tests=pass"})
_TARGET = re.compile(r"(test|check|lint|spec|verify|typecheck|ci)", re.IGNORECASE)
_SEPARATORS = re.compile(r"(&&|\|\||[;&|\n])")


def _words(segment: str) -> list[str] | None:
    try:
        words = shlex.split(segment, comments=True)
    except ValueError:
        return None
    while words and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", words[0]):  # CI=1 pytest
        words = words[1:]
    return words


def _strip_wrappers(words: list[str]) -> list[str]:
    changed = True
    while words and changed:
        changed = False
        for wrapper in WRAPPERS:
            if tuple(words[: len(wrapper)]) == wrapper:
                words = words[len(wrapper):]
                if wrapper == ("timeout",) and words:
                    words = words[1:]  # timeout 600 pytest
                changed = True
                break
    return words


def _invokes_check(words: list[str]) -> bool:
    words = _strip_wrappers(words)
    if not words or any(w in NOT_A_RUN for w in words):
        return False
    first, rest = words[0], words[1:]
    name = Path(first).name
    if name in RUNNERS:
        return True
    if re.fullmatch(r"python(3(\.\d+)?)?", name) and len(rest) >= 2 and rest[0] == "-m":
        return rest[1] in PY_MODULES
    if name in ("npm", "pnpm", "yarn", "bun") and rest:
        if rest[0] in ("test", "t"):
            return True
        if rest[0] in ("run", "run-script"):
            return len(rest) > 1 and bool(_TARGET.search(rest[1]))
        return name in ("yarn", "pnpm") and bool(_TARGET.search(rest[0]))  # yarn lint, pnpm typecheck
    if name in ("make", "just", "task", "invoke", "nx", "turbo"):
        targets = [w for w in rest if not w.startswith("-") and "=" not in w]
        return bool(targets) and all(_TARGET.search(t) for t in targets)
    allowed = SUBCOMMANDS.get(first, SUBCOMMANDS.get(name))
    if allowed is not None:
        return bool(rest) and rest[0] in allowed
    # A project script such as ./scripts/test.sh or bin/check, inside the repository.
    if "/" in first and not first.startswith(("/", "~")) and ".." not in first.split("/"):
        return bool(_TARGET.search(Path(first).name))
    return False


def is_check_command(command: str) -> bool:
    """A command whose exit code is a real test, lint or type-check result for this repository.

    - The check must be the last command, joined to anything before it only by `&&`: the shell reports
      the last command's exit code, so in `pytest; true`, `pytest || true` or `pytest | tee log` a
      failing run still exits 0.
    - It must *invoke* a known runner (pytest, python -m unittest, npm test, go test, make check, ...),
      not mention one (`echo pytest`, `cat tests/x.py`), and not just print its version or list tests.
    - No `cd` out of the repository (absolute paths, `..`, `~`).
    """
    pieces = _SEPARATORS.split(command)
    segments, operators = pieces[0::2], pieces[1::2]
    if not segments or any(op != "&&" for op in operators):
        return False
    for segment in segments[:-1]:
        words = _words(segment)
        if words is None:
            return False
        if words and words[0] in ("cd", "pushd") and len(words) > 1:
            target = words[1]
            if target.startswith(("/", "~", "-")) or ".." in target.split("/"):
                return False
    words = _words(segments[-1])
    return bool(words) and _invokes_check(words)


# ---- Fingerprints ---------------------------------------------------------------------------


SAFE_GIT = ["-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", "-c", "protocol.ext.allow=never"]


def _git(repo: Path, *args: str, env: dict[str, str] | None = None) -> str:
    return subprocess.run(["git", *SAFE_GIT, *args], cwd=repo, capture_output=True, text=True, check=True, env=env,
                           timeout=120).stdout


def _digest(entries: list[tuple[str, str, str]], skip: Callable[[str], bool] = is_doc) -> str:
    """entries: (mode, object sha, path). Paths where skip() is true (documentation) are left out."""
    kept = sorted(f"{mode} {sha} {path}" for mode, sha, path in entries if not skip(path))
    return hashlib.sha256("\n".join(kept).encode()).hexdigest()[:16]


def _git_dir(repo: Path) -> Path:
    return Path(_git(repo, "rev-parse", "--absolute-git-dir").strip())


def fingerprint(repo: Path, skip: Callable[[str], bool] = is_doc) -> str:
    """Hash of the working tree's files, committed or not, leaving out paths where skip() is true.

    Uses a throwaway copy of git's index, so unchanged files aren't re-read and the real index is untouched.
    """
    with tempfile.TemporaryDirectory() as tmp:
        index = Path(tmp) / "index"
        real = _git_dir(repo) / "index"
        if real.exists():
            # copy2 keeps the index's timestamp, which git needs to spot "racily clean" files (edited in
            # the same second the index was written). A fresh timestamp would hide a same-size edit.
            shutil.copy2(real, index)
        env = {**os.environ, "GIT_INDEX_FILE": str(index)}
        _git(repo, "add", "-A", ".", env=env)
        listing = _git(repo, "ls-files", "-s", "-z", env=env)
    entries = []
    for record in filter(None, listing.split("\0")):
        meta, _, path = record.partition("\t")
        mode, sha, _stage = meta.split()
        entries.append((mode, sha, path))
    return _digest(entries, skip)


def code_fingerprint(repo: Path) -> str:
    """Like fingerprint(), but leaving out tests too: what Sentinel may not change."""
    return fingerprint(repo, skip=lambda path: is_doc(path) or is_test(path))


def tree_fingerprint(repo: Path, ref: str | None) -> str:
    """Fingerprint of a commit's tree (what a push would send). An empty tree for None."""
    if ref is None:
        return _digest([], is_doc)
    listing = _git(repo, "ls-tree", "-r", "-z", ref)
    entries = []
    for record in filter(None, listing.split("\0")):
        meta, _, path = record.partition("\t")
        mode, _type, sha = meta.split()
        entries.append((mode, sha, path))
    return _digest(entries, is_doc)


def resolve(repo: Path, ref: str) -> str | None:
    try:
        return _git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}").strip() or None
    except subprocess.CalledProcessError:
        return None


def base_fingerprint(repo: Path, branch: str) -> str:
    """Fingerprint of the default branch (origin's copy if there is one). An empty tree if neither exists."""
    return tree_fingerprint(repo, resolve(repo, f"origin/{branch}") or resolve(repo, branch))
