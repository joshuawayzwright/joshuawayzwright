"""A tiny MCP server for tests (MCP Python SDK 2.x)."""

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

server = MCPServer("echo")


@server.tool(annotations=ToolAnnotations(read_only_hint=True))
def shout(text: str) -> str:
    """Return the text in capitals."""
    return text.upper()


@server.tool()
def fail(reason: str) -> str:
    """Always fails."""
    raise ValueError(reason)


if __name__ == "__main__":
    server.run()
