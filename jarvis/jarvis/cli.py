"""Command-line entry point: `jarvis` (interactive) or `jarvis "question"` (one shot)."""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import anthropic

from . import github, mcp_bridge, team, voice, wake, watch, web
from .agent import AUTO_MAX_STEPS, DEFAULT_MAX_STEPS, DEFAULT_MODEL, Jarvis
from .memory import Memory
from .tools import ToolContext

DIM, CYAN, RED, RESET = "\033[2m", "\033[36m", "\033[31m", "\033[0m"


def make_approver(auto_yes: bool):
    def approve(question: str) -> bool:
        if auto_yes:
            print(f"{DIM}  auto-approved: {question}{RESET}")
            return True
        if not sys.stdin.isatty():
            print(f"{DIM}  denied (non-interactive; pass --yes to allow): {question}{RESET}")
            return False
        answer = input(f"  {question} [y/N] ").strip().lower()
        return answer in ("y", "yes")

    return approve


class RunLog:
    """Markdown record of an autonomous run: the goal, every tool call and result, and the outcome."""

    def __init__(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / time.strftime("%Y%m%d-%H%M%S.md")
        self._write(f"# Jarvis run {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

    def _write(self, text: str) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(text + "\n")

    def goal(self, text: str) -> None:
        self._write(f"## Goal\n\n{text}\n\n## Steps\n")

    def text(self, text: str) -> None:
        self._write(f"\n**Jarvis:** {text}\n")

    def tool(self, line: str) -> None:
        self._write(f"- `{line}`")

    def crew(self, status: str) -> None:
        self._write(f"\n## Crew\n\n```\n{status}\n```")

    def result(self, name: str, content: object, is_error: bool) -> None:
        if not isinstance(content, str):
            content = "[image and text content]"
        head = content.strip().splitlines()[:6]
        marker = "ERROR " if is_error else ""
        self._write("  ```\n  " + marker + "\n  ".join(line[:200] for line in head) + "\n  ```")


def run_turn(jarvis: Jarvis, prompt: str) -> str | None:
    """Run one turn. Returns the final reply text, or None if the Claude API call failed."""
    checkpoint = len(jarvis.messages)
    try:
        return jarvis.ask(prompt)
    except anthropic.AuthenticationError:
        print("Authentication failed. Set ANTHROPIC_API_KEY or run `ant auth login`.", file=sys.stderr)
    except anthropic.RateLimitError:
        print("Rate limited by the Claude API. Wait a moment and try again.", file=sys.stderr)
    except anthropic.APIStatusError as err:
        print(f"Claude API error {err.status_code}: {err.message}", file=sys.stderr)
    except anthropic.APIConnectionError:
        print("Could not reach the Claude API. Check your network.", file=sys.stderr)
    # Roll back the failed turn so the conversation stays valid for the next request.
    del jarvis.messages[checkpoint:]
    return None


@dataclass
class VoiceIO:
    recorder: voice.Recorder
    transcriber: voice.Transcriber
    speaker: voice.Speaker
    muted: bool = False
    _speech: voice.SpeechQueue | None = None

    @property
    def speech(self) -> voice.SpeechQueue:
        if self._speech is None:
            self._speech = voice.SpeechQueue(self.speaker, on_error=lambda m: print(f"{DIM}  {m}{RESET}"))
        return self._speech


def build_voice(args: argparse.Namespace) -> VoiceIO:
    """Set up microphone, speech recognition and speech output. Raises VoiceUnavailable with a fix."""
    recorder = voice.PushToTalkRecorder()
    print(f"{DIM}Loading speech model '{args.whisper_model}' (the first run downloads it)...{RESET}")
    transcriber = voice.WhisperTranscriber(args.whisper_model, args.language)

    tts = args.tts
    if tts == "auto":
        tts = "elevenlabs" if os.environ.get("ELEVENLABS_API_KEY") else "system"
    speaker: voice.Speaker
    if tts == "elevenlabs":
        key = os.environ.get("ELEVENLABS_API_KEY")
        if not key:
            raise voice.VoiceUnavailable("--tts elevenlabs needs the ELEVENLABS_API_KEY environment variable.")
        speaker = voice.ElevenLabsSpeaker(key, voice_id=args.voice_id)
    elif tts == "system":
        try:
            speaker = voice.SystemSpeaker()
        except voice.VoiceUnavailable as err:
            if args.tts == "system":
                raise
            print(f"{DIM}{err} Replies will be shown, not spoken.{RESET}")
            speaker = voice.NullSpeaker()
    else:
        speaker = voice.NullSpeaker()
    return VoiceIO(recorder, transcriber, speaker)


def speak(io: VoiceIO, reply: str) -> None:
    if io.muted or not reply.strip():
        return
    try:
        io.speaker.say(voice.speakable(reply))
    except voice.VoiceUnavailable as err:
        print(f"{DIM}  (could not speak the reply: {err}){RESET}")
    except KeyboardInterrupt:
        print(f"{DIM}  (stopped speaking){RESET}")


def talk_turn(jarvis: Jarvis, io: VoiceIO, prompt: str) -> str | None:
    """Run a turn, speaking the reply sentence by sentence while it streams in."""
    if io.muted:
        return run_turn(jarvis, prompt)
    segmenter = voice.SentenceSegmenter()
    printer = jarvis.on_delta

    def on_delta(chunk: str) -> None:
        printer(chunk)
        for sentence in segmenter.feed(chunk):
            io.speech.say(sentence)

    jarvis.on_delta = on_delta
    try:
        reply = run_turn(jarvis, prompt)
    except KeyboardInterrupt:
        io.speech.cancel()
        raise
    finally:
        jarvis.on_delta = printer
    try:
        for sentence in segmenter.flush():
            io.speech.say(sentence)
        io.speech.wait()  # finish talking before listening again, so Jarvis never hears itself
    except KeyboardInterrupt:
        io.speech.cancel()
        print(f"{DIM}  (stopped speaking){RESET}")
    return reply


def listen(io: VoiceIO) -> str:
    print(f"{RED}● Listening...{RESET} press Enter to stop.")
    audio = io.recorder.record()
    print(f"{DIM}Transcribing...{RESET}")
    return io.transcriber.transcribe(audio)


def chat_loop(jarvis: Jarvis, io: VoiceIO | None, workspace: Path, read: Callable[[str], str] = input) -> int:
    commands = "/reset, /memory, /tools, " + ("/team, " if jarvis.team else "") + "/exit" + (", /mute, /unmute" if io else "")
    print(f"{CYAN}Jarvis online.{RESET} Workspace: {workspace}. Commands: {commands}")
    if io:
        print("Voice mode: press Enter to talk, press Enter again to stop. You can still type messages.")
    label = f"{CYAN}🎙  Enter to talk, or type ›{RESET} " if io else f"{CYAN}you ›{RESET} "

    while True:
        try:
            prompt = read(label).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if io and not prompt:
            try:
                prompt = listen(io)
            except KeyboardInterrupt:
                print("\nRecording cancelled.")
                continue
            if not prompt:
                print("I didn't catch that. Try again.")
                continue
            print(f"{CYAN}you (voice) ›{RESET} {prompt}")
        if not prompt:
            continue
        if prompt in ("/exit", "/quit"):
            return 0
        if prompt == "/memory":
            notes = jarvis.ctx.memory.notes() if jarvis.ctx.memory else []
            print("\n".join(f"- {n}" for n in notes) if notes else "Memory is empty.")
            if jarvis.ctx.memory:
                print(f"{DIM}Stored in {jarvis.ctx.memory.path}{RESET}")
            continue
        if prompt == "/tools":
            print(f"{len(jarvis._tools)} tools. MCP servers: {jarvis.mcp.summary() if jarvis.mcp else 'none'}")
            continue
        if prompt == "/team":
            print(jarvis.team.status() if jarvis.team else "Team mode is off. Start Jarvis with --team.")
            continue
        if prompt == "/reset":
            jarvis.reset()
            print("Conversation cleared.")
            continue
        if io and prompt in ("/mute", "/unmute"):
            io.muted = prompt == "/mute"
            print("Spoken replies off." if io.muted else "Spoken replies on.")
            continue

        checkpoint = len(jarvis.messages)
        try:
            run_turn(jarvis, prompt) if io is None else talk_turn(jarvis, io, prompt)
        except KeyboardInterrupt:
            print("\nInterrupted. That turn was discarded.")
            del jarvis.messages[checkpoint:]
            continue


def wake_loop(jarvis: Jarvis, io: VoiceIO, listener: wake.WakeWordListener) -> int:
    """Hands-free conversation: "Hey Jarvis" wakes it; follow-ups within a few seconds need no wake word."""
    print(f"{CYAN}Jarvis online, hands-free.{RESET} Say \"Hey Jarvis\" and then your request.")
    print(f"{DIM}After each answer you have 5 seconds to ask a follow-up without the wake word. "
          f"Say \"goodbye\" or press Ctrl+C to quit.{RESET}")

    def woke() -> None:
        print(f"{RED}● Listening...{RESET}")

    follow_up = False
    while True:
        try:
            if follow_up:
                print(f"{DIM}  (listening for a follow-up...){RESET}")
                audio = listener.listen_for_follow_up()
                if len(audio) == 0:
                    follow_up = False
                    print(f"{DIM}Waiting for \"Hey Jarvis\"...{RESET}")
                    continue
            else:
                audio = listener.wait_for_command(on_wake=woke)
            print(f"{DIM}Transcribing...{RESET}")
            prompt = wake.strip_wake_word(io.transcriber.transcribe(audio))
        except KeyboardInterrupt:
            print()
            return 0

        command = wake.normalise(prompt)
        if not command:
            print("I didn't catch that.")
            follow_up = False
            continue
        print(f"{CYAN}you (voice) ›{RESET} {prompt}")
        if command in wake.EXIT_PHRASES:
            speak(io, "Goodbye.")
            return 0
        if command in wake.CANCEL_PHRASES:
            follow_up = False
            continue

        checkpoint = len(jarvis.messages)
        try:
            reply = talk_turn(jarvis, io, prompt)
        except KeyboardInterrupt:
            print("\nInterrupted. That turn was discarded.")
            del jarvis.messages[checkpoint:]
            follow_up = False
            continue
        follow_up = reply is not None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jarvis", description="AI engineering assistant that pulls and works with code from GitHub.")
    parser.add_argument("prompt", nargs="*", help="Ask one question and exit. Omit for interactive mode.")
    home = Path(os.environ.get("JARVIS_HOME", Path.home() / ".jarvis"))
    parser.add_argument("--workspace", type=Path, default=home / "repos", help="Where repositories are cloned (default ~/.jarvis/repos).")
    parser.add_argument("--mcp-config", type=Path, default=home / "mcp.json", help="MCP servers config in the standard mcpServers format (default ~/.jarvis/mcp.json).")
    parser.add_argument("--no-mcp", action="store_true", help="Don't start MCP servers.")
    parser.add_argument("--no-memory", action="store_true", help="Don't load or save long-term memory (~/.jarvis/memory.md).")
    parser.add_argument("--model", default=os.environ.get("JARVIS_MODEL", DEFAULT_MODEL))
    parser.add_argument("--effort", default="high", choices=["low", "medium", "high", "xhigh", "max"])
    parser.add_argument("-y", "--yes", action="store_true", help="Auto-approve file writes and shell commands.")
    parser.add_argument("--team", action="store_true", default=os.environ.get("JARVIS_TEAM") == "1", help="Team mode: Jarvis becomes the chief of a seven-agent crew and delegates to six specialists (Scout, Architect, Medic, Forge, Sentinel, Herald). Also JARVIS_TEAM=1.")
    parser.add_argument("--team-models", default=os.environ.get("JARVIS_TEAM_MODELS", ""), metavar="SPEC", help="Team mode: models per specialist, e.g. 'scout=claude-sonnet-5-5,herald=claude-haiku-5-5'. 'economy' runs Scout, Medic and Herald on claude-sonnet-5-5 and can be combined: 'economy,forge=...'. Others use --model. Implies --team. Also JARVIS_TEAM_MODELS.")
    parser.add_argument("--auto", action="store_true", help="Autonomous agent: works through the goal end to end (research, build, test, commit, open a draft PR) without asking. Implies --yes. Logs to ~/.jarvis/runs/.")
    parser.add_argument("--brief", nargs="?", const="", metavar="OWNER", help="Morning briefing: what needs your attention across your GitHub repositories (open PRs, new issues, failing CI). Optionally name a user or organisation; defaults to the token's account. Combine with --voice to hear it.")
    parser.add_argument("--watch", nargs="*", metavar="TARGET", help="Watch mode: announce when a default-branch build breaks or recovers. Targets are owner/name repositories or owners (their repositories active in the last 30 days); none means the token's account.")
    parser.add_argument("--interval", type=float, default=5, help="Watch mode: minutes between checks (default 5).")
    parser.add_argument("--fix", action="store_true", help="Watch mode: when a build breaks, run an autonomous fix that opens a draft PR. Implies --auto.")
    group_web = parser.add_argument_group("web and phone")
    group_web.add_argument("--web", action="store_true", help="Serve a chat page with streaming replies, approvals and browser voice. Opens on this computer only unless --web-host is set.")
    group_web.add_argument("--web-host", default="127.0.0.1", help="Address to listen on. Use 0.0.0.0 to reach Jarvis from your phone on the same network.")
    group_web.add_argument("--web-port", type=int, default=8765)
    group_web.add_argument("--web-cert", type=Path, help="TLS certificate (PEM) to serve HTTPS. Phones only allow the microphone over HTTPS.")
    group_web.add_argument("--web-key", type=Path, help="TLS private key (PEM) for --web-cert.")
    parser.add_argument("--max-steps", type=int, default=None, help=f"Max agent steps per request (default {DEFAULT_MAX_STEPS}, or {AUTO_MAX_STEPS} with --auto).")
    group = parser.add_argument_group("voice")
    group.add_argument("--voice", action="store_true", help="Talk to Jarvis: push-to-talk input and spoken replies.")
    group.add_argument("--wake", action="store_true", help='Hands-free: say "Hey Jarvis" instead of pressing Enter. Implies --voice.')
    group.add_argument("--wake-threshold", type=float, default=0.5, help="Wake word sensitivity, 0-1. Lower hears you more easily but triggers falsely more often. Default 0.5.")
    group.add_argument("--tts", default="auto", choices=["auto", "system", "elevenlabs", "none"], help="Speech output. auto = ElevenLabs if ELEVENLABS_API_KEY is set, else the system voice.")
    group.add_argument("--voice-id", default=os.environ.get("ELEVENLABS_VOICE_ID", voice.ELEVENLABS_DEFAULT_VOICE), help="ElevenLabs voice ID (default: George).")
    group.add_argument("--whisper-model", default=os.environ.get("JARVIS_WHISPER_MODEL", "base.en"), help="Whisper model: tiny.en, base.en, small.en, medium.en, or a multilingual size such as small.")
    group.add_argument("--language", default=None, help="Spoken language code (e.g. en). Default: auto-detect.")
    args = parser.parse_args(argv)
    try:
        args.team_models = team.parse_models(args.team_models)
    except ValueError as err:
        parser.error(f"--team-models: {err}")
    if args.team_models:
        args.team = True
    if args.fix:
        if args.watch is None:
            parser.error("--fix works with --watch")
        args.auto = True

    io: VoiceIO | None = None
    listener: wake.WakeWordListener | None = None
    if args.wake and not args.prompt:
        args.voice = True
    if args.voice:
        try:
            io = build_voice(args)
            if args.wake and not args.prompt:
                listener = wake.WakeWordListener(threshold=args.wake_threshold)
        except voice.VoiceUnavailable as err:
            print(f"Voice mode unavailable: {err}", file=sys.stderr)
            return 2

    args.workspace.mkdir(parents=True, exist_ok=True)
    mcp = None if args.no_mcp else start_mcp(args.mcp_config, args.workspace.parent / "logs")
    try:
        return run(args, io, listener, mcp)
    finally:
        if mcp:
            mcp.close()


def start_mcp(config: Path, log_dir: Path) -> mcp_bridge.MCPManager | None:
    try:
        servers, warnings = mcp_bridge.load_config(config)
    except mcp_bridge.MCPUnavailable as err:
        print(f"{DIM}{err}{RESET}", file=sys.stderr)
        return None
    for warning in warnings:
        print(f"{DIM}{warning}{RESET}", file=sys.stderr)
    if not servers:
        return None
    try:
        manager = mcp_bridge.MCPManager(servers, log_dir=log_dir)
    except mcp_bridge.MCPUnavailable as err:
        print(f"{DIM}{err}{RESET}", file=sys.stderr)
        return None
    print(f"{DIM}Starting MCP servers: {', '.join(s.name for s in servers)}...{RESET}")
    manager.start()
    for error in manager.errors:
        print(f"{DIM}{error} (log: {log_dir}){RESET}", file=sys.stderr)
    print(f"{DIM}MCP tools: {manager.summary()}{RESET}")
    return manager


def briefing_prompt(owner: str) -> str:
    today = time.strftime("%A %d %B %Y")
    return (
        f"Give me my briefing for {today}. List the repositories of {owner} with list_user_repos and focus on "
        "those pushed in the last 7 days. For each, use github_activity. Lead with what needs action: failing CI "
        "on a default branch (use get_ci_failure to say briefly why), pull requests waiting for review, and new "
        "issues. Then give one line per other active repository. Be brief; skip repositories with nothing to report. "
        "End by offering to fix the most urgent problem."
    )


def _lan_address() -> str:
    import socket

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("192.0.2.1", 80))  # TEST-NET address: no packet is sent for a UDP connect
            return sock.getsockname()[0]
    except OSError:
        return "your-computer-ip"


def run_web(args: argparse.Namespace, jarvis: Jarvis) -> int:
    import ssl

    if bool(args.web_cert) != bool(args.web_key):
        print("--web-cert and --web-key go together.", file=sys.stderr)
        return 2
    session = web.WebSession(jarvis, auto_approve=args.yes or args.auto)
    try:
        server, token = web.serve(session, args.web_host, args.web_port)
    except OSError as err:
        print(f"Can't listen on {args.web_host}:{args.web_port}: {err}", file=sys.stderr)
        return 1
    scheme = "http"
    if args.web_cert:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(args.web_cert, args.web_key)
        server.socket = context.wrap_socket(server.socket, server_side=True)
        scheme = "https"
    host = _lan_address() if args.web_host in ("0.0.0.0", "::") else args.web_host
    print(f"{CYAN}Jarvis web is running.{RESET} Open this link (it contains your secret token, keep it private):")
    print(f"  {scheme}://{host}:{args.web_port}/?token={token}")
    if args.web_host not in ("127.0.0.1", "localhost", "::1"):
        print(f"{DIM}Reachable from other devices on your network."
              f"{'' if scheme == 'https' else ' Without --web-cert the connection is unencrypted and phones block the microphone.'}{RESET}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        server.server_close()
    return 0


def run_watch(args: argparse.Namespace, jarvis: Jarvis, io: VoiceIO | None) -> int:
    repos = [t for t in args.watch if "/" in t]
    owners = [t for t in args.watch if "/" not in t]
    if not args.watch:
        try:
            owners = [github.authenticated_login()]
        except github.GitHubError as err:
            print(f"Watch mode needs targets or a GitHub token: {err}", file=sys.stderr)
            return 1
    try:
        watcher = watch.Watcher(repos, owners)
    except github.GitHubError as err:
        print(str(err), file=sys.stderr)
        return 1

    def announce(alert: watch.Alert) -> None:
        colour = RED if alert.kind == "failing" else CYAN
        print(f"{colour}{time.strftime('%H:%M')} {alert.message()}{RESET}")
        if io:
            speak(io, alert.message().split(" http")[0])

    def fix(alert: watch.Alert) -> None:
        print(f"{DIM}Starting an autonomous fix for {alert.repo} ({alert.workflow})...{RESET}")
        jarvis.reset()
        if run_turn(jarvis, watch.fix_prompt(alert)) is None:
            print(f"{DIM}The fix attempt stopped with an error; watching continues.{RESET}")

    print(f"{CYAN}Jarvis is watching{RESET} {', '.join(repos + owners)} every {args.interval:g} min. Ctrl+C stops.")
    try:
        watch.watch_loop(watcher, announce, report=lambda m: print(f"{DIM}{m}{RESET}"),
                         interval_s=args.interval * 60, on_failure=fix if args.fix else None)
    except KeyboardInterrupt:
        print()
    return 0


def run(args: argparse.Namespace, io: VoiceIO | None, listener: wake.WakeWordListener | None,
        mcp: mcp_bridge.MCPManager | None) -> int:
    log = RunLog(args.workspace.parent / "runs") if args.auto else None

    streaming = {"active": False}

    def show_delta(chunk: str) -> None:
        if not streaming["active"]:
            print()
            streaming["active"] = True
        print(chunk, end="", flush=True)

    def show_text(text: str) -> None:
        if streaming["active"]:
            print("\n")  # the block has already streamed to the screen
            streaming["active"] = False
        else:
            print(f"\n{text}\n")
        if log:
            log.text(text)

    def show_tool(line: str) -> None:
        print(f"{DIM}  ⚙ {line}{RESET}")
        if log:
            log.tool(line)

    jarvis = Jarvis(
        ctx=ToolContext(
            workspace=args.workspace.resolve(),
            approve=make_approver(args.yes or args.auto),
            memory=None if args.no_memory else Memory(args.workspace.parent / "memory.md"),
            confirm_private=make_approver(False),  # screenshots always ask; refused when nobody can answer
        ),
        mcp=mcp,
        model=args.model,
        effort=args.effort,
        voice_mode=io is not None,
        autonomous=args.auto,
        team_mode=args.team,
        team_models=args.team_models,
        max_steps=args.max_steps or (AUTO_MAX_STEPS if args.auto else DEFAULT_MAX_STEPS),
        on_text=show_text,
        on_delta=show_delta,
        on_tool=show_tool,
        on_result=log.result if log else (lambda name, content, is_error: None),
    )
    if jarvis.team:
        print(f"{CYAN}Team mode:{RESET} Jarvis leads Scout, Architect, Medic, Forge, Sentinel and Herald. /team shows the crew.")
    if args.auto:
        print(f"{RED}Autonomous mode:{RESET} Jarvis will edit, run commands, commit and open draft PRs without asking. "
              f"Destructive commands are blocked, and it never pushes the default branch or merges. Ctrl+C stops it.")
        print(f"{DIM}Run log: {log.path}{RESET}" if log else "")

    if args.watch is not None:
        return run_watch(args, jarvis, io)
    if args.web:
        return run_web(args, jarvis)

    if args.brief is not None:
        try:
            args.prompt = [briefing_prompt(args.brief or github.authenticated_login())]
        except github.GitHubError as err:
            print(f"Briefing needs a GitHub account: pass --brief <owner> or set GITHUB_TOKEN. ({err})", file=sys.stderr)
            return 1

    if args.prompt:
        goal = " ".join(args.prompt)
        if log:
            log.goal(goal)
        reply = run_turn(jarvis, goal) if io is None else talk_turn(jarvis, io, goal)
        if log and jarvis.team:
            log.crew(jarvis.team.status())
        return 0 if reply is not None else 1

    if io and listener:
        return wake_loop(jarvis, io, listener)
    return chat_loop(jarvis, io, args.workspace)


if __name__ == "__main__":
    sys.exit(main())
