"""packages/mcp-common: the only place RevenueOS imports the MCP SDK.

Receipts, rate limiting and telemetry have no MCP dependency, so services that only write
receipts (runtime-os, runtime-omni) can import them without FastMCP installed; the client and
server symbols load the SDK on first attribute access.
"""
from .ratelimit import RateLimited, TokenBucket, retry_with_backoff
from .receipts import ApprovalRequired, Receipts
from .telemetry import setup_tracing, standard_attributes

__all__ = ["McpClient", "RawMcpClient", "RateLimited", "TokenBucket", "retry_with_backoff", "ApprovalRequired",
           "Receipts", "RevenueOSMcpServer", "create_server", "setup_tracing", "standard_attributes"]

_LAZY = {"McpClient": "client", "RawMcpClient": "client", "RevenueOSMcpServer": "server", "create_server": "server"}


def __getattr__(name: str):
    mod = _LAZY.get(name)
    if mod is None:
        raise AttributeError(name)
    import importlib
    return getattr(importlib.import_module(f".{mod}", __name__), name)
