"""GitHub access for Jarvis: REST API (search, files, pull requests) and local git clones."""

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
NAME = r"[A-Za-z0-9_.-]+"
OWNER = r"[A-Za-z0-9-]+"  # GitHub user and organisation names cannot contain dots or underscores
REPO_RE = re.compile(rf"^{OWNER}/{NAME}$")
# Public git hosts Jarvis may clone from, besides GitHub. Repos there are written host/owner/name.
OTHER_HOSTS = ("gitlab.com", "codeberg.org", "bitbucket.org")
HOSTED_RE = re.compile(rf"^({'|'.join(re.escape(h) for h in OTHER_HOSTS)})/{NAME}/{NAME}$")
REF_RE = re.compile(r"^[A-Za-z0-9_./-]+$")
PROTECTED_BRANCHES = {"main", "master", "trunk", "develop", "production", "release"}


class GitHubError(Exception):
    """Raised when a GitHub or git operation fails. The message is shown to the model."""


def github_token() -> str | None:
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or None


def validate_repo(repo: str) -> str:
    """Normalise a repository reference.

    GitHub repositories are "owner/name". Repositories on other public hosts are
    "host/owner/name" (e.g. gitlab.com/inkscape/inkscape). Full https URLs are accepted.
    """
    repo = repo.strip().removesuffix("/").removesuffix(".git")
    repo = re.sub(r"^https://(www\.)?", "", repo)
    repo = repo.removeprefix("github.com/")
    if ".." in repo or not (REPO_RE.match(repo) or HOSTED_RE.match(repo)):
        hosts = ", ".join(OTHER_HOSTS)
        raise GitHubError(f"Invalid repository '{repo}'. Use owner/name for GitHub, or host/owner/name for {hosts}.")
    return repo


def is_github(repo: str) -> bool:
    return REPO_RE.match(repo) is not None


def clone_url(repo: str) -> str:
    return f"https://github.com/{repo}.git" if is_github(repo) else f"https://{repo}.git"


def validate_ref(ref: str) -> str:
    if ref.startswith("-") or ".." in ref or not REF_RE.match(ref):
        raise GitHubError(f"Invalid branch or ref '{ref}'.")
    return ref


# ---- REST API -----------------------------------------------------------------------------


def _request(method: str, path: str, params: dict[str, str | int] | None = None, body: object = None,
             accept: str = "application/vnd.github+json") -> object:
    url = f"{API_ROOT}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    headers = {"Accept": accept, "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "jarvis-agent"}
    token = github_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8") or "null")
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", "replace")[:400]
        hint = ""
        if err.code in (401, 403, 404, 422) and not token:
            hint = " (set GITHUB_TOKEN: code search, private repositories and pull requests need it)"
        elif err.code == 403 and "rate limit" in detail.lower():
            hint = " (rate limited: code search allows about 10 requests a minute; wait and retry)"
        raise GitHubError(f"GitHub API {err.code} for {method} {path}: {detail}{hint}") from err
    except urllib.error.URLError as err:
        raise GitHubError(f"Could not reach GitHub: {err.reason}") from err


def api_get(path: str, params: dict[str, str | int] | None = None, accept: str = "application/vnd.github+json") -> object:
    return _request("GET", path, params, accept=accept)


def api_post(path: str, body: object) -> object:
    return _request("POST", path, body=body)


def _require_github(repo: str) -> str:
    repo = validate_repo(repo)
    if not is_github(repo):
        raise GitHubError(f"{repo} is not on GitHub. Clone it with pull_repo and read it locally.")
    return repo


def search_repos(query: str, limit: int = 10) -> list[dict[str, object]]:
    data = api_get("/search/repositories", {"q": query, "per_page": max(1, min(limit, 50))})
    assert isinstance(data, dict)
    return [_summarise(item) for item in data.get("items", [])]


def search_code(query: str, limit: int = 15) -> dict[str, object]:
    """Search source code across all public GitHub repositories (needs a token)."""
    data = api_get(
        "/search/code",
        {"q": query, "per_page": max(1, min(limit, 50))},
        accept="application/vnd.github.text-match+json",
    )
    assert isinstance(data, dict)
    results = []
    for item in data.get("items", []):
        fragments = [m.get("fragment", "") for m in item.get("text_matches", []) or []]
        results.append({
            "repo": (item.get("repository") or {}).get("full_name"),
            "path": item.get("path"),
            "url": item.get("html_url"),
            "snippet": "\n…\n".join(f.strip() for f in fragments[:2])[:600],
        })
    return {"total_count": data.get("total_count"), "results": results}


def repo_info(repo: str) -> dict[str, object]:
    data = api_get(f"/repos/{_require_github(repo)}")
    assert isinstance(data, dict)
    info = _summarise(data)
    info["topics"] = data.get("topics")
    info["homepage"] = data.get("homepage")
    info["open_issues"] = data.get("open_issues_count")
    info["archived"] = data.get("archived")
    return info


def read_remote_file(repo: str, path: str, ref: str | None = None) -> str:
    """Read one file from a GitHub repository without cloning it."""
    repo = _require_github(repo)
    path = path.strip("/")
    if ".." in path.split("/"):
        raise GitHubError("Invalid path.")
    params = {"ref": validate_ref(ref)} if ref else None
    data = api_get(f"/repos/{repo}/contents/{urllib.parse.quote(path)}", params)
    if isinstance(data, list):
        names = [f"{e.get('name')}{'/' if e.get('type') == 'dir' else ''}" for e in data]
        return f"{path or '/'} is a directory:\n" + "\n".join(names)
    assert isinstance(data, dict)
    if data.get("encoding") != "base64" or data.get("content") is None:
        raise GitHubError(f"{path} is too large to read through the API ({data.get('size')} bytes). Use pull_repo.")
    raw = base64.b64decode(data["content"])
    if b"\x00" in raw[:8000]:
        raise GitHubError(f"{path} is a binary file.")
    return raw.decode("utf-8", "replace")


def repo_tree(repo: str, ref: str | None = None) -> list[str]:
    """List every file path in a GitHub repository without cloning it."""
    repo = _require_github(repo)
    if not ref:
        ref = str(repo_info(repo).get("default_branch") or "HEAD")
    data = api_get(f"/repos/{repo}/git/trees/{urllib.parse.quote(validate_ref(ref))}", {"recursive": 1})
    assert isinstance(data, dict)
    paths = [e["path"] for e in data.get("tree", []) if e.get("type") == "blob"]
    if data.get("truncated"):
        paths.append("… (tree truncated by GitHub; use pull_repo for the full list)")
    return paths


def list_user_repos(owner: str, limit: int = 30) -> list[dict[str, object]]:
    if not re.match(r"^[A-Za-z0-9-]+$", owner):
        raise GitHubError(f"Invalid owner '{owner}'.")
    data = api_get(f"/users/{owner}/repos", {"per_page": max(1, min(limit, 100)), "sort": "pushed"})
    assert isinstance(data, list)
    return [_summarise(item) for item in data]


def _summarise(item: dict[str, object]) -> dict[str, object]:
    license_info = item.get("license") or {}
    return {
        "repo": item.get("full_name"),
        "description": item.get("description"),
        "language": item.get("language"),
        "stars": item.get("stargazers_count"),
        "license": license_info.get("spdx_id") if isinstance(license_info, dict) else None,
        "private": item.get("private"),
        "default_branch": item.get("default_branch"),
        "pushed_at": item.get("pushed_at"),
    }


def create_pull_request(repo: str, head: str, base: str, title: str, body: str) -> dict[str, object]:
    data = api_post(
        f"/repos/{_require_github(repo)}/pulls",
        {"title": title, "head": head, "base": base, "body": body, "draft": True},
    )
    assert isinstance(data, dict)
    return {"number": data.get("number"), "url": data.get("html_url")}


# ---- git ----------------------------------------------------------------------------------


def _git_auth_args() -> list[str]:
    """Pass the token per command as an HTTP header, scoped to github.com, never written to .git/config."""
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
        raise GitHubError(f"git {' '.join(args[:2])} failed: {(result.stderr or result.stdout).strip()[:500]}")
    return result.stdout


def _has_upstream(target: Path) -> bool:
    try:
        run_git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], cwd=target)
        return True
    except GitHubError:
        return False


def default_branch(target: Path) -> str:
    try:
        ref = run_git(["symbolic-ref", "--short", "refs/remotes/origin/HEAD"], cwd=target).strip()
        return ref.removeprefix("origin/")
    except GitHubError:
        return "main"


def pull_repo(workspace: Path, repo: str, ref: str | None = None) -> str:
    """Clone the repository into the workspace, or fetch and fast-forward an existing clone."""
    repo = validate_repo(repo)
    target = workspace / repo
    if ref is not None:
        validate_ref(ref)

    if (target / ".git").is_dir():
        run_git(["fetch", "--prune", "origin"], cwd=target)
        if ref:
            run_git(["checkout", ref], cwd=target)
        branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=target).strip()
        if branch != "HEAD" and _has_upstream(target):  # skip detached checkouts and local-only branches
            run_git(["pull", "--ff-only"], cwd=target)
        action = "Updated"
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        run_git(["clone", "--filter=blob:none", clone_url(repo), str(target)])
        if ref:
            run_git(["checkout", ref], cwd=target)
        action = "Cloned"

    head = run_git(["log", "-1", "--format=%h %s (%cr)"], cwd=target).strip()
    branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=target).strip()
    files = len(run_git(["ls-files"], cwd=target).splitlines())
    return (f"{action} {repo} at {target}\nBranch: {branch} (default: {default_branch(target)})\n"
            f"HEAD: {head}\nTracked files: {files}")


def _identity_args(target: Path) -> list[str]:
    """Use the user's git identity; fall back to a Jarvis identity only if none is configured."""
    try:
        if run_git(["config", "user.email"], cwd=target).strip():
            return []
    except GitHubError:
        pass
    name = os.environ.get("JARVIS_GIT_NAME", "Jarvis")
    email = os.environ.get("JARVIS_GIT_EMAIL", "jarvis@users.noreply.github.com")
    return ["-c", f"user.name={name}", "-c", f"user.email={email}"]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "changes"


def commit_changes(target: Path, message: str, branch: str | None = None) -> str:
    """Commit all changes on a working branch. Never commits onto the default branch."""
    current = run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=target).strip()
    protected = PROTECTED_BRANCHES | {default_branch(target)}
    if branch:
        validate_ref(branch)
    elif current in protected or current == "HEAD":
        branch = f"jarvis/{_slug(message.splitlines()[0])}"
    if branch and branch in protected:
        raise GitHubError(f"Refusing to commit to '{branch}'. Use a feature branch.")
    if branch and branch != current:
        exists = subprocess.run(["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"],
                                cwd=target, capture_output=True).returncode == 0
        run_git(["checkout", branch] if exists else ["checkout", "-b", branch], cwd=target)
        current = branch
    run_git(["add", "-A"], cwd=target)
    if not run_git(["status", "--porcelain"], cwd=target).strip():
        return f"Nothing to commit on {current}."
    run_git([*_identity_args(target), "commit", "-q", "-m", message], cwd=target)
    stat = run_git(["show", "--stat", "--format=%h %s", "HEAD"], cwd=target).strip()
    return f"Committed on branch {current}:\n{stat}"


def push_and_open_pr(target: Path, repo: str, title: str, body: str) -> str:
    """Push the current feature branch (never the default branch, never forced) and open a draft PR."""
    repo = _require_github(repo)
    branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=target).strip()
    base = default_branch(target)
    if branch == "HEAD" or branch in PROTECTED_BRANCHES | {base}:
        raise GitHubError(f"Refusing to push '{branch}'. Commit on a feature branch first (commit_changes).")
    ahead = run_git(["rev-list", "--count", f"origin/{base}..HEAD"], cwd=target).strip()
    if ahead == "0":
        raise GitHubError(f"Branch {branch} has no commits ahead of {base}. Nothing to propose.")
    run_git(["push", "-u", "origin", f"HEAD:refs/heads/{branch}"], cwd=target)
    pr = create_pull_request(repo, head=branch, base=base, title=title, body=body)
    return f"Pushed {branch} ({ahead} commit(s)) and opened draft PR #{pr['number']}: {pr['url']}"
