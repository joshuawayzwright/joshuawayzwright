"""GitHub access for Jarvis: REST API lookups and local git clones."""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API_ROOT = "https://api.github.com"
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class GitHubError(Exception):
    """Raised when a GitHub or git operation fails. The message is shown to the model."""


def github_token() -> str | None:
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or None


def validate_repo(repo: str) -> str:
    repo = repo.strip().removesuffix(".git")
    if repo.startswith("https://github.com/"):
        repo = repo.removeprefix("https://github.com/").strip("/")
    if not REPO_RE.match(repo) or ".." in repo:
        raise GitHubError(f"Invalid repository '{repo}'. Use the form owner/name.")
    return repo


def api_get(path: str, params: dict[str, str | int] | None = None) -> object:
    url = f"{API_ROOT}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "jarvis-agent",
    }
    token = github_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", "replace")[:300]
        hint = ""
        if err.code in (401, 403, 404) and not token:
            hint = " (set GITHUB_TOKEN to reach private repositories or raise rate limits)"
        raise GitHubError(f"GitHub API {err.code} for {path}: {detail}{hint}") from err
    except urllib.error.URLError as err:
        raise GitHubError(f"Could not reach GitHub: {err.reason}") from err


def search_repos(query: str, limit: int = 10) -> list[dict[str, object]]:
    data = api_get("/search/repositories", {"q": query, "per_page": max(1, min(limit, 50))})
    assert isinstance(data, dict)
    return [_summarise(item) for item in data.get("items", [])]


def list_user_repos(owner: str, limit: int = 30) -> list[dict[str, object]]:
    if not re.match(r"^[A-Za-z0-9-]+$", owner):
        raise GitHubError(f"Invalid owner '{owner}'.")
    data = api_get(f"/users/{owner}/repos", {"per_page": max(1, min(limit, 100)), "sort": "pushed"})
    assert isinstance(data, list)
    return [_summarise(item) for item in data]


def _summarise(item: dict[str, object]) -> dict[str, object]:
    return {
        "repo": item.get("full_name"),
        "description": item.get("description"),
        "language": item.get("language"),
        "stars": item.get("stargazers_count"),
        "private": item.get("private"),
        "default_branch": item.get("default_branch"),
        "pushed_at": item.get("pushed_at"),
    }


def _git_auth_args() -> list[str]:
    """Pass the token per command as an HTTP header so it is never written to .git/config."""
    token = github_token()
    if not token:
        return []
    basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    return ["-c", f"http.https://github.com/.extraheader=Authorization: Basic {basic}"]


def run_git(args: list[str], cwd: Path | None = None, timeout: int = 300) -> str:
    try:
        result = subprocess.run(
            ["git", *_git_auth_args(), *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
    except subprocess.TimeoutExpired as err:
        raise GitHubError(f"git {args[0]} timed out after {timeout}s") from err
    if result.returncode != 0:
        raise GitHubError(f"git {' '.join(args[:2])} failed: {result.stderr.strip()[:500]}")
    return result.stdout


def pull_repo(workspace: Path, repo: str, ref: str | None = None) -> str:
    """Clone the repository into the workspace, or fetch and fast-forward an existing clone."""
    repo = validate_repo(repo)
    target = workspace / repo
    if ref is not None and (ref.startswith("-") or not re.match(r"^[A-Za-z0-9_./-]+$", ref)):
        raise GitHubError(f"Invalid ref '{ref}'.")

    if (target / ".git").is_dir():
        run_git(["fetch", "--prune", "origin"], cwd=target)
        if ref:
            run_git(["checkout", ref], cwd=target)
        branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=target).strip()
        if branch != "HEAD":  # skip pull on a detached tag/commit checkout
            run_git(["pull", "--ff-only"], cwd=target)
        action = "Updated"
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        run_git(["clone", "--filter=blob:none", f"https://github.com/{repo}.git", str(target)])
        if ref:
            run_git(["checkout", ref], cwd=target)
        action = "Cloned"

    head = run_git(["log", "-1", "--format=%h %s (%cr)"], cwd=target).strip()
    branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=target).strip()
    files = len(run_git(["ls-files"], cwd=target).splitlines())
    return f"{action} {repo} at {target}\nBranch: {branch}\nHEAD: {head}\nTracked files: {files}"
