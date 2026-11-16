#!/usr/bin/env python3
"""Validate the marketing and content engine.

Checks:
  * every agent and skill file has front matter with a name and a description;
  * every draft names a known brand and channel, lives in that brand's folder,
    and has a valid status;
  * no approved draft still contains a placeholder or lacks a review block;
  * no WrightWayz draft links to a SOLO website, and no draft makes
    WrightWayz charity or tax-deductibility claims.

Standard library only. Exit code 1 on any failure.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MARKETING = ROOT / "marketing"

BRANDS = {"solo", "wrightwayz", "ai-download-center"}
CHANNELS = {
    "linkedin", "x", "facebook", "instagram", "threads", "blog",
    "email", "video-short", "video-long", "gbp",
}
STATUSES = {"draft", "approved", "needs-changes", "published"}
PLACEHOLDER = re.compile(r"\[(NEEDS (INFO|OWNER APPROVAL|ASSET)|UNSUBSCRIBE LINK|POSTAL ADDRESS)")
SOLO_DOMAIN = "thesoloserviceprovider.com.au"
# Claims WrightWayz must never make (see marketing/brands/wrightwayz.md).
WRIGHTWAYZ_BANNED = re.compile(
    r"registered charity|tax[- ]deductible|\bDGR\b|deductible gift", re.IGNORECASE
)


def front_matter(text: str) -> dict[str, str] | None:
    """Return simple top-level `key: value` pairs, or None if absent."""
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    if end == -1:
        return None
    fields: dict[str, str] = {}
    for line in text[4:end].splitlines():
        match = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if match:
            fields[match.group(1)] = match.group(2).strip()
    return fields


def check_definitions(errors: list[str]) -> None:
    files = sorted((ROOT / ".claude" / "agents").glob("*.md"))
    files += sorted((ROOT / ".claude" / "skills").glob("*/SKILL.md"))
    if not files:
        errors.append(".claude: no agent or skill definitions found")
    for path in files:
        fm = front_matter(path.read_text(encoding="utf-8"))
        rel = path.relative_to(ROOT)
        if fm is None:
            errors.append(f"{rel}: missing front matter")
            continue
        for key in ("name", "description"):
            if not fm.get(key):
                errors.append(f"{rel}: front matter needs '{key}'")
        if path.name != "SKILL.md" and fm.get("name") != path.stem:
            errors.append(f"{rel}: name '{fm.get('name')}' should match the file name")


def check_draft(path: Path, errors: list[str]) -> None:
    rel = path.relative_to(ROOT)
    text = path.read_text(encoding="utf-8")
    fm = front_matter(text)
    if fm is None:
        errors.append(f"{rel}: missing front matter")
        return

    brand = fm.get("brand", "")
    channel = fm.get("channel", "")
    status = fm.get("status", "")
    folder_brand = path.relative_to(MARKETING / "drafts").parts[0]

    if brand not in BRANDS:
        errors.append(f"{rel}: unknown brand '{brand}'")
    elif brand != folder_brand:
        errors.append(f"{rel}: brand '{brand}' is filed under '{folder_brand}'")
    if channel not in CHANNELS:
        errors.append(f"{rel}: unknown channel '{channel}'")
    if status not in STATUSES:
        errors.append(f"{rel}: invalid status '{status}'")

    if status in {"approved", "published"}:
        if PLACEHOLDER.search(text):
            errors.append(f"{rel}: marked {status} but still contains a placeholder")
        if "## Review:" not in text:
            errors.append(f"{rel}: marked {status} without a review block")

    if brand == "wrightwayz":
        body = text.split("## Review:")[0]
        if SOLO_DOMAIN in body:
            errors.append(f"{rel}: WrightWayz draft links to the SOLO business site")
        for match in WRIGHTWAYZ_BANNED.finditer(body):
            # Honest negations ("not tax-deductible", "isn't a registered charity") are allowed.
            before = body[max(0, match.start() - 30):match.start()].lower()
            if re.search(r"\bnot\b|n't\b", before):
                continue
            errors.append(f"{rel}: WrightWayz draft makes a prohibited claim: '{match.group(0)}'")


def check_drafts(errors: list[str]) -> None:
    drafts = MARKETING / "drafts"
    if not drafts.is_dir():
        return
    for path in sorted(drafts.rglob("*.md")):
        if "packs" in path.relative_to(drafts).parts:
            continue  # pack indexes are not publishable drafts
        check_draft(path, errors)


def main() -> int:
    errors: list[str] = []
    for required in ("README.md", "channels.md", "compliance.md"):
        if not (MARKETING / required).is_file():
            errors.append(f"marketing/{required}: missing")
    for brand in sorted(BRANDS):
        if not (MARKETING / "brands" / f"{brand}.md").is_file():
            errors.append(f"marketing/brands/{brand}.md: missing")
    check_definitions(errors)
    check_drafts(errors)

    for error in errors:
        print(f"error: {error}")
    if errors:
        print(f"\n{len(errors)} problem(s) found.")
        return 1
    print("Marketing engine checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
