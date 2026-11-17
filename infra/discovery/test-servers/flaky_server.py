"""Test MCP server (Acceptance 4, health): works until its `break_server` tool is called, then
exits and refuses to start again, so the next health probe fails."""
import os
import sys

from revenueos_mcp_common.plain import run_stdio

DEAD = "/workspace/dead"


def ping() -> dict:
    """Answer while healthy."""
    return {"pong": True}


def break_server() -> dict:
    """Make this server unhealthy from now on."""
    open(DEAD, "w").close()
    os._exit(1)


if __name__ == "__main__":
    if os.path.exists(DEAD):
        sys.exit(1)
    run_stdio("fixture-flaky", {"ping": ping, "break_server": break_server})
