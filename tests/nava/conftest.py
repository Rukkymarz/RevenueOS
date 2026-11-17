"""NAVA test fixtures: a Gateway + Kernel wired to the per-test database and tmp workspaces."""
import pytest

import dbkit
from revenueos_common.db import Database


@pytest.fixture
def pgdb(db):
    """revenueos_common Database bound to this test's database (superuser: triggers still fire)."""
    return Database(dbname=db.name, host=dbkit.HOST, port=dbkit.PORT, user=dbkit.USER, actor="nava-test")


@pytest.fixture
def nava(db, world, pgdb, tmp_path):
    from revenueos_mcp_common.receipts import Receipts
    from revenueos_runtime_os.kernel import Kernel
    from revenueos_runtime_os.nava import Gateway, ToolSpec, Workspaces
    from revenueos_runtime_os.tools import builtin_tools

    ws = Workspaces(tmp_path / "ws", tmp_path / "snaps")
    tools = builtin_tools()

    def echo(ctx, args):
        return {"echo": args.get("text", "")}

    def boom(ctx, args):
        raise RuntimeError("tool exploded")

    tools["test.echo"] = ToolSpec("test.echo", echo, {"type": "object", "properties": {"text": {"type": "string"}}})
    tools["test.boom"] = ToolSpec("test.boom", boom, {"type": "object"}, mutating=False)
    gw = Gateway(pgdb, Receipts(pgdb), tools, ws, lock_timeout_s=0.3)
    k = Kernel(pgdb, gw)

    class Nava:
        pass

    n = Nava()
    n.db, n.gw, n.k, n.ws, n.world = db, gw, k, ws, world
    n.agent, n.other = world["exec"], world["ver"]
    n.task = world["task"]
    n.call = lambda **kw: gw.syscall(**{"caller_agent": n.agent, "agent_id": n.agent, "task_id": n.task,
                                        "mode": "auto", **kw})
    return n


def approve(db, approval_id, approver="human:christine"):
    db.q(f"SELECT approval_decide('{approval_id}', '{approver}', true)")
    return approval_id


def make_approval(db, task, args_hash, tool=None, server="runtime-os"):
    tool_sql = f"'{tool}'" if tool else "NULL"
    a = db.one("INSERT INTO approvals(task_id, tool_call_args_hash, requested_by, expires_at, mcp_server, tool) "
               f"VALUES ('{task}', '{args_hash}', 'agent:test', now() + interval '1 hour', '{server}', {tool_sql}) "
               "RETURNING id")
    return approve(db, a)
