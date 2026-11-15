"""A remote (streamable HTTP) MCP server for tests. Rejects requests without the expected bearer token."""

import sys

import uvicorn
from mcp.server.mcpserver import MCPServer

server = MCPServer("remote-echo")


@server.tool()
def shout(text: str) -> str:
    """Return the text in capitals."""
    return text.upper()


def require_token(app, token):
    async def guarded(scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers") or [])
            if headers.get(b"authorization") != f"Bearer {token}".encode():
                await send({"type": "http.response.start", "status": 401, "headers": [(b"content-type", b"text/plain")]})
                await send({"type": "http.response.body", "body": b"unauthorized"})
                return
        await app(scope, receive, send)

    return guarded


if __name__ == "__main__":
    port, token = int(sys.argv[1]), sys.argv[2]
    uvicorn.run(require_token(server.streamable_http_app(), token), host="127.0.0.1", port=port, log_level="warning")
