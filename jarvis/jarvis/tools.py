"""Tool definitions and handlers exposed to Claude."""

from __future__ import annotations

import fnmatch
import json
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from . import github
from .github import GitHubError
from .memory import Memory

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
    memory: Memory | None = None


def _str(description: str) -> dict[str, object]:
    return {"type": "string", "description": description}


def _int(description: str) -> dict[str, object]:
    return {"type": "integer", "description": description}


REPO = _str("Repository as owner/name (GitHub), or host/owner/name for gitlab.com, codeberg.org or bitbucket.org.")

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
        "name": "search_github_code",
        "description": "Search source code across ALL public GitHub repositories. Use it to find prior art, working implementations, library usage and examples to learn from. Supports GitHub code search qualifiers: language:, repo:, org:, user:, path:, extension:, filename:. Example: 'openwakeword Model language:python'. Rate-limited to about 10 searches a minute.",
        "input_schema": {
            "type": "object",
            "properties": {"query": _str("Code search query with optional qualifiers."), "limit": _int("Max results, 1-50. Default 15.")},
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_repo_info",
        "description": "Get a GitHub repository's description, stars, license, topics, default branch and activity. Check the license before reusing code from another project.",
        "input_schema": {"type": "object", "properties": {"repo": REPO}, "required": ["repo"], "additionalProperties": False},
    },
    {
        "name": "get_repo_tree",
        "description": "List every file path in any GitHub repository without cloning it. Good for quickly exploring another project's structure.",
        "input_schema": {
            "type": "object",
            "properties": {"repo": REPO, "ref": _str("Optional branch, tag or commit. Default: the default branch."), "path_prefix": _str("Optional directory to limit the listing, e.g. 'src/'.")},
            "required": ["repo"],
            "additionalProperties": False,
        },
    },
    {
        "name": "read_remote_file",
        "description": "Read a file (or list a directory) from any GitHub repository without cloning it. Use for files found with search_github_code or get_repo_tree.",
        "input_schema": {
            "type": "object",
            "properties": {"repo": REPO, "path": _str("File or directory path in the repository."), "ref": _str("Optional branch, tag or commit.")},
            "required": ["repo", "path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "pull_repo",
        "description": "Clone a repository into the local workspace, or fetch and fast-forward it if already cloned. Call this before reading, searching, editing or testing a repository locally. GitHub repos are owner/name; GitLab, Codeberg and Bitbucket repos are host/owner/name (e.g. gitlab.com/owner/name).",
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
        "name": "edit_file",
        "description": "Replace an exact snippet in a file in a cloned repository. old_text must appear exactly once (include surrounding lines to make it unique). Prefer this over write_file for changes to existing files.",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": REPO,
                "path": _str("File path inside the repository."),
                "old_text": _str("Exact text to replace, copied from read_file output without line numbers."),
                "new_text": _str("Replacement text."),
            },
            "required": ["repo", "path", "old_text", "new_text"],
            "additionalProperties": False,
        },
    },
    {
        "name": "git_diff",
        "description": "Show the current branch, uncommitted changes (git status and diff) in a cloned repository. Review it before committing.",
        "input_schema": {"type": "object", "properties": {"repo": REPO}, "required": ["repo"], "additionalProperties": False},
    },
    {
        "name": "commit_changes",
        "description": "Commit all changes in a cloned repository on a feature branch. If the repo is on its default branch, a branch named jarvis/<message> is created. Never commits to main/master.",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": REPO,
                "message": _str("Commit message: a short summary line, then optional detail."),
                "branch": _str("Optional feature branch name, e.g. feature/voice-commands."),
            },
            "required": ["repo", "message"],
            "additionalProperties": False,
        },
    },
    {
        "name": "push_and_open_pr",
        "description": "Push the current feature branch of a cloned GitHub repository and open a DRAFT pull request against its default branch. Never pushes the default branch and never force-pushes. Requires GITHUB_TOKEN with write access to the repository.",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": REPO,
                "title": _str("Pull request title."),
                "body": _str("Pull request description: what changed, why, how it was tested, and credit for any code adapted from other projects (repo, path, license)."),
            },
            "required": ["repo", "title", "body"],
            "additionalProperties": False,
        },
    },
    {
        "name": "remember",
        "description": "Save a note to long-term memory that persists across sessions: the user's preferences, their projects and repositories, decisions, conventions, and what you worked on. Keep each note to one specific fact.",
        "input_schema": {"type": "object", "properties": {"note": _str("One fact worth remembering next time.")}, "required": ["note"], "additionalProperties": False},
    },
    {
        "name": "forget",
        "description": "Remove a note from long-term memory, for example when it is wrong or the user asks you to forget something.",
        "input_schema": {"type": "object", "properties": {"text": _str("Text contained in the note to remove.")}, "required": ["text"], "additionalProperties": False},
    },
    {
        "name": "run_command",
        "description": "Run a shell command inside a cloned repository: install dependencies, run tests, builds and linters. Use commit_changes and push_and_open_pr for git commits and pushes. Times out after 120 seconds unless timeout_seconds is set (max 900).",
        "input_schema": {
            "type": "object",
            "properties": {"repo": REPO, "command": _str("Shell command to run from the repository root."), "timeout_seconds": _int("Timeout, 10-900 seconds. Default 120.")},
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
    git_dirs = [*ctx.workspace.glob("*/*/.git"), *ctx.workspace.glob("*/*/*/.git")]
    repos = sorted(str(d.parent.relative_to(ctx.workspace)) for d in git_dirs)
    return "\n".join(repos) if repos else "No repositories cloned yet."


def search_github_code(ctx: ToolContext, query: str, limit: int = 15) -> str:
    return json.dumps(github.search_code(query, limit), indent=2)


def get_repo_info(ctx: ToolContext, repo: str) -> str:
    return json.dumps(github.repo_info(repo), indent=2)


def get_repo_tree(ctx: ToolContext, repo: str, ref: str | None = None, path_prefix: str = "") -> str:
    paths = [p for p in github.repo_tree(repo, ref) if p.startswith(path_prefix)]
    shown = paths[:MAX_LIST_ENTRIES * 2]
    footer = f"\n... {len(paths) - len(shown)} more (narrow with path_prefix)" if len(paths) > len(shown) else ""
    return f"{len(paths)} files\n" + "\n".join(shown) + footer if paths else "No matching files."


def read_remote_file(ctx: ToolContext, repo: str, path: str, ref: str | None = None) -> str:
    text = github.read_remote_file(repo, path, ref)
    if text.endswith("is a directory:") or " is a directory:\n" in text[:300]:
        return text
    lines = text.splitlines()[:MAX_READ_LINES]
    body = "\n".join(f"{n:>6}\t{line}" for n, line in enumerate(lines, 1))
    more = f"\n... file continues ({len(text.splitlines())} lines); clone with pull_repo to read the rest" if len(text.splitlines()) > MAX_READ_LINES else ""
    return f"{repo}:{path}\n" + _truncate(body, MAX_READ_BYTES) + more


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


def edit_file(ctx: ToolContext, repo: str, path: str, old_text: str, new_text: str) -> str:
    root = repo_dir(ctx, repo)
    target = safe_path(root, path)
    if ".git" in target.relative_to(root.resolve()).parts:
        raise ToolError("Editing inside .git is not allowed.")
    if not target.is_file():
        raise ToolError(f"File not found: {path}. Use write_file to create it.")
    content = target.read_text(encoding="utf-8")
    count = content.count(old_text)
    if count != 1:
        raise ToolError(f"old_text appears {count} times in {path}; it must appear exactly once. Include more surrounding lines.")
    if not ctx.approve(f"Edit {repo}/{path} (-{len(old_text.splitlines())} +{len(new_text.splitlines())} lines)?"):
        return "The user declined this edit."
    target.write_text(content.replace(old_text, new_text, 1), encoding="utf-8")
    return f"Edited {path}."


def git_diff(ctx: ToolContext, repo: str) -> str:
    root = repo_dir(ctx, repo)
    branch = _git(root, ["rev-parse", "--abbrev-ref", "HEAD"]).strip()
    _git(root, ["add", "-A", "-N"])  # intent-to-add, so new files appear in the diff
    status = _git(root, ["status", "--short"]) or "(clean)"
    diff = _git(root, ["diff"])
    return _truncate(f"Branch: {branch}\n{status}\n{diff}")


def commit_changes(ctx: ToolContext, repo: str, message: str, branch: str | None = None) -> str:
    root = repo_dir(ctx, repo)
    if not ctx.approve(f"Commit in {repo}: {message.splitlines()[0]}"):
        return "The user declined this commit."
    return github.commit_changes(root, message, branch)


def push_and_open_pr(ctx: ToolContext, repo: str, title: str, body: str) -> str:
    root = repo_dir(ctx, repo)
    if not ctx.approve(f"Push {repo} and open a draft PR: {title}"):
        return "The user declined the push."
    return github.push_and_open_pr(root, github.validate_repo(repo), title, body)


def remember(ctx: ToolContext, note: str) -> str:
    if ctx.memory is None:
        raise ToolError("Memory is turned off for this session.")
    return ctx.memory.remember(note)


def forget(ctx: ToolContext, text: str) -> str:
    if ctx.memory is None:
        raise ToolError("Memory is turned off for this session.")
    return ctx.memory.forget(text)


BLOCKED_COMMANDS = [
    (re.compile(r"\bsudo\b|\bsu\s+-|\bdoas\b"), "commands that need root"),
    (re.compile(r"\brm\s+(-\w*\s+)*(/|~|\$HOME|/\*)(\s|$)"), "deleting the root or home directory"),
    (re.compile(r"\b(mkfs|fdisk|diskpart|shutdown|reboot|halt|poweroff)\b|\bdd\s+if="), "disk or system commands"),
    (re.compile(r":\(\)\s*\{"), "fork bombs"),
    (re.compile(r"\b(curl|wget)\b[^|]*\|\s*(sudo\s+)?(ba|z)?sh\b"), "piping downloads into a shell"),
    (re.compile(r"\bgit\s+push\b"), "git push (use push_and_open_pr, which never pushes the default branch)"),
    (re.compile(r"\bgit\s+(reset\s+--hard\s+origin|clean\s+-\w*f\w*d)"), "destructive git resets"),
    (re.compile(r"\bgh\s+(repo\s+delete|pr\s+merge|release\s+delete)\b"), "deleting repos, merging or deleting releases"),
]


def blocked_reason(command: str) -> str | None:
    for pattern, reason in BLOCKED_COMMANDS:
        if pattern.search(command):
            return reason
    return None


def run_command(ctx: ToolContext, repo: str, command: str, timeout_seconds: int = 120) -> str:
    root = repo_dir(ctx, repo)
    reason = blocked_reason(command)
    if reason:
        raise ToolError(f"Blocked for safety: {reason}. Find another way to do this.")
    timeout = max(10, min(timeout_seconds, 900))
    if not ctx.approve(f"Run in {repo}: {command}"):
        return "The user declined this command."
    try:
        result = subprocess.run(command, shell=True, cwd=root, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return f"Command timed out after {timeout} seconds."
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
    "edit_file": edit_file,
    "git_diff": git_diff,
    "commit_changes": commit_changes,
    "push_and_open_pr": push_and_open_pr,
    "run_command": run_command,
    "search_github_code": search_github_code,
    "get_repo_info": get_repo_info,
    "get_repo_tree": get_repo_tree,
    "read_remote_file": read_remote_file,
    "remember": remember,
    "forget": forget,
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
