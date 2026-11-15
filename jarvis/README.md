# Jarvis

An AI engineering assistant for your terminal. Jarvis pulls code from GitHub, reads and searches it, and answers questions about it. It can also edit files and run commands, but only after you approve each one. It runs on the Claude API (`claude-opus-5-5` by default), and you can talk to it by voice.

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

## Voice mode

Talk to Jarvis and hear its replies.

```bash
pip install ".[voice]"
jarvis --voice
```

Press **Enter** to start talking and **Enter** again to stop. Jarvis transcribes what you said, does the work, prints its full reply and reads a short spoken version aloud. Code blocks, tables and file lists stay on screen and are not read out. You can still type messages; `/mute` and `/unmute` turn spoken replies off and on. Press Ctrl+C while it is speaking to stop it.

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
- Jarvis never pushes. Writes stay in your local clone until you commit and push them yourself.

## Tests

```bash
pip install ".[dev]"
pytest -q
```

The tests run offline and need no voice packages. They exercise every tool against a temporary git repository, and drive the agent loop and the voice loop with a fake Claude client, microphone and speaker.
