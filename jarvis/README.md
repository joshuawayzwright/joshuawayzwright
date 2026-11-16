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

> **Run it somewhere disposable.** Autonomous mode runs commands from repositories it pulls, including their install scripts and tests, without asking. Use a container, VM or cloud dev box rather than your main machine, and a GitHub token limited to the repositories you want it to change.

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

### Dashboard

Add `--watch` to get a live dashboard next to the chat. Jarvis prints its link (`/dashboard?token=…`), and the chat page links to it.

```bash
jarvis --web --watch                              # your account's repositories active in the last 30 days
jarvis --web --watch my-org acme/api --interval 10
```

- **CI on default branches:** every watched repository with the latest result of each workflow, failing ones first, and links to the run logs. Each workflow shows its last 10 results and pass rate, so you can see a flaky workflow from one that is newly broken. Jarvis checks every `--interval` minutes; **Check now** checks at once.
- **Open pull requests:** across the watched repositories, most recently updated first, with drafts marked.
- **Fix with Jarvis:** on a failing workflow, opens the chat with a fix request filled in. You read it and press Send, so nothing runs until you do.
- **Activity:** what Jarvis is doing right now: your requests, each tool call, approvals and how each turn ended. When Jarvis is waiting for an approval, the status at the top reads **Needs your approval** and opens the chat.
- **Alerts:** builds that broke or recovered since the dashboard started.
- **Session:** model, effort, approval mode, tools (including MCP), whether Jarvis is working, and tokens used this session (input, output and cached).
- **Memory:** the most recent long-term notes.

The dashboard reads GitHub through your `GITHUB_TOKEN` (two requests per repository per check) and never calls Claude, so viewing it costs no tokens. It refreshes every 15 seconds while open. Without `--watch`, it shows the session and memory panels only. `--fix` is terminal-only; on the web, use the Fix with Jarvis button.

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
jarvis                                   # interactive (/reset, /memory, /tools, /exit)
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
| `--mcp-config` | `~/.jarvis/mcp.json` | MCP servers to start |
| `--no-mcp`, `--no-memory` | off | Turn off MCP servers or long-term memory |
| `--brief [OWNER]` | | Morning briefing across your repositories |
| `--watch [TARGET ...]`, `--interval`, `--fix` | 5 min | Watch default-branch builds; optionally auto-fix. With `--web`, feeds the dashboard |
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
