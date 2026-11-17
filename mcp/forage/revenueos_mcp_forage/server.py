"""Forage as an MCP server (spec 4.1): the one gateway an agent host is configured with by hand.
Everything else is discovered through it.

Four tools: `forage_search`, `forage_install`, `forage_learn`, and `call` for any server Forage
installed. None of them does the work itself. Like the 15 NAVA servers, each forwards to a
governed syscall on the NAVA gateway (forage.search, forage.install, forage.learn, mcp.call),
where classification, policy, approvals, INV-10 and the receipt happen exactly once."""
import os

from pydantic import BaseModel, Field

from revenueos_mcp_common import create_server
from revenueos_mcp_nava.suite import _syscall

TOOLS = {"forage_search": "forage.search", "forage_install": "forage.install",
         "forage_learn": "forage.learn", "call": "mcp.call"}


class SyscallArgs(BaseModel):
    args: dict = Field(default_factory=dict)
    mode: str = "auto"
    expect: list = Field(default_factory=list)


def build(*, db=None, secrets=None, token_ref: str | None = None):
    server = create_server("forage", db=db, secrets=secrets,
                           token_ref=token_ref or os.environ.get("FORAGE_MCP_TOKEN_REF", "keychain://mcp-forage-token"))
    secrets = server.secrets
    for name, syscall in TOOLS.items():
        def make(syscall=syscall):
            def handler(args: dict, ctx: dict) -> dict:
                payload = SyscallArgs.model_validate(args).model_dump()
                return _syscall(secrets, ctx, syscall, payload, approval_id=args.get("approval_id"))
            handler.__doc__ = f"Run the governed NAVA syscall {syscall} (12-step gateway, receipted)."
            return handler
        server.tool(name, risk_class="low", args_model=SyscallArgs)(make())
    return server


def main() -> None:  # pragma: no cover - process entrypoint
    import uvicorn
    uvicorn.run(build().http_app(), host="0.0.0.0", port=int(os.environ.get("PORT", 8401)))
