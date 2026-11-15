"""Command-line entry point: `jarvis` (interactive) or `jarvis "question"` (one shot)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import anthropic

from .agent import DEFAULT_MODEL, Jarvis
from .tools import ToolContext

DIM, CYAN, RESET = "\033[2m", "\033[36m", "\033[0m"


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


def run_turn(jarvis: Jarvis, prompt: str) -> bool:
    """Run one turn. Returns False on an error that should end a one-shot run."""
    checkpoint = len(jarvis.messages)
    try:
        jarvis.ask(prompt)
        return True
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
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jarvis", description="AI engineering assistant that pulls and works with code from GitHub.")
    parser.add_argument("prompt", nargs="*", help="Ask one question and exit. Omit for interactive mode.")
    parser.add_argument("--workspace", type=Path, default=Path(os.environ.get("JARVIS_HOME", Path.home() / ".jarvis")) / "repos", help="Where repositories are cloned (default ~/.jarvis/repos).")
    parser.add_argument("--model", default=os.environ.get("JARVIS_MODEL", DEFAULT_MODEL))
    parser.add_argument("--effort", default="high", choices=["low", "medium", "high", "xhigh", "max"])
    parser.add_argument("-y", "--yes", action="store_true", help="Auto-approve file writes and shell commands.")
    args = parser.parse_args(argv)

    args.workspace.mkdir(parents=True, exist_ok=True)
    jarvis = Jarvis(
        ctx=ToolContext(workspace=args.workspace.resolve(), approve=make_approver(args.yes)),
        model=args.model,
        effort=args.effort,
        on_text=lambda text: print(f"\n{text}\n"),
        on_tool=lambda line: print(f"{DIM}  ⚙ {line}{RESET}"),
    )

    if args.prompt:
        return 0 if run_turn(jarvis, " ".join(args.prompt)) else 1

    print(f"{CYAN}Jarvis online.{RESET} Workspace: {args.workspace}. Commands: /reset, /exit")
    while True:
        try:
            prompt = input(f"{CYAN}you ›{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not prompt:
            continue
        if prompt in ("/exit", "/quit"):
            return 0
        if prompt == "/reset":
            jarvis.reset()
            print("Conversation cleared.")
            continue
        checkpoint = len(jarvis.messages)
        try:
            run_turn(jarvis, prompt)
        except KeyboardInterrupt:
            print("\nInterrupted. That turn was discarded.")
            del jarvis.messages[checkpoint:]


if __name__ == "__main__":
    sys.exit(main())
