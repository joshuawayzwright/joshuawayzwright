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
COMPACTION_BETA = "compact-2026-01-12"
DEFAULT_MAX_STEPS = 60
AUTO_MAX_STEPS = 250

SYSTEM_PROMPT = """You are Jarvis, a sharp, calm engineering agent. You work with code on GitHub, and you can research, change, test and ship it.

Your reach:
- All of GitHub: search_github_repos finds projects; search_github_code searches source code across every public repository; get_repo_info, get_repo_tree and read_remote_file inspect any repository without cloning it.
- pull_repo clones GitHub repositories (owner/name) and also gitlab.com, codeberg.org and bitbucket.org ones (host/owner/name) for deep work: list_files, search_code, read_file, git_log.
- Changing code: edit_file for targeted changes, write_file for new files, run_command for installs, tests and builds, git_diff to review, commit_changes to commit on a feature branch, push_and_open_pr to push and open a draft pull request.

How you work:
- Read code before making claims about it; cite files as path:line.
- If the user names a project without an owner, find it with search_github_repos or list_user_repos first.
- To build a feature, look for prior art: search GitHub for how good projects solve the same problem, read their implementations, then adapt the best approach to the target codebase's conventions. Prefer well-maintained, permissively licensed sources.
- Reusing code from another project: check its license with get_repo_info. Copy or closely adapt code only when the license allows it in the target project (MIT, BSD, Apache-2.0 and ISC are generally fine; GPL code must not go into a project under a different license without the user's say-so; no license means all rights reserved, so learn from it but don't copy it). Credit every adapted source (repo, path, license) in the commit message and the pull request.
- Match the existing code style, and add or update tests. Run the project's tests before committing, and say honestly if they fail or don't exist.
- Memory: use remember to save durable facts (the user's preferences, their repositories, decisions and conventions, what you shipped) and forget to remove wrong ones. Don't store secrets.
- MCP tools (named mcp__<server>__<tool>) come from extra tool servers the user has plugged in, such as a browser or documentation lookup. Use them when they fit the task.
- Writes, commands, commits and pushes may need the user's approval. If the user declines, accept that and continue without it.
- Say plainly when something is unknown, a tool failed, or you did not verify a claim.

Style: lead with the answer, keep it concise, use Markdown and code blocks. A touch of dry wit is welcome; flattery is not."""

VOICE_PROMPT = """

Voice mode is on: the user is speaking to you, and your final reply is read aloud. Their words come from speech recognition, so read past small transcription errors (a repository name may be misheard; check with search_github_repos when unsure). Keep the spoken part short: two to four plain sentences, no tables or headings. Put code, file lists and long detail in code blocks: those are shown on screen, not spoken."""

AUTO_PROMPT = """

Autonomous mode is on. The user has handed you a goal and is not watching; work through it end to end without asking questions.
1. Understand: pull the target repository, read its README, structure, conventions and tests.
2. Research: search GitHub for prior art and proven implementations of what you need; read the best two or three; check their licenses.
3. Plan: decide the approach and the smallest set of changes that fully achieves the goal. Where the goal is ambiguous, choose the most reasonable interpretation and record the assumption.
4. Build: make the changes, matching the codebase's style, with tests.
5. Verify: install dependencies and run the tests and linters; fix what fails. Never weaken or skip a test to get a pass.
6. Ship: review git_diff, commit_changes with a clear message, then push_and_open_pr with a description covering what changed, why, how it was tested, assumptions, and credits for adapted code. Pull requests are drafts for the user to review; you never merge.
7. Report: finish with a short summary: the PR link, what you built, test results, and anything left undone.
If something blocks you (missing permissions, failing tests you cannot fix), stop working around it, ship what is solid if anything is, and explain the blocker in the report. Destructive and system-level commands are blocked; don't try to get around the blocks."""


Printer = Callable[[str], None]


@dataclass
class Jarvis:
    ctx: ToolContext
    client: Any = None
    model: str = field(default_factory=lambda: os.environ.get("JARVIS_MODEL", DEFAULT_MODEL))
    effort: str = "high"
    voice_mode: bool = False
    autonomous: bool = False
    max_steps: int = DEFAULT_MAX_STEPS
    on_text: Printer = print
    on_tool: Printer = print
    on_result: Callable[[str, str, bool], None] = lambda name, content, is_error: None
    mcp: Any = None  # an MCPManager, when MCP servers are configured
    messages: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.client is None:
            self.client = anthropic.Anthropic()
        # Fixed for the session, so the cached prompt prefix stays valid; new notes appear next session.
        self._memory_section = self.ctx.memory.prompt_section() if self.ctx.memory else ""
        self._tools = TOOL_SCHEMAS + (self.mcp.schemas() if self.mcp else [])

    def reset(self) -> None:
        self.messages.clear()

    def system_prompt(self) -> str:
        return (SYSTEM_PROMPT + (AUTO_PROMPT if self.autonomous else "")
                + (VOICE_PROMPT if self.voice_mode else "") + self._memory_section)

    def _request(self) -> Any:
        return self.client.beta.messages.create(
            model=self.model,
            max_tokens=16000,
            system=self.system_prompt(),
            tools=self._tools,
            messages=self.messages,
            thinking={"type": "adaptive"},
            output_config={"effort": self.effort},
            # Cache the growing conversation prefix across agent steps.
            cache_control={"type": "ephemeral"},
            # Long runs: the API summarises earlier context server-side when it grows large.
            context_management={"edits": [{"type": "compact_20260112"}]},
            # On a safety-classifier refusal, the API retries on a suitable fallback model.
            betas=[FALLBACK_BETA, COMPACTION_BETA],
            fallbacks="default",
        )

    def ask(self, prompt: str) -> str:
        """Send one user turn and run tools until Claude finishes. Returns the final text."""
        self.messages.append({"role": "user", "content": prompt})
        final_text = ""

        for _ in range(self.max_steps):
            response = self._request()
            # Append the full content (thinking, compaction, fallback and tool_use blocks), unchanged.
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
                content, is_error = self._dispatch(block.name, block.input)
                self.on_result(block.name, content, is_error)
                results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": content, "is_error": is_error}
                )
            # All results for one assistant turn go back in a single user message.
            self.messages.append({"role": "user", "content": results})

        self.on_text(f"[Stopped after {self.max_steps} steps. Ask me to continue if needed.]")
        return final_text


    def _dispatch(self, name: str, tool_input: Any) -> tuple[str, bool]:
        if self.mcp is not None and self.mcp.handles(name):
            if not isinstance(tool_input, dict):
                return "Error: tool input must be a JSON object.", True
            # Tools marked read-only by their server run freely; others need approval like run_command.
            if not self.mcp.is_read_only(name) and not self.ctx.approve(f"Use {name} {_preview(tool_input)}"):
                return "The user declined this tool call.", False
            return self.mcp.call(name, tool_input)
        return execute(self.ctx, name, tool_input)


def _preview(data: object, limit: int = 120) -> str:
    if not isinstance(data, dict):
        return ""
    parts = []
    for key, value in data.items():
        text = str(value).replace("\n", " ")
        parts.append(f"{key}={text[:60] + '…' if len(text) > 60 else text}")
    joined = " ".join(parts)
    return joined[:limit]
