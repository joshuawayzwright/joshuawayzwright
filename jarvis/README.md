# Jarvis

An AI engineering agent for your terminal. Jarvis searches the code of every public repository on GitHub, pulls projects from GitHub, GitLab, Codeberg and Bitbucket, and answers questions about them. It can also build features: it researches how other projects solve the problem, makes the change, runs the tests, commits to a feature branch and opens a draft pull request. It asks before each change, or works through a goal end to end in autonomous mode. It runs on the Claude API (`claude-opus-5-5` by default), and you can talk to it by voice.

Example session (the tool calls are what Jarvis prints; the answer text depends on the model):

```text
you › pull octocat/Hello-World and summarise it
  ⚙ pull_repo repo=octocat/Hello-World
  ⚙ list_files repo=octocat/Hello-World
  ⚙ read_file repo=octocat/Hello-World path=README
<Jarvis's answer, citing files as path:line>
```

## What it can do

**Research across GitHub**

| Tool | What it does | Needs approval |
|---|---|---|
| `search_github_code` | Searches source code across **all public GitHub repositories** (`language:`, `repo:`, `org:`, `path:`, `filename:` qualifiers). Needs `GITHUB_TOKEN` | No |
| `search_github_repos` | Searches for repositories | No |
| `list_user_repos` | Lists a user's or organisation's repositories | No |
| `get_repo_info` | Description, stars, **license**, topics and default branch of any repository | No |
| `get_repo_tree` | Lists every file in any GitHub repository, without cloning it | No |
| `read_remote_file` | Reads a file or directory from any GitHub repository, without cloning it | No |

**Work locally**

| Tool | What it does | Needs approval |
|---|---|---|
| `pull_repo` | Clones or updates a repository: `owner/name` for GitHub, `host/owner/name` for gitlab.com, codeberg.org and bitbucket.org | No |
| `list_local_repos`, `list_files`, `read_file`, `search_code`, `git_log` | Explore cloned code | No |
| `edit_file` | Replaces an exact snippet in a file | **Yes** |
| `write_file` | Creates or overwrites a file | **Yes** |
| `run_command` | Installs, tests, builds (120 s timeout by default, up to 900 s). Dangerous commands are always blocked | **Yes** |
| `git_diff` | Shows the branch, status and uncommitted changes | No |

**Watch CI and see**

| Tool | What it does | Needs approval |
|---|---|---|
| `github_activity` | Open PRs and issues, recent CI runs and commits of a repository | No |
| `get_ci_failure` | Failed jobs and steps of a GitHub Actions run, with the log output before the first error | No |
| `look_at_screen` | Screenshot of your screen, for Claude to look at | **Yes** |
| `remember`, `forget` | Long-term notes across sessions | No |

**Ship**

| Tool | What it does | Needs approval |
|---|---|---|
| `commit_changes` | Commits on a feature branch. On the default branch it creates `jarvis/<summary>`; it never commits to `main` or `master` | **Yes** |
| `push_and_open_pr` | Pushes the feature branch and opens a **draft** pull request. Never pushes the default branch, never force-pushes, never merges | **Yes** |

## Setup

Requires Python 3.10 or later and `git`.

```bash
cd jarvis
python3 -m venv .venv && source .venv/bin/activate
pip install .

export ANTHROPIC_API_KEY=...   # or run `ant auth login`
export GITHUB_TOKEN=...        # code search, private repos, pushes and pull requests
```

GitHub token permissions:

- **Research only:** any token works for code search and public repositories. A fine-grained token with no repository access is enough.
- **Shipping changes:** a fine-grained token limited to *your* repositories, with **Contents: read and write** and **Pull requests: read and write**.

Jarvis sends the token as a header on each GitHub request and git command, never to other hosts, and never writes it to `.git/config`.

## Autonomous mode

Give Jarvis a goal and it works through it without asking:

```bash
jarvis --auto "Add a dark mode toggle to joshuawayzwright/wrightwayz-website"
jarvis --auto "Find how popular projects implement rate limiting for GitHub API clients and add it to acme/api"
jarvis --auto --max-steps 400 "Upgrade acme/api to the latest FastAPI and fix what breaks"
```

What it does:

1. **Understands** the target repository: README, structure, conventions, tests.
2. **Researches** prior art by searching code across GitHub, reading the best implementations and checking their licenses.
3. **Builds** the change in the codebase's style, with tests.
4. **Verifies** by installing dependencies and running tests and linters, and fixes failures.
5. **Ships** by committing to a feature branch and opening a draft pull request that lists what changed, how it was tested, its assumptions, and credits for adapted code.
6. **Reports** the PR link and anything left undone.

Every run is logged to `~/.jarvis/runs/<timestamp>.md`: the goal, each tool call and result, and Jarvis's messages. Long runs keep going past the context limit because the API summarises earlier context automatically (compaction).

**Guardrails stay on in autonomous mode:**

- Changes reach GitHub only as **draft pull requests on feature branches**. Jarvis never pushes or commits to the default branch, never force-pushes and never merges. You review and merge.
- Always blocked: `sudo`, deleting `/` or `~`, disk and power commands, piping downloads into a shell, `git push` outside `push_and_open_pr`, `git reset --hard origin`, `gh pr merge` and `gh repo delete`.
- **Licenses:** Jarvis checks licenses and credits sources. It won't copy GPL code into a project with a different license, or code with no license at all.
- `--max-steps` caps the run (default 250 in auto mode, 60 otherwise). Ctrl+C stops it at any time.

> **Run it somewhere disposable, or use `--sandbox`.** Autonomous mode runs commands from repositories it pulls, including their install scripts and tests, without asking. Use `--sandbox` (below), or a container, VM or cloud dev box rather than your main machine. Either way, use a GitHub token limited to the repositories you want it to change.

### Sandboxed commands

```bash
jarvis --team --auto --sandbox "..."                  # or JARVIS_SANDBOX=1
jarvis --issues acme/api --sandbox --sandbox-network none
```

With `--sandbox`, every `run_command`, Jarvis's own and every specialist's, runs in a fresh Docker container that is removed afterwards:

- **It sees only the repository**, mounted at `/work`. It never sees your home directory, SSH keys or environment variables, so `GITHUB_TOKEN` and `ANTHROPIC_API_KEY` stay out.
- **It's locked down:** it runs as your user ID, so files it creates are yours. Every Linux capability is dropped, `no-new-privileges` is set, and memory, CPU and process count are limited (4 GB, 2 CPUs, 512 processes).
- **Installs are cached per repository** in `~/.jarvis/sandbox-home/<repo>`, the container's home folder, so `pip install --user` or npm caches survive between commands.
- **Network:** `bridge` by default, so dependencies install; `--sandbox-network none` cuts it off completely.
- **Image:** `node:22-bookworm` by default (Node 22, Python 3, git, make and a C toolchain). Change it with `--sandbox-image` or `JARVIS_SANDBOX_IMAGE`. Jarvis pulls it on first use.
- **Timeouts kill the container**, not just the client.
- **What stays on the host:** the blocked-command list is still checked first, and Jarvis's own git operations (commit, push) still run on the host with the token only Jarvis holds.

It needs Docker (Docker Desktop, or Engine on Linux). If Docker isn't running, Jarvis says so and exits rather than falling back to running commands on your machine.

## Team mode: Jarvis and six specialists

With `--team`, Jarvis becomes the chief of a seven-agent crew. It plans, hands work to six specialists, checks what they report and tells you the outcome. Each specialist is its own Claude agent with its own instructions and a restricted set of tools.

| Agent | Role | Tools | Runs |
|---|---|---|---|
| **Jarvis** (chief) | Plans, delegates, checks reports, remembers, reports to you | Read-only GitHub and local tools, CI status, memory, `delegate` | |
| **Scout** | Research: prior art across GitHub, library docs, license checks | Remote GitHub search and reads, read-only MCP tools | In parallel |
| **Architect** | Design: reads the target repository and writes a file-by-file plan with a test plan | Remote and local reads | In parallel |
| **Medic** | CI and operations: diagnoses failing builds and repository health | `github_activity`, `get_ci_failure`, reads | In parallel |
| **Forge** | Build: edits code, installs dependencies, builds and runs tests | Reads, `write_file`, `edit_file`, `run_command` | One at a time |
| **Sentinel** | QA and security: reviews the diff, runs tests and linters, ends with `VERDICT: PASS` or `FAIL` | Reads, test edits, `run_command`, all MCP tools (e.g. a browser) | One at a time |
| **Herald** | Ship: updates docs, commits on a feature branch, opens the draft PR | Reads, docs edits, `commit_changes`, `push_and_open_pr` | One at a time |

```bash
jarvis --team                                    # interactive; /team shows the crew and the quality gate
jarvis --team --auto "Add rate limiting to acme/api"
jarvis --team --watch --fix                      # the crew fixes broken builds
export JARVIS_TEAM=1                             # make team mode the default
```

How the crew works:

- **Delegation.** Jarvis calls `delegate(agent, task)` with everything the specialist needs, including findings from the others. Specialists don't see each other's reports unless Jarvis passes them on.
- **Parallel recon.** When Jarvis delegates to several of Scout, Architect and Medic in one step, they run at the same time. Forge, Sentinel and Herald change things, so they run one at a time, and two assignments for the *same* specialist always queue. Ctrl+C during a parallel step returns at once; the specialists stop before their next request.
- **Failures stay contained.** A specialist that crashes, for example because the API is down, is rolled back to its last valid conversation, so its next assignment works. If Forge or Sentinel crashes, the gate is marked unverified.
- **Memory per specialist.** Each specialist keeps its conversation across assignments in a session, so "now fix issue 2" works. Jarvis can pass `fresh: true` to start one over; `/reset` clears everyone.
- **Quality gate, enforced on the code itself.** Jarvis fingerprints a repository by hashing every file except documentation, committed or not.
  - `commit_changes` checks the files about to be committed; `push_and_open_pr` checks the commit actually being pushed (HEAD), not the files on disk.
  - Either goes through only when the fingerprint matches the default branch (only docs changed) or code that Sentinel passed.
  - If code changes after verification by *any* route, it no longer matches and shipping is refused until Sentinel verifies again. Routes include a `sed` in `run_command`, an MCP tool, a run that crashed halfway, or edits left over after `/reset`.
  - **The base is pinned.** Jarvis records the default branch as the remote reports it, after a fetch, before any specialist command touches the repository. Moving a local ref later (for example `git fetch . X:refs/remotes/origin/main` or `git branch -f main`) can't make new code look like the base.
  - On `FAIL`, Jarvis sends the issues back to Forge and verifies again, up to three rounds.
- **A PASS needs proof.** Sentinel's report must end with `VERDICT: PASS`, and the verdict counts only if, in that same assignment:
  - a command that *invokes* a real test, lint or type-check runner exited 0. Examples: `pytest`, `python -m unittest`, `npm test`, `go test`, `cargo test`, `make check`, `ruff check`, `tsc`, or a project script such as `./scripts/test.sh`. It must be the last command, joined only by `&&`, as in `pip install -e . && pytest`. These don't count:
    - commands that only mention a runner (`echo pytest`, `cat tests/x.py`) or print its version or test list (`--version`, `--collect-only`, `--if-present`);
    - installs, or `cd` out of the repository;
    - anything whose failure is hidden by `; true`, `|| true` or a pipe;
  - Sentinel left the application code alone. Its edits are limited to tests, and a PASS from a Sentinel that changed non-test code is rejected;
  - the check ran on *exactly* the code present when Sentinel finished;
  - Sentinel ended normally. A PASS from a run cut short by the step limit or the budget is ignored.
- **Scoped writes.** Sentinel can write only test files (`tests/`, `test_*`, `*.test.*` and similar), and Herald only documentation (README, CHANGELOG, `*.md`, text under `docs/`). Paths are normalised first, so `tests/../src/app.py` is refused. `.mdx` files and `docs/requirements.txt` count as code. Specialists can't run git commands that commit, push or move refs (`commit`, `push`, `reset`, `stash`, `fetch`, `pull`, `branch`, `checkout`, `switch`, `symbolic-ref` and similar) through `run_command`; `status`, `diff`, `log` and `show` are fine. That rule is a speed bump; the pinned base and the HEAD check are what actually stop a disguised command. Only Forge changes application code.
- **MCP tools.** The chief and the specialists get only the MCP tools their servers mark read-only. `--sentinel-mcp playwright` (or `JARVIS_SENTINEL_MCP`) also gives Sentinel the write tools of the servers you name, for example a browser to click through a UI. The fingerprint gate still covers anything those tools change in the repository.
- **Known limit: gitignored files.** The fingerprint follows `.gitignore`, so a file it ignores (`.env`, `local_settings.py`, a patched `node_modules`) can make Sentinel's tests pass locally without being shipped. The PR then fails CI instead of being wrong silently, but review a PR that depends on local configuration with that in mind.
- **Separation of duties.** Jarvis can't edit, run commands or ship in team mode, and every specialist is limited to its own tools: a call outside them is refused.
- **Approvals.** Without `--yes` or `--auto`, each write, command and push still asks you, labelled with the specialist that wants it (`[Forge] Run in acme/api: pytest`). Approval prompts never overlap.
- **Visibility.** Specialists' tool calls appear in the terminal, web page and run log, prefixed with their name (`Scout ▸ search_github_code ...`).

### Models and cost

A team run makes more API calls than a solo run, because each specialist reads the code it works on. Every specialist uses Jarvis's model (`--model`) unless you choose another with `--team-models`. Each also has an effort level that fits its role: `medium` for Scout, Medic and Herald, `high` for the rest.

```bash
jarvis --team-models economy "..."                          # Scout, Medic and Herald on claude-sonnet-5-5
jarvis --team-models "economy,forge=claude-sonnet-5-5" "..."  # presets and overrides combine
export JARVIS_TEAM_MODELS="scout=claude-haiku-5-5"
```

`--team-models` turns on team mode. Keep Forge and Sentinel on your strongest model: they write and judge the code.

`/team` shows each agent's model, assignments, API requests and tokens used this session (input includes prompt-cache reads and writes). Autonomous runs write the same table to the end of the run log. Jarvis reports tokens, not dollars: multiply by your plan's prices for each model.

**Spending cap.** `--budget` (or `JARVIS_BUDGET`) stops Jarvis and every specialist once they have used that many tokens between them. It works in solo mode too.

```bash
jarvis --team --auto --budget 1.5M "..."     # also 500000 or 500k
```

- Every token counts toward the cap: input, prompt-cache reads and writes, and output. That's deliberately conservative, because cache reads cost much less than fresh input.
- Each agent checks the budget before each request. A specialist that hits the cap stops and reports what it has. Jarvis then stops before its next request and tells you how much was used. A request already in progress finishes, so a run can go over the cap by up to one response per agent working at that moment, at most three in a parallel step.

### Crew panel in the browser

In team mode, `jarvis --web --team` adds a crew panel above the chat. It shows:

- each agent's status: working (pulsing), done, error or idle;
- each agent's latest result, or Sentinel's verdict;
- tasks and tokens per agent;
- the quality-gate state;
- a budget meter, when `--budget` is set.

The panel refreshes every 2 seconds. On a phone it starts collapsed to a one-line summary (gate, who's working, budget); tap it to see the agents. It reads `GET /api/team`, which needs the same token as the rest of the page.

### Self-test

`--selftest` checks, end to end and with real API calls, that team mode works with your key, models and MCP setup:

```bash
jarvis --selftest                              # capped at 2M tokens
jarvis --selftest --team-models economy --budget 1M
```

1. Jarvis creates a small local repository (`selftest/stats`) under `~/.jarvis/selftest/<time>/`. It has a planted bug and a failing test, and no remote.
2. The crew gets one autonomous goal: find the bug, fix it, verify it, and commit on a feature branch without pushing. It works in `--auto` mode, so its writes, commands and commits run without asking you, all inside that folder.
3. Jarvis then checks the result itself, without relying on the crew's reports:
   - the fix is on a feature branch and `main` is untouched;
   - the working tree is clean;
   - the suite passes;
   - **the original tests pass on the new code**, so deleting or weakening a test can't fake a pass;
   - the run went Forge → Sentinel → Herald, so the quality gate was exercised.

It prints `SELF-TEST PASSED` or `FAILED` with each check and the crew table, and exits 0 or 1. The full run log is in the same folder. The self-test needs no GitHub token, and it uses its own memory file, so your notes are left alone.

## Issue autopilot and notifications

**Hand Jarvis an issue by labelling it.** The crew works each open issue labelled `jarvis` and opens a draft pull request that starts with `Closes #N`:

```bash
jarvis --issues acme/api acme/web                       # checks every 5 minutes, one issue per round
jarvis --issues acme/api --label ai-ready --per-poll 2 --interval 15 --budget 2M
```

- **The label is the permission.** On GitHub only people with triage access or higher can add labels, so the crew only works issues a maintainer has approved.
- **Only maintainers' issues, by default.** Authors can still edit an issue after it is labelled, so by default the autopilot works only issues opened by the repository's owners, members and collaborators. It records and skips others; `--any-author` includes them.
- **Issue text is still treated as data.** The crew reads it as a description of the change, not as instructions about how Jarvis operates. It ignores requests to reveal secrets or to change credentials, CI, permissions or settings. If an issue is unclear, unsafe, or not a code change, the crew changes nothing and explains why.
- **Each issue is worked once.** `~/.jarvis/autopilot.json` records every issue when it starts (`started`, then `done`, `failed` or `skipped`), so a restart never repeats work or spends twice. Delete an entry to retry that issue. If the file is unreadable, the autopilot refuses to start rather than guess. Every labelled open issue is read, across all pages.
- **Every safeguard of team mode applies.** That includes the evidence-backed quality gate, draft PRs only, and `--budget`, which applies to *each issue*. An issue that crashes is recorded and the autopilot moves on.

**Get told when work finishes.** `--notify URL` (or `JARVIS_NOTIFY`) sends a summary when one of these finishes: an autonomous run, a self-test, a watch-mode fix or an autopilot issue.

| URL | Sent as |
|---|---|
| `https://ntfy.sh/<your-topic>` (or your own ntfy server) | Phone push notification, with the title in a header |
| `https://hooks.slack.com/services/...` | Slack message (`{"text": ...}`) |
| `https://discord.com/api/webhooks/...` | Discord message (`{"content": ...}`) |

```bash
export JARVIS_NOTIFY=https://ntfy.sh/my-jarvis-7f3k   # pick a hard-to-guess topic: ntfy topics are public
jarvis --issues acme/api
```

Only the summary is sent, capped at 1,800 characters. URLs must use `https://`; `http://` is accepted only for localhost. A failed notification is reported and never stops the run.

## Plug in tools from GitHub (MCP)

Jarvis can use any [Model Context Protocol](https://modelcontextprotocol.io) server, local or hosted: the open-source tool ecosystem on GitHub. That includes browsers, documentation lookup, databases, Slack, Sentry, Figma, cloud consoles and thousands more. It reads the standard `mcpServers` config used by Claude Desktop, Cursor and most server READMEs, so you can paste a server's documented config in as-is.

```bash
pip install ".[mcp]"
cp mcp.example.json ~/.jarvis/mcp.json     # then edit to taste
jarvis                                     # starts the servers; /tools lists them
```

The starter config ([`mcp.example.json`](mcp.example.json)) includes these widely used servers:

| Server | What Jarvis gains | Runs with |
|---|---|---|
| [Playwright MCP](https://github.com/microsoft/playwright-mcp) | A real browser: open your site, click through it, check the UI after a change | `npx @playwright/mcp@latest` |
| [Context7](https://github.com/upstash/context7) | Up-to-date documentation for thousands of libraries, so code matches the current API | `npx -y @upstash/context7-mcp` |
| [Fetch](https://github.com/modelcontextprotocol/servers/tree/main/src/fetch) | Reads any web page as Markdown | `uvx mcp-server-fetch` |
| [Filesystem](https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem) | Read and write access to folders you choose (disabled in the example) | `npx -y @modelcontextprotocol/server-filesystem <folder>` |

How it works:

- Each server's tools appear to Claude as `mcp__<server>__<tool>`.
- Tools that their server marks **read-only** run freely. Every other MCP tool needs your approval, like `run_command`, unless you use `--yes` or `--auto`.
- Server output and errors go to `~/.jarvis/logs/mcp-<server>.log`. A server that fails to start is reported and skipped; the rest keep working.
- **Remote servers** connect by URL over streamable HTTP. Write `${VAR}` in the config to read tokens from environment variables, so secrets stay out of the file. Remote URLs must use `https://` (`http://` is accepted only for localhost). Legacy SSE-only servers aren't supported.

  ```json
  {"mcpServers": {"sentry": {"type": "http", "url": "https://mcp.sentry.dev/mcp",
                             "headers": {"Authorization": "Bearer ${SENTRY_TOKEN}"}}}}
  ```
- `--mcp-config <file>` uses a different config; `--no-mcp` starts none.
- Each server adds tool descriptions to every request, so enable the servers you use rather than dozens.

MCP servers are third-party programs that run on your machine with your permissions. Only add servers you trust, from their official repositories.

## CI doctor, watch mode and morning briefing

Jarvis reads GitHub Actions directly:

- `github_activity` shows a repository's open pull requests and issues, recent commits, and **the latest result of every workflow on the default branch**.
- `get_ci_failure` diagnoses what is failing *now*. It looks at the latest run of each workflow on the branch (the default branch unless you name one) and reports:
  - **CURRENT**, **ALREADY FIXED** (a newer run passed) or **INTERMITTENT** (identical code passed in another run, matched by commit or by file tree, so a merge commit still matches its pull request). An intermittent failure points to memory, timing, network or caching rather than a code bug.
  - The failure rate across the workflow's recent runs.
  - The failed jobs and steps, with **the log output leading up to the first error**. Repeated lines are collapsed, and timestamps and colour codes are stripped.

Fix a broken build end to end:

```bash
jarvis --auto "CI is failing on joshuawayzwright/ai-download-center. Find out why, fix it and open a PR."
```

**Watch mode** keeps an eye on your repositories and tells you when a default-branch build breaks or recovers. It checks every 5 minutes by default, and `--voice` speaks the alerts:

```bash
jarvis --watch                                  # your account's repositories active in the last 30 days
jarvis --watch my-org acme/api --interval 10    # owners and/or specific repositories
jarvis --watch --fix                            # and start an autonomous fix (draft PR) for each new failure
```

The first check reports what's already failing. After that, Jarvis only speaks up when something changes, so a broken build isn't announced every 5 minutes. With `--fix`, each failure gets a fresh autonomous run: it diagnoses first, stops if the failure is already fixed, and otherwise opens a draft PR.

For a **morning briefing**, use `--brief`. Jarvis leads with failing CI, pull requests waiting for review and new issues, then one line per active repository:

```bash
jarvis --brief                 # the GitHub account of your token
jarvis --brief --voice         # read aloud
```

The GitHub token is sent only to `api.github.com`. Log downloads redirect to a storage URL, which Jarvis fetches without the token.

## Web and phone

```bash
jarvis --web                                         # this computer only
jarvis --web --web-host 0.0.0.0                      # reachable from your phone on the same Wi-Fi
jarvis --web --web-host 0.0.0.0 --web-cert cert.pem --web-key key.pem   # HTTPS, needed for the phone's microphone
```

Jarvis prints a link that contains a secret token. Open it in any browser:

- Replies stream in as they're written. Tool calls show as they happen, and approvals appear as **Allow** and **Decline** buttons.
- **Voice in the browser:** tap 🎙 and speak, using your browser's own speech recognition. Tick "Speak replies" to hear answers sentence by sentence; code stays on screen. Nothing extra is installed, and on a phone this makes Jarvis a pocket assistant.
- Every request needs the token, which is compared in constant time. The server listens only on localhost unless you pass `--web-host`.
- Phones allow the microphone only over HTTPS. Over plain `http://` on your network, typing works but the mic button won't. For HTTPS, use a certificate with `--web-cert` and `--web-key` (`mkcert` makes locally trusted ones), or put Jarvis behind a tunnel that provides HTTPS, such as Tailscale Serve.
- Treat the link like a password. Anyone with it can ask Jarvis to act on your machine, subject to the same approvals.

## Screen vision

Ask about what's on your screen: "what's this error?", "why does this page look broken?", "match this design".

```bash
pip install ".[screen]"
```

The `look_at_screen` tool takes a screenshot, downscales it to 1568 px on the long edge and shows it to Claude. **Every screenshot asks for your approval, even with `--yes` or `--auto`**, because a screenshot can capture anything you have open. When nobody can answer (no terminal attached), screenshots are refused. On macOS, allow your terminal under System Settings > Privacy & Security > Screen Recording.

## Memory

Jarvis keeps long-term notes in `~/.jarvis/memory.md`: your preferences, your repositories, conventions and what it shipped. It saves them with its `remember` tool, removes them with `forget`, and reads them at the start of each session. The file is plain Markdown, so you can edit it by hand. `/memory` shows it, and `--no-memory` turns it off. Jarvis is told not to store secrets.

## Usage

```bash
jarvis                                   # interactive (/reset, /memory, /tools, /team, /exit)
jarvis "what changed in octocat/Hello-World this month?"   # one question, then exit
jarvis --yes "pull acme/api and run its tests"             # auto-approve writes and commands
jarvis --effort medium --model claude-sonnet-5-5 "..."     # cheaper and faster
```

| Option / variable | Default | Purpose |
|---|---|---|
| `--workspace`, `JARVIS_HOME` | `~/.jarvis/repos` | Where repositories are cloned |
| `--model`, `JARVIS_MODEL` | `claude-opus-5-5` | Claude model |
| `--effort` | `high` | Reasoning depth: `low` to `max` |
| `-y`, `--yes` | off | Approve edits, commands, commits and pushes without asking |
| `--auto` | off | Autonomous mode (implies `--yes`) |
| `--team`, `JARVIS_TEAM=1` | off | Team mode: Jarvis leads six specialist agents |
| `--team-models`, `JARVIS_TEAM_MODELS` | `--model` for all | Models per specialist, or `economy` |
| `--sentinel-mcp`, `JARVIS_SENTINEL_MCP` | none | MCP servers whose write tools Sentinel may use (e.g. `playwright`) |
| `--budget`, `JARVIS_BUDGET` | no cap | Stop after this many tokens across all agents (`500k`, `2M`) |
| `--selftest` | | Live end-to-end team check on a local repository with a planted bug |
| `--issues REPO ...`, `--label`, `--per-poll` | `jarvis`, 1 | Issue autopilot: the crew works labelled issues into draft PRs |
| `--notify`, `JARVIS_NOTIFY` | off | ntfy, Slack or Discord message when a run finishes |
| `--sandbox`, `--sandbox-image`, `--sandbox-network` | off, `node:22-bookworm`, `bridge` | Run commands in a locked-down Docker container |
| `--mcp-config` | `~/.jarvis/mcp.json` | MCP servers to start |
| `--no-mcp`, `--no-memory` | off | Turn off MCP servers or long-term memory |
| `--brief [OWNER]` | | Morning briefing across your repositories |
| `--watch [TARGET ...]`, `--interval`, `--fix` | 5 min | Watch default-branch builds; optionally auto-fix |
| `--web`, `--web-host`, `--web-port`, `--web-cert`, `--web-key` | localhost:8765 | Browser and phone interface |
| `--max-steps` | 60, or 250 with `--auto` | Agent steps per request |

When stdin is not a terminal (in scripts or CI, for example), writes and commands are **denied** unless you pass `--yes`.

## Voice mode

Talk to Jarvis and hear its replies.

```bash
pip install ".[voice]"
jarvis --voice
```

Press **Enter** to start talking and **Enter** again to stop. Jarvis transcribes what you said and does the work. Its reply **streams to the screen as it's written, and Jarvis starts speaking as soon as the first sentence is finished**, rather than waiting for the whole answer. Code blocks, tables and file lists stay on screen; Jarvis says "the code is on screen" instead of reading them out. You can still type messages; `/mute` and `/unmute` turn spoken replies off and on. Press Ctrl+C while it is speaking to stop it.

| Part | How it works | Cost and privacy |
|---|---|---|
| Speech to text | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) running on your machine. The model (about 150 MB for `base.en`) downloads on first use. | Free. Audio never leaves your computer. |
| Spoken replies: `system` | Your operating system's voice through pyttsx3 (Windows SAPI5, macOS NSSpeechSynthesizer, eSpeak on Linux) | Free and offline, but robotic |
| Spoken replies: `elevenlabs` | The ElevenLabs API. The default voice is George, a British male premade voice | Natural voice. Uses ElevenLabs credits, and the reply text is sent to ElevenLabs |

```bash
export ELEVENLABS_API_KEY=...                  # picks ElevenLabs automatically
jarvis --voice --voice-id <voice id>           # any voice from your ElevenLabs library
jarvis --voice --tts system                    # force the free offline voice
jarvis --voice --whisper-model small.en        # more accurate, slower
jarvis --voice --whisper-model small --language es   # other languages
jarvis --voice "pull octocat/Hello-World and summarise it"   # one question, spoken answer
```

| Option / variable | Default | Purpose |
|---|---|---|
| `--wake` | off | Hands-free mode with the "Hey Jarvis" wake word (implies `--voice`) |
| `--wake-threshold` | `0.5` | Wake-word sensitivity, 0 to 1 |
| `--tts` | `auto` | `elevenlabs` if `ELEVENLABS_API_KEY` is set, otherwise `system`. Use `none` for text only |
| `--voice-id`, `ELEVENLABS_VOICE_ID` | George (`JBFqnCBsd6RMkjVDRZzb`) | ElevenLabs voice |
| `--whisper-model`, `JARVIS_WHISPER_MODEL` | `base.en` | `tiny.en` is fastest; `small.en` and `medium.en` are more accurate |
| `--language` | auto-detect | Spoken language code for multilingual Whisper models |

### Hands-free: "Hey Jarvis"

```bash
jarvis --wake
```

Say **"Hey Jarvis"**, then your request, in one breath or after the chime. Jarvis records until you stop talking (about 1.2 seconds of quiet), answers, then listens for **5 seconds for a follow-up** that needs no wake word. If you say nothing, it goes back to waiting for "Hey Jarvis".

- Say **"never mind"** to cancel, or **"goodbye"** (or press Ctrl+C) to quit.
- Wake-word detection uses [openWakeWord](https://github.com/dscripka/openWakeWord)'s `hey_jarvis` model. It runs on your computer and is included in the `voice` extra, so nothing extra downloads.
- `--wake-threshold` sets the sensitivity (default `0.5`). Lower it to about `0.3` if Jarvis misses you; raise it to `0.7` if it wakes when nobody called it.
- Jarvis stops listening while it works and speaks, so it never hears its own voice.
- File writes and commands still need a keypress to approve. A misheard "yes" should never run a shell command.

System requirements:

- **Microphone access** for your terminal (macOS asks the first time).
- **PortAudio:** bundled with the `sounddevice` package on Windows and macOS. On Debian or Ubuntu, run `sudo apt install libportaudio2`.
- **eSpeak** for the `system` voice on Linux only: `sudo apt install espeak-ng`.

Each spoken reply is capped at about 1,500 characters, which also limits ElevenLabs usage. Anything longer finishes with "The rest is on screen."

## How it works

- **Agent loop** (`jarvis/agent.py`): a manual tool-use loop on the Messages API, with adaptive thinking, prompt caching of the conversation prefix, and server-side refusal fallbacks (`fallbacks: "default"`). All tool results for one turn go back in a single message. The loop stops after 40 steps.
- **Team** (`jarvis/team.py`): the six specialist roles, their prompts and tool allowlists, parallel delegation on a thread pool, and the quality gate, applied as middleware on every specialist tool call.
- **Tools** (`jarvis/tools.py`): every tool input is checked against its schema before it runs. File paths are resolved and confined to the repository, and writes into `.git` are refused. Output is capped so large files and searches don't flood the context.
- **Wake word** (`jarvis/wake.py`): openWakeWord scores each 80 ms microphone frame for "hey Jarvis". A loudness-based end-of-speech detector, calibrated to the room's background noise, decides when you have finished talking.
- **Voice** (`jarvis/voice.py`): push-to-talk recording with `sounddevice`, local transcription with faster-whisper, and speech output through pyttsx3 or ElevenLabs. In voice mode the system prompt asks Claude for short, speakable replies and to allow for transcription errors.
- **GitHub** (`jarvis/github.py`): uses the REST API through the Python standard library and `git` for clones, with partial clones (`--filter=blob:none`) for speed. Repository names and refs are validated to block path traversal and git option injection.

## Safety notes

- `run_command` runs a real shell in the cloned repository. Code you pull from GitHub is untrusted: read a repository's scripts before approving commands such as `npm install` or `make`.
- Jarvis pushes only feature branches and opens only draft pull requests. It never pushes or merges your default branch.

## Tests

```bash
pip install ".[dev]"
pytest -q
```

The tests run offline and need no voice packages. They exercise every tool against temporary git repositories (including commit, push and pull request against a local remote), the safety guard, and the agent, voice and wake-word loops with a fake Claude client, microphone and speaker.
