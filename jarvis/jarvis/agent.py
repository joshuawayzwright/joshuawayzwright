"""The Jarvis agent loop on the Claude Messages API."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import anthropic

from .tools import TOOL_SCHEMAS, ToolContext, execute

DEFAULT_MODEL = "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
MAX_STEPS = 40

SYSTEM_PROMPT = """You are Jarvis, a sharp, calm engineering assistant. You work with code that lives on GitHub.

How you work:
- To answer questions about a repository, pull it with pull_repo first, then explore with list_files, search_code and read_file. Read the code before making claims about it; cite files as path:line.
- If the user names a project without an owner, find it with search_github_repos or list_user_repos before pulling.
- Pulling again fetches the latest commits, so do it when the user asks about recent changes.
- write_file and run_command change things on the user's machine. Use them only when the user asked for a change or a check, and explain what you are about to do. If the user declines, accept that and continue without it.
- Say plainly when something is unknown, a tool failed, or you did not verify a claim.

Style: lead with the answer, keep it concise, use Markdown and code blocks. A touch of dry wit is welcome; flattery is not."""


Printer = Callable[[str], None]


@dataclass
class Jarvis:
    ctx: ToolContext
    client: Any = None
    model: str = field(default_factory=lambda: os.environ.get("JARVIS_MODEL", DEFAULT_MODEL))
    effort: str = "high"
    on_text: Printer = print
    on_tool: Printer = print
    messages: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.client is None:
            self.client = anthropic.Anthropic()

    def reset(self) -> None:
        self.messages.clear()

    def _request(self) -> Any:
        return self.client.beta.messages.create(
            model=self.model,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            tools=TOOL_SCHEMAS,
            messages=self.messages,
            thinking={"type": "adaptive"},
            output_config={"effort": self.effort},
            # Cache the growing conversation prefix across agent steps.
            cache_control={"type": "ephemeral"},
            # On a safety-classifier refusal, the API retries on a suitable fallback model.
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )

    def ask(self, prompt: str) -> str:
        """Send one user turn and run tools until Claude finishes. Returns the final text."""
        self.messages.append({"role": "user", "content": prompt})
        final_text = ""

        for _ in range(MAX_STEPS):
            response = self._request()
            # Append the full content (thinking, fallback and tool_use blocks included), unchanged.
            self.messages.append({"role": "assistant", "content": response.content})

            texts = [b.text for b in response.content if b.type == "text" and b.text.strip()]
            for text in texts:
                self.on_text(text)
            if texts:
                final_text = texts[-1]

            if response.stop_reason == "refusal":
                self.on_text("[Jarvis declined this request.]")
                return final_text
            if response.stop_reason == "pause_turn":
                continue
            if response.stop_reason == "max_tokens":
                self.on_text("[Response hit the token limit; ask me to continue.]")
                return final_text
            if response.stop_reason != "tool_use":
                return final_text

            results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                self.on_tool(f"{block.name} {_preview(block.input)}")
                content, is_error = execute(self.ctx, block.name, block.input)
                results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": content, "is_error": is_error}
                )
            # All results for one assistant turn go back in a single user message.
            self.messages.append({"role": "user", "content": results})

        self.on_text(f"[Stopped after {MAX_STEPS} steps. Ask me to continue if needed.]")
        return final_text


def _preview(data: object, limit: int = 120) -> str:
    if not isinstance(data, dict):
        return ""
    parts = []
    for key, value in data.items():
        text = str(value).replace("\n", " ")
        parts.append(f"{key}={text[:60] + '…' if len(text) > 60 else text}")
    joined = " ".join(parts)
    return joined[:limit]
