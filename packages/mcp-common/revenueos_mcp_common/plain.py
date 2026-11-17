"""A plain (envelope-free) MCP server: the server-side peer of `RawMcpClient`.

Spec 1.3 keeps every MCP SDK import inside mcp-common, so anything that has to *be* a generic
third-party-shaped MCP server (the Phase 4 test servers that Forage installs, sandboxes and
governs) is built here. Tools take their own native arguments; there is no RevenueOS envelope,
receipt or approval, because the point is to behave like a server RevenueOS did not write."""
from typing import Callable

from fastmcp import FastMCP


def plain_server(name: str, tools: dict[str, Callable]) -> FastMCP:
    server = FastMCP(name)
    for tool_name, fn in tools.items():
        server.tool(fn, name=tool_name)
    return server


def run_stdio(name: str, tools: dict[str, Callable]) -> None:  # pragma: no cover - process entrypoint
    plain_server(name, tools).run(transport="stdio", show_banner=False)


def run_http(name: str, tools: dict[str, Callable], host: str = "0.0.0.0", port: int = 8090) -> None:  # pragma: no cover
    plain_server(name, tools).run(transport="streamable-http", host=host, port=port, show_banner=False)
