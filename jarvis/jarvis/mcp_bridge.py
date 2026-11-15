"""Plug in any MCP server: the open-source tool ecosystem on GitHub (browsers, docs, databases, ...).

Servers are configured in the standard `mcpServers` JSON format used by Claude Desktop, Cursor and
most MCP READMEs, so a server's documented config can be pasted in as-is. Each server runs as a
subprocess over stdio; its tools are offered to Claude as `mcp__<server>__<tool>`.
"""

from __future__ import annotations

import asyncio
import builtins
import json
import os
import re
import threading
from concurrent.futures import Future
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PREFIX = "mcp__"
CALL_TIMEOUT_S = 120
START_TIMEOUT_S = 60
MAX_RESULT_CHARS = 30_000


class MCPUnavailable(Exception):
    """MCP support cannot start; the message says what to install or fix."""


@dataclass
class ServerConfig:
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    cwd: str | None = None


def load_config(path: Path) -> tuple[list[ServerConfig], list[str]]:
    """Read an mcpServers config. Returns the stdio servers and warnings about skipped entries."""
    if not path.is_file():
        return [], []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as err:
        raise MCPUnavailable(f"{path} is not valid JSON: {err}") from err
    servers, warnings = [], []
    for name, spec in (data.get("mcpServers") or {}).items():
        if not isinstance(spec, dict) or spec.get("disabled"):
            continue
        if not re.match(r"^[A-Za-z0-9_-]{1,30}$", name):
            warnings.append(f"Skipped MCP server '{name}': use letters, digits, - and _ (max 30).")
            continue
        if "command" not in spec:
            warnings.append(f"Skipped MCP server '{name}': only local (command) servers are supported, not URL servers.")
            continue
        servers.append(ServerConfig(
            name=name,
            command=str(spec["command"]),
            args=[str(a) for a in spec.get("args", [])],
            env={str(k): str(v) for k, v in (spec.get("env") or {}).items()},
            cwd=spec.get("cwd"),
        ))
    return servers, warnings


def _field(obj: Any, snake: str, camel: str, default: Any = None) -> Any:
    """Read a field from MCP SDK 2.x (snake_case) or 1.x (camelCase) models."""
    value = getattr(obj, snake, None)
    return getattr(obj, camel, default) if value is None else value


def tool_name(server: str, tool: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", tool)
    return f"{PREFIX}{server}__{safe}"[:64]


def format_result(result: Any) -> tuple[str, bool]:
    """Turn an MCP CallToolResult into text for Claude."""
    parts: list[str] = []
    for item in getattr(result, "content", None) or []:
        kind = getattr(item, "type", "")
        if kind == "text":
            parts.append(item.text)
        elif kind == "image":
            parts.append(f"[image: {getattr(item, 'mime_type', None) or getattr(item, 'mimeType', 'image')}]")
        elif kind == "resource_link":
            parts.append(f"[resource: {getattr(item, 'uri', '')}]")
        elif kind == "resource":
            resource = getattr(item, "resource", None)
            parts.append(getattr(resource, "text", None) or f"[resource: {getattr(resource, 'uri', '')}]")
        else:
            parts.append(f"[{kind or 'unknown'} content]")
    structured = _field(result, "structured_content", "structuredContent")
    if not parts and structured is not None:
        parts.append(json.dumps(structured, indent=2, default=str))
    text = "\n".join(parts) or "(no output)"
    if len(text) > MAX_RESULT_CHARS:
        text = text[:MAX_RESULT_CHARS] + f"\n... [truncated {len(text) - MAX_RESULT_CHARS} characters]"
    return text, bool(_field(result, "is_error", "isError", False))


@dataclass
class _Tool:
    server: str
    name: str
    read_only: bool
    schema: dict[str, Any]


class MCPManager:
    """Runs MCP servers on a background event loop and exposes their tools synchronously."""

    def __init__(self, servers: list[ServerConfig], log_dir: Path | None = None) -> None:
        try:
            from mcp import ClientSession, StdioServerParameters  # noqa: F401
        except ImportError as err:
            raise MCPUnavailable('MCP support needs the mcp package: pip install ".[mcp]"') from err
        self.servers = servers
        self.log_dir = log_dir
        self.tools: dict[str, _Tool] = {}
        self.sessions: dict[str, Any] = {}
        self.errors: list[str] = []
        self._stop: asyncio.Event | None = None
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, name="jarvis-mcp", daemon=True)
        self._tasks: list[Future] = []

    # -- lifecycle ------------------------------------------------------------------------------

    def start(self) -> None:
        self._thread.start()
        asyncio.run_coroutine_threadsafe(self._make_stop(), self._loop).result()
        ready: list[Future] = []
        for server in self.servers:
            started: Future = Future()
            ready.append(started)
            self._tasks.append(asyncio.run_coroutine_threadsafe(self._serve(server, started), self._loop))
        for server, started in zip(self.servers, ready):
            try:
                started.result(timeout=START_TIMEOUT_S)
            except Exception as err:  # noqa: BLE001 - report any start failure and carry on without that server
                self.errors.append(f"MCP server '{server.name}' failed to start: {_describe(err)}")

    async def _make_stop(self) -> None:
        self._stop = asyncio.Event()

    async def _serve(self, server: ServerConfig, started: Future) -> None:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import get_default_environment, stdio_client

        params = StdioServerParameters(
            command=server.command,
            args=server.args,
            env={**get_default_environment(), **server.env},
            cwd=server.cwd,
        )
        # Server stderr (startup banners, tracebacks) goes to a log file, not the user's terminal.
        log_path = self.log_dir / f"mcp-{server.name}.log" if self.log_dir else Path(os.devnull)
        if self.log_dir:
            self.log_dir.mkdir(parents=True, exist_ok=True)
        errlog = log_path.open("a", encoding="utf-8")
        try:
            async with stdio_client(params, errlog=errlog) as (read, write), ClientSession(read, write) as session:
                await session.initialize()
                listed = []
                cursor = None
                while True:
                    page = await _list_tools(session, cursor)
                    listed.extend(page.tools)
                    cursor = _field(page, "next_cursor", "nextCursor")
                    if not cursor:
                        break
                for tool in listed:
                    name = tool_name(server.name, tool.name)
                    annotations = getattr(tool, "annotations", None)
                    read_only = bool(annotations and _field(annotations, "read_only_hint", "readOnlyHint", False))
                    schema = _field(tool, "input_schema", "inputSchema") or {"type": "object", "properties": {}}
                    self.tools[name] = _Tool(server.name, tool.name, read_only, {
                        "name": name,
                        "description": f"[MCP server: {server.name}] {(tool.description or tool.name)[:1000]}",
                        "input_schema": schema,
                    })
                self.sessions[server.name] = session
                started.set_result(len(listed))
                assert self._stop is not None
                await self._stop.wait()
        except BaseException as err:  # noqa: BLE001 - surface the failure to start(), then end this task
            if not started.done():
                started.set_exception(err)
            elif not isinstance(err, asyncio.CancelledError):
                self.errors.append(f"MCP server '{server.name}' stopped: {_describe(err)}")
        finally:
            self.sessions.pop(server.name, None)
            errlog.close()

    def close(self) -> None:
        if not self._thread.is_alive():
            return
        if self._stop is not None:
            self._loop.call_soon_threadsafe(self._stop.set)
        for task in self._tasks:
            try:
                task.result(timeout=10)
            except Exception:  # noqa: BLE001 - best-effort shutdown
                pass
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)

    # -- tools ----------------------------------------------------------------------------------

    def schemas(self) -> list[dict[str, Any]]:
        return [tool.schema for tool in self.tools.values()]

    def handles(self, name: str) -> bool:
        return name in self.tools

    def is_read_only(self, name: str) -> bool:
        return self.tools[name].read_only

    def summary(self) -> str:
        counts: dict[str, int] = {}
        for tool in self.tools.values():
            counts[tool.server] = counts.get(tool.server, 0) + 1
        return ", ".join(f"{server} ({n} tools)" for server, n in counts.items()) or "none"

    def call(self, name: str, arguments: dict[str, Any]) -> tuple[str, bool]:
        tool = self.tools[name]
        session = self.sessions.get(tool.server)
        if session is None:
            return f"Error: MCP server '{tool.server}' is not running.", True
        future = asyncio.run_coroutine_threadsafe(session.call_tool(tool.name, arguments), self._loop)
        try:
            return format_result(future.result(timeout=CALL_TIMEOUT_S))
        except TimeoutError:
            future.cancel()
            return f"Error: {name} timed out after {CALL_TIMEOUT_S} seconds.", True
        except Exception as err:  # noqa: BLE001 - MCP/transport errors become tool errors for Claude
            return f"Error from MCP server '{tool.server}': {_describe(err)}", True


async def _list_tools(session: Any, cursor: str | None) -> Any:
    if not cursor:
        return await session.list_tools()
    try:  # MCP SDK 2.x
        from mcp import types

        return await session.list_tools(params=types.PaginatedRequestParams(cursor=cursor))
    except (TypeError, AttributeError):  # MCP SDK 1.x
        return await session.list_tools(cursor=cursor)


_GROUP = getattr(builtins, "BaseExceptionGroup", ())  # Python 3.11+


def _describe(err: BaseException) -> str:
    """Unwrap exception groups (anyio raises them) to the first real cause."""
    while _GROUP and isinstance(err, _GROUP) and err.exceptions:
        err = err.exceptions[0]
    return f"{type(err).__name__}: {err}"
