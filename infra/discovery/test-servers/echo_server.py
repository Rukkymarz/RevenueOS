"""Test MCP server (compose profile `test`, unit tests): a well-behaved third-party-shaped
server. `python echo_server.py stdio` or `python echo_server.py http [port]`."""
import sys

from revenueos_mcp_common.plain import run_http, run_stdio


def echo(message: str) -> dict:
    """Echo a message back."""
    return {"echo": message}


def add(a: int, b: int) -> dict:
    """Add two integers."""
    return {"sum": a + b}


TOOLS = {"echo": echo, "add": add}

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "http":
        run_http("fixture-echo", TOOLS, port=int(sys.argv[2]) if len(sys.argv) > 2 else 8090)
    else:
        run_stdio("fixture-echo", TOOLS)
