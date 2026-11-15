"""Command-line entry point: `jarvis` (interactive) or `jarvis "question"` (one shot)."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import anthropic

from . import voice
from .agent import DEFAULT_MODEL, Jarvis
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


def listen(io: VoiceIO) -> str:
    print(f"{RED}● Listening...{RESET} press Enter to stop.")
    audio = io.recorder.record()
    print(f"{DIM}Transcribing...{RESET}")
    return io.transcriber.transcribe(audio)


def chat_loop(jarvis: Jarvis, io: VoiceIO | None, workspace: Path, read: Callable[[str], str] = input) -> int:
    commands = "/reset, /exit" + (", /mute, /unmute" if io else "")
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
            reply = run_turn(jarvis, prompt)
        except KeyboardInterrupt:
            print("\nInterrupted. That turn was discarded.")
            del jarvis.messages[checkpoint:]
            continue
        if io and reply:
            speak(io, reply)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jarvis", description="AI engineering assistant that pulls and works with code from GitHub.")
    parser.add_argument("prompt", nargs="*", help="Ask one question and exit. Omit for interactive mode.")
    parser.add_argument("--workspace", type=Path, default=Path(os.environ.get("JARVIS_HOME", Path.home() / ".jarvis")) / "repos", help="Where repositories are cloned (default ~/.jarvis/repos).")
    parser.add_argument("--model", default=os.environ.get("JARVIS_MODEL", DEFAULT_MODEL))
    parser.add_argument("--effort", default="high", choices=["low", "medium", "high", "xhigh", "max"])
    parser.add_argument("-y", "--yes", action="store_true", help="Auto-approve file writes and shell commands.")
    group = parser.add_argument_group("voice")
    group.add_argument("--voice", action="store_true", help="Talk to Jarvis: push-to-talk input and spoken replies.")
    group.add_argument("--tts", default="auto", choices=["auto", "system", "elevenlabs", "none"], help="Speech output. auto = ElevenLabs if ELEVENLABS_API_KEY is set, else the system voice.")
    group.add_argument("--voice-id", default=os.environ.get("ELEVENLABS_VOICE_ID", voice.ELEVENLABS_DEFAULT_VOICE), help="ElevenLabs voice ID (default: George).")
    group.add_argument("--whisper-model", default=os.environ.get("JARVIS_WHISPER_MODEL", "base.en"), help="Whisper model: tiny.en, base.en, small.en, medium.en, or a multilingual size such as small.")
    group.add_argument("--language", default=None, help="Spoken language code (e.g. en). Default: auto-detect.")
    args = parser.parse_args(argv)

    io: VoiceIO | None = None
    if args.voice:
        try:
            io = build_voice(args)
        except voice.VoiceUnavailable as err:
            print(f"Voice mode unavailable: {err}", file=sys.stderr)
            return 2

    args.workspace.mkdir(parents=True, exist_ok=True)
    jarvis = Jarvis(
        ctx=ToolContext(workspace=args.workspace.resolve(), approve=make_approver(args.yes)),
        model=args.model,
        effort=args.effort,
        voice_mode=io is not None,
        on_text=lambda text: print(f"\n{text}\n"),
        on_tool=lambda line: print(f"{DIM}  ⚙ {line}{RESET}"),
    )

    if args.prompt:
        reply = run_turn(jarvis, " ".join(args.prompt))
        if io and reply:
            speak(io, reply)
        return 0 if reply is not None else 1

    return chat_loop(jarvis, io, args.workspace)


if __name__ == "__main__":
    sys.exit(main())
