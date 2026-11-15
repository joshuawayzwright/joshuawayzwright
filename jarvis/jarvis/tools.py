"""Tool definitions and handlers exposed to Claude."""

from __future__ import annotations

import fnmatch
import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from . import github
from .github import GitHubError

MAX_READ_BYTES = 200_000
MAX_READ_LINES = 2_000
MAX_LIST_ENTRIES = 500
MAX_SEARCH_LINES = 200
MAX_OUTPUT_CHARS = 30_000


class ToolError(Exception):
    """A tool failure reported back to Claude as an is_error result."""


Approver = Callable[[str], bool]


@dataclass
class ToolContext:
    workspace: Path
    approve: Approver


def _str(description: str) -> dict[str, object]:
    return {"type": "string", "description": description}


def _int(description: str) -> dict[str, object]:
    return {"type": "integer", "description": description}


REPO = _str("Repository as owner/name, e.g. octocat/Hello-World.")

TOOL_SCHEMAS: list[dict[str, object]] = [
    {
        "name": "search_github_repos",
        "description": "Search GitHub for repositories. Supports GitHub search syntax (user:, org:, language:, stars:>N).",
        "input_schema": {
            "type": "object",
            "properties": {"query": _str("GitHub repository search query."), "limit": _int("Max results, 1-50. Default 10.")},
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "list_user_repos",
        "description": "List public repositories for a GitHub user or organisation, most recently pushed first.",
        "input_schema": {
            "type": "object",
            "properties": {"owner": _str("GitHub username or organisation."), "limit": _int("Max results, 1-100. Default 30.")},
            "required": ["owner"],
            "additionalProperties": False,
        },
    },
    {
        "name": "pull_repo",
        "description": "Clone a GitHub repository into the local workspace, or fetch and fast-forward it if already cloned. Call this before reading or searching a repository's code.",
        "input_schema": {
            "type": "object",
            "properties": {"repo": REPO, "ref": _str("Optional branch, tag or commit to check out.")},
            "required": ["repo"],
            "additionalProperties": False,
        },
    },
    {
        "name": "list_local_repos",
        "description": "List repositories already cloned in the local workspace.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "list_files",
        "description": "List tracked files in a cloned repository, optionally under a directory and filtered by a glob such as '*.py'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": REPO,
                "path": _str("Directory inside the repository. Default: repository root."),
                "glob": _str("Filename glob filter, e.g. '*.ts' or 'src/**/*.py'."),
            },
            "required": ["repo"],
            "additionalProperties": False,
        },
    },
    {
        "name": "read_file",
        "description": "Read a file from a cloned repository with line numbers. Use start_line/end_line for large files.",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": REPO,
                "path": _str("File path inside the repository."),
                "start_line": _int("First line to read (1-based). Default 1."),
                "end_line": _int("Last line to read, inclusive."),
            },
            "required": ["repo", "path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "search_code",
        "description": "Search a cloned repository's tracked files with an extended regular expression (git grep). Returns file:line:match.",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": REPO,
                "pattern": _str("Extended regex to search for."),
                "glob": _str("Optional pathspec glob to limit the search, e.g. '*.py'."),
                "ignore_case": {"type": "boolean", "description": "Case-insensitive search. Default false."},
            },
            "required": ["repo", "pattern"],
            "additionalProperties": False,
        },
    },
    {
        "name": "git_log",
        "description": "Show recent commits in a cloned repository, optionally for one path.",
        "input_schema": {
            "type": "object",
            "properties": {"repo": REPO, "path": _str("Optional file or directory."), "limit": _int("Number of commits, 1-100. Default 20.")},
            "required": ["repo"],
            "additionalProperties": False,
        },
    },
    {
        "name": "write_file",
        "description": "Create or overwrite a file in a cloned repository. The user must approve each write.",
        "input_schema": {
            "type": "object",
            "properties": {"repo": REPO, "path": _str("File path inside the repository."), "content": _str("Full new file content.")},
            "required": ["repo", "path", "content"],
            "additionalProperties": False,
        },
    },
    {
        "name": "run_command",
        "description": "Run a shell command inside a cloned repository (tests, builds, linters). The user must approve each command. Times out after 120 seconds.",
        "input_schema": {
            "type": "object",
            "properties": {"repo": REPO, "command": _str("Shell command to run from the repository root.")},
            "required": ["repo", "command"],
            "additionalProperties": False,
        },
    },
]

_TYPES: dict[str, type | tuple[type, ...]] = {"string": str, "integer": int, "boolean": bool}


def validate_input(name: str, data: object) -> dict[str, object]:
    """Check tool input against its schema; the API does not guarantee validity without strict mode."""
    schema = next((s for s in TOOL_SCHEMAS if s["name"] == name), None)
    if schema is None:
        raise ToolError(f"Unknown tool '{name}'.")
    if not isinstance(data, dict):
        raise ToolError("Tool input must be a JSON object.")
    spec = schema["input_schema"]
    assert isinstance(spec, dict)
    properties: dict[str, dict[str, str]] = spec.get("properties", {})
    for key in spec.get("required", []):
        if key not in data:
            raise ToolError(f"Missing required field '{key}'.")
    for key, value in data.items():
        if key not in properties:
            raise ToolError(f"Unexpected field '{key}'.")
        expected = _TYPES[properties[key]["type"]]
        if isinstance(value, bool) and expected is int or not isinstance(value, expected):
            raise ToolError(f"Field '{key}' must be of type {properties[key]['type']}.")
    return data


def repo_dir(ctx: ToolContext, repo: str) -> Path:
    try:
        repo = github.validate_repo(repo)
    except GitHubError as err:
        raise ToolError(str(err)) from err
    path = ctx.workspace / repo
    if not (path / ".git").is_dir():
        raise ToolError(f"{repo} is not cloned yet. Call pull_repo first.")
    return path


def safe_path(root: Path, relative: str) -> Path:
    """Resolve a path inside the repository, refusing anything that escapes it."""
    resolved = (root / relative).resolve()
    if resolved != root.resolve() and root.resolve() not in resolved.parents:
        raise ToolError(f"Path '{relative}' is outside the repository.")
    return resolved


def _truncate(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated {len(text) - limit} characters]"


def _git(root: Path, args: list[str]) -> str:
    try:
        return github.run_git(args, cwd=root, timeout=60)
    except GitHubError as err:
        raise ToolError(str(err)) from err


def search_github_repos(ctx: ToolContext, query: str, limit: int = 10) -> str:
    return json.dumps(github.search_repos(query, limit), indent=2)


def list_user_repos(ctx: ToolContext, owner: str, limit: int = 30) -> str:
    return json.dumps(github.list_user_repos(owner, limit), indent=2)


def pull_repo(ctx: ToolContext, repo: str, ref: str | None = None) -> str:
    return github.pull_repo(ctx.workspace, repo, ref)


def list_local_repos(ctx: ToolContext) -> str:
    if not ctx.workspace.is_dir():
        return "No repositories cloned yet."
    repos = sorted(
        f"{git_dir.parent.parent.name}/{git_dir.parent.name}" for git_dir in ctx.workspace.glob("*/*/.git")
    )
    return "\n".join(repos) if repos else "No repositories cloned yet."


def list_files(ctx: ToolContext, repo: str, path: str = "", glob: str | None = None) -> str:
    root = repo_dir(ctx, repo)
    args = ["ls-files"]
    if path:
        safe_path(root, path)
        args += ["--", path]
    files = _git(root, args).splitlines()
    if glob:
        files = [f for f in files if fnmatch.fnmatch(f, glob) or fnmatch.fnmatch(Path(f).name, glob)]
    total = len(files)
    shown = files[:MAX_LIST_ENTRIES]
    footer = f"\n... {total - len(shown)} more files (narrow with path or glob)" if total > len(shown) else ""
    return (f"{total} files\n" + "\n".join(shown) + footer) if files else "No matching files."


def read_file(ctx: ToolContext, repo: str, path: str, start_line: int = 1, end_line: int | None = None) -> str:
    root = repo_dir(ctx, repo)
    target = safe_path(root, path)
    if not target.is_file():
        raise ToolError(f"File not found: {path}")
    raw = target.read_bytes()[: MAX_READ_BYTES * 5]
    if b"\x00" in raw[:8_000]:
        raise ToolError(f"{path} looks like a binary file.")
    lines = raw.decode("utf-8", "replace").splitlines()
    start = max(1, start_line)
    end = min(len(lines), end_line or start + MAX_READ_LINES - 1, start + MAX_READ_LINES - 1)
    body = "\n".join(f"{n:>6}\t{lines[n - 1]}" for n in range(start, end + 1))
    header = f"{path} (lines {start}-{end} of {len(lines)})\n"
    return header + _truncate(body, MAX_READ_BYTES)


def search_code(ctx: ToolContext, repo: str, pattern: str, glob: str | None = None, ignore_case: bool = False) -> str:
    root = repo_dir(ctx, repo)
    args = ["-c", "grep.fallbackToNoIndex=false", "grep", "-n", "-I", "-E"]
    if ignore_case:
        args.append("-i")
    args += ["-e", pattern]
    if glob:
        args += ["--", glob]
    try:
        result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired as err:
        raise ToolError("Search timed out; use a narrower pattern or glob.") from err
    if result.returncode == 1:
        return "No matches."
    if result.returncode != 0:
        raise ToolError(f"Search failed: {result.stderr.strip()[:300]}")
    matches = result.stdout.splitlines()
    shown = [m[:400] for m in matches[:MAX_SEARCH_LINES]]
    footer = f"\n... {len(matches) - len(shown)} more matches" if len(matches) > len(shown) else ""
    return f"{len(matches)} matches\n" + "\n".join(shown) + footer


def git_log(ctx: ToolContext, repo: str, path: str | None = None, limit: int = 20) -> str:
    root = repo_dir(ctx, repo)
    args = ["log", f"-{max(1, min(limit, 100))}", "--format=%h %ad %an: %s", "--date=short"]
    if path:
        safe_path(root, path)
        args += ["--", path]
    return _git(root, args) or "No commits."


def write_file(ctx: ToolContext, repo: str, path: str, content: str) -> str:
    root = repo_dir(ctx, repo)
    target = safe_path(root, path)
    if ".git" in target.relative_to(root.resolve()).parts:
        raise ToolError("Writing inside .git is not allowed.")
    verb = "Overwrite" if target.exists() else "Create"
    if not ctx.approve(f"{verb} {repo}/{path} ({len(content.splitlines())} lines)?"):
        return "The user declined this write."
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} characters to {path}."


def run_command(ctx: ToolContext, repo: str, command: str) -> str:
    root = repo_dir(ctx, repo)
    if not ctx.approve(f"Run in {repo}: {command}"):
        return "The user declined this command."
    try:
        result = subprocess.run(command, shell=True, cwd=root, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return "Command timed out after 120 seconds."
    output = f"exit code {result.returncode}\n--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    return _truncate(output)


HANDLERS: dict[str, Callable[..., str]] = {
    "search_github_repos": search_github_repos,
    "list_user_repos": list_user_repos,
    "pull_repo": pull_repo,
    "list_local_repos": list_local_repos,
    "list_files": list_files,
    "read_file": read_file,
    "search_code": search_code,
    "git_log": git_log,
    "write_file": write_file,
    "run_command": run_command,
}


def execute(ctx: ToolContext, name: str, raw_input: object) -> tuple[str, bool]:
    """Run a tool. Returns (content, is_error)."""
    try:
        args = validate_input(name, raw_input)
        return HANDLERS[name](ctx, **args), False
    except (ToolError, GitHubError) as err:
        return f"Error: {err}", True
    except OSError as err:
        return f"Error: {err}", True
