"""Long-term memory: notes Jarvis keeps about the user and their projects across sessions."""

from __future__ import annotations

import time
from pathlib import Path

MAX_NOTES = 200
MAX_NOTE_CHARS = 500
MAX_PROMPT_CHARS = 12_000


class Memory:
    """A plain Markdown list in ~/.jarvis/memory.md that the user can read and edit by hand."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def notes(self) -> list[str]:
        if not self.path.is_file():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        return [line[2:].strip() for line in lines if line.startswith("- ") and line[2:].strip()]

    def _save(self, notes: list[str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        body = "".join(f"- {note}\n" for note in notes)
        self.path.write_text("# Jarvis memory\n\nEdit or delete lines freely.\n\n" + body, encoding="utf-8")

    def remember(self, note: str) -> str:
        note = " ".join(note.split())[:MAX_NOTE_CHARS]
        if not note:
            return "Nothing to remember."
        notes = self.notes()
        if any(note.lower() in existing.lower() for existing in notes):
            return "Already remembered."
        notes.append(f"{note} ({time.strftime('%Y-%m-%d')})")
        self._save(notes[-MAX_NOTES:])
        return f"Remembered. {len(notes[-MAX_NOTES:])} notes in memory."

    def forget(self, text: str) -> str:
        notes = self.notes()
        matches = [n for n in notes if text.lower() in n.lower()]
        if not matches:
            return f"No note contains '{text}'."
        if len(matches) > 1:
            listed = "\n".join(f"- {m}" for m in matches[:10])
            return f"{len(matches)} notes match; be more specific:\n{listed}"
        notes.remove(matches[0])
        self._save(notes)
        return f"Forgot: {matches[0]}"

    def prompt_section(self) -> str:
        notes = self.notes()
        if not notes:
            return ""
        listed = "\n".join(f"- {note}" for note in notes)[-MAX_PROMPT_CHARS:]
        return (
            "\n\nWhat you remember from earlier sessions (your own notes, which may be out of date; "
            "check facts about code before relying on them):\n" + listed
        )
