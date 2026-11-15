"""Sandbox supervisor HTTP surface (C03/C17).

POST /v1/run runs a command for an agent inside Bubblewrap with a COW shadow workspace,
quotas and the blocklist, optionally with an identity-pinned egress session (the sandbox's
only network route). Every run is a sandbox_sessions row; every egress session an
egress_sessions row. /health is green only when Bubblewrap can actually start a sandbox.
"""
import os
import re
from pathlib import Path

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from revenueos_common import egress_identity
from revenueos_common.db import Database
from revenueos_common.secrets import KeychainStore, SecretResolver
from revenueos_common.service import create_app, postgres_check
from revenueos_sandbox.egress import EgressSession
from revenueos_sandbox.records import Recorder, egress_hooks
from revenueos_sandbox.supervisor import Quotas, run_in_sandbox

UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
WORKSPACE_ROOT = Path(os.environ.get("REVENUEOS_WORKSPACE_ROOT", "/var/lib/revenueos/workspaces"))
db = Database(actor="sandbox-supervisor")
secrets = SecretResolver(KeychainStore(os.environ.get("REVENUEOS_KEYCHAIN_DIR", "/run/revenueos/keychain")))


def _proxy() -> tuple[str, int]:
    host, _, port = os.environ.get("EGRESS_PROXY", "envoy:10000").rpartition(":")
    return host, int(port)


def sandbox_works() -> bool:
    return run_in_sandbox(["true"], quotas=Quotas(wall_seconds=10)).status == "ok"


def _workspace(agent: str, name: str | None) -> Path | None:
    if not name:
        return None
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", name) or name in {".", ".."}:
        raise ValueError("workspace must be a plain name")
    return WORKSPACE_ROOT / agent / name


async def run(request: Request) -> JSONResponse:
    body = await request.json()
    agent, task = body.get("agent_id", ""), body.get("task_id") or ""
    argv = body.get("argv")
    if not UUID.match(agent) or (task and not UUID.match(task)):
        return JSONResponse({"error": "agent_id (and task_id if given) must be UUIDs"}, status_code=400)
    if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
        return JSONResponse({"error": "argv must be a non-empty list of strings"}, status_code=400)
    try:
        ws = _workspace(agent, body.get("workspace"))
        q = Quotas(**{k: int(v) for k, v in (body.get("quotas") or {}).items()})
    except (ValueError, TypeError) as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    def go():
        recorder = Recorder(db)
        if not body.get("egress"):
            return run_in_sandbox(argv, ws, yolo=bool(body.get("yolo")), agent_id=agent, task_id=task,
                                  quotas=q, recorder=recorder)
        key = secrets.get(egress_identity.KEY_REF)
        if not key:
            raise RuntimeError("egress identity key unavailable (fail closed)")
        opened, closed = egress_hooks(db)
        with EgressSession(agent, task, key, _proxy(), on_open=opened, on_close=closed) as s:
            return run_in_sandbox(argv, ws, yolo=bool(body.get("yolo")), agent_id=agent, task_id=task,
                                  quotas=q, egress=s, recorder=recorder)

    try:
        r = await run_in_threadpool(go)
    except RuntimeError as e:
        return JSONResponse({"error": str(e)}, status_code=503)
    return JSONResponse({"status": r.status, "exit_code": r.exit_code, "stdout": r.stdout[-65536:],
                         "stderr": r.stderr[-65536:], "reason": r.reason, "changes": r.changes,
                         "changeset_hash": r.changeset_hash, "command_hash": r.command_hash})


async def info(_: Request) -> JSONResponse:
    return JSONResponse({"service": "sandbox-supervisor", "component": "C17", "backend": "bubblewrap"})


app = create_app("sandbox-supervisor", checks={"postgres": postgres_check(db), "bubblewrap": sandbox_works},
                 routes=[Route("/v1/info", info), Route("/v1/run", run, methods=["POST"])])


def main() -> None:  # pragma: no cover
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8300)))
