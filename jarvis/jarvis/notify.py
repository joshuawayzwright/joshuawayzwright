"""Tell the user when a long run finishes: ntfy, Slack or Discord, by webhook URL.

`--notify URL` (or JARVIS_NOTIFY) picks the format from the URL:

- hooks.slack.com/...                  Slack incoming webhook, {"text": ...}
- discord.com/api/webhooks/...         Discord webhook, {"content": ...}
- anything else (e.g. https://ntfy.sh/<topic>)   plain-text POST with a Title header (ntfy)

A failed notification is reported and never stops Jarvis. Only the summary text is sent: no tokens,
no repository contents beyond what the summary says.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable

MAX_CHARS = 1_800  # under Discord's 2,000-character limit; plenty for a summary
LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")

Post = Callable[[urllib.request.Request], None]


def _post(request: urllib.request.Request) -> None:
    with urllib.request.urlopen(request, timeout=15) as response:
        response.read()


def validate_url(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    if parts.scheme == "https" and parts.hostname:
        return url
    if parts.scheme == "http" and parts.hostname in LOCAL_HOSTS:
        return url
    raise ValueError("notification URLs must use https:// (http:// only for localhost)")


def kind(url: str) -> str:
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    path = urllib.parse.urlsplit(url).path
    if host == "hooks.slack.com":
        return "slack"
    if host in ("discord.com", "discordapp.com") and path.startswith("/api/webhooks/"):
        return "discord"
    return "ntfy"


def build_request(url: str, title: str, message: str) -> urllib.request.Request:
    text = message.strip()
    if len(text) > MAX_CHARS:
        text = text[: MAX_CHARS - 1] + "…"
    style = kind(url)
    if style == "slack":
        body, headers = json.dumps({"text": f"*{title}*\n{text}"}), {"Content-Type": "application/json"}
    elif style == "discord":
        body, headers = json.dumps({"content": f"**{title}**\n{text}"}), {"Content-Type": "application/json"}
    else:
        # ntfy reads the title from a header; header values must be latin-1, so drop anything else.
        safe_title = title.encode("latin-1", "ignore").decode("latin-1")
        body, headers = text, {"Title": safe_title, "Content-Type": "text/plain; charset=utf-8"}
    headers["User-Agent"] = "jarvis-agent"
    return urllib.request.Request(url, data=body.encode("utf-8"), headers=headers, method="POST")


class Notifier:
    def __init__(self, url: str, post: Post = _post, report: Callable[[str], None] = print) -> None:
        self.url = validate_url(url)
        self.post = post
        self.report = report

    def send(self, title: str, message: str) -> bool:
        try:
            self.post(build_request(self.url, title, message))
            return True
        except (urllib.error.URLError, OSError, ValueError) as err:
            self.report(f"Notification failed ({kind(self.url)}): {err}")
            return False
