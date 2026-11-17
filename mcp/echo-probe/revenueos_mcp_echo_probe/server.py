"""echo-probe: proves the mcp-common path (auth, span, receipt, approvals) end to end."""
import os

from pydantic import BaseModel, Field
from revenueos_mcp_common import create_server

server = create_server("echo-probe")


class EchoArgs(BaseModel):
    message: str = Field(max_length=200)


@server.tool("probe_echo", risk_class="low", args_model=EchoArgs)
def echo(args: dict) -> dict:
    """Echo a message back."""
    return {"echo": args["message"]}


@server.tool("probe_guarded", risk_class="high", args_model=EchoArgs)
def guarded(args: dict) -> dict:
    """High-risk probe: only runs with a consumed, hash-bound approval."""
    return {"echo": args["message"], "guarded": True}


app = server.http_app()


def main() -> None:  # pragma: no cover - process entrypoint
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8201)))


if __name__ == "__main__":  # pragma: no cover
    main()
