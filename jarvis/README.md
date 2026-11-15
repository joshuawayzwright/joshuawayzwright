# Jarvis

An AI engineering assistant for your terminal. Jarvis pulls code from GitHub, reads and searches it, and answers questions about it. It can also edit files and run commands, but only after you approve each one. It runs on the Claude API (`claude-opus-5-5` by default).

Example session (the tool calls are what Jarvis prints; the answer text depends on the model):

```text
you › pull octocat/Hello-World and summarise it
  ⚙ pull_repo repo=octocat/Hello-World
  ⚙ list_files repo=octocat/Hello-World
  ⚙ read_file repo=octocat/Hello-World path=README
<Jarvis's answer, citing files as path:line>
```

## What it can do

| Tool | What it does | Needs approval |
|---|---|---|
| `search_github_repos` | Searches GitHub (supports `user:`, `org:`, `language:` and other qualifiers) | No |
| `list_user_repos` | Lists a user's or organisation's repositories | No |
| `pull_repo` | Clones a repository into the workspace, or fetches and fast-forwards an existing clone. Can check out a branch, tag or commit | No |
| `list_local_repos` | Lists repositories already cloned | No |
| `list_files` | Lists tracked files, filtered by directory or glob | No |
| `read_file` | Reads a file with line numbers, by line range | No |
| `search_code` | Searches with a regex (`git grep`) | No |
| `git_log` | Shows recent commits for a repository or path | No |
| `write_file` | Creates or overwrites a file in a cloned repository | **Yes** |
| `run_command` | Runs a shell command in a repository, such as tests or a build (120 s timeout) | **Yes** |

## Setup

Requires Python 3.10 or later and `git`.

```bash
cd jarvis
python3 -m venv .venv && source .venv/bin/activate
pip install .

export ANTHROPIC_API_KEY=...   # or run `ant auth login`
export GITHUB_TOKEN=...        # optional: private repos and higher API rate limits
```

Use a fine-grained GitHub token with **read-only Contents** access to the repositories you want Jarvis to reach. Jarvis sends the token as a header on each git command and never writes it to `.git/config`.

## Usage

```bash
jarvis                                   # interactive session (/reset clears history, /exit quits)
jarvis "what changed in octocat/Hello-World this month?"   # one question, then exit
jarvis --yes "pull acme/api and run its tests"             # auto-approve writes and commands
jarvis --effort medium --model claude-sonnet-5-5 "..."     # cheaper and faster
```

| Option / variable | Default | Purpose |
|---|---|---|
| `--workspace`, `JARVIS_HOME` | `~/.jarvis/repos` | Where repositories are cloned |
| `--model`, `JARVIS_MODEL` | `claude-opus-5-5` | Claude model |
| `--effort` | `high` | Reasoning depth: `low` to `max` |
| `-y`, `--yes` | off | Approve `write_file` and `run_command` without asking |

When stdin is not a terminal (in scripts or CI, for example), writes and commands are **denied** unless you pass `--yes`.

## How it works

- **Agent loop** (`jarvis/agent.py`): a manual tool-use loop on the Messages API, with adaptive thinking, prompt caching of the conversation prefix, and server-side refusal fallbacks (`fallbacks: "default"`). All tool results for one turn go back in a single message. The loop stops after 40 steps.
- **Tools** (`jarvis/tools.py`): every tool input is checked against its schema before it runs. File paths are resolved and confined to the repository, and writes into `.git` are refused. Output is capped so large files and searches don't flood the context.
- **GitHub** (`jarvis/github.py`): uses the REST API through the Python standard library and `git` for clones, with partial clones (`--filter=blob:none`) for speed. Repository names and refs are validated to block path traversal and git option injection.

## Safety notes

- `run_command` runs a real shell in the cloned repository. Code you pull from GitHub is untrusted: read a repository's scripts before approving commands such as `npm install` or `make`.
- Jarvis never pushes. Writes stay in your local clone until you commit and push them yourself.

## Tests

```bash
pip install ".[dev]"
pytest -q
```

The tests run offline. They exercise every tool against a temporary git repository and drive the agent loop with a fake Claude client.
