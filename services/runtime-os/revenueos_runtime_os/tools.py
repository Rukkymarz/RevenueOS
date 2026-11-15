"""The NAVA tool table: built-in workspace tools, the sandboxed shell, and OmniPilot's desktop
tools delegated to runtime-omni. Every entry is reached only through `Gateway.syscall`."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from .nava import CallContext, ToolError, ToolSpec, Workspaces

MAX_FILE = 4 * 1024 * 1024
MAX_SHELL_S = 300


def _ws_res(args: dict, ctx: CallContext) -> list[str]:
    return [Workspaces.resource(ctx.agent_id, args["workspace"])]


def _file(ctx: CallContext, args: dict) -> Path:
    root = ctx.workspaces.path(ctx.agent_id, args["workspace"])
    p = (root / args["path"]).resolve()
    if not str(p).startswith(str(root.resolve()) + os.sep):
        raise ToolError(f"{args['path']} escapes the workspace")
    return p


def fs_read(ctx: CallContext, args: dict):
    p = _file(ctx, args)
    if not p.is_file():
        raise ToolError(f"{args['path']} not found")
    if p.stat().st_size > MAX_FILE:
        raise ToolError("file larger than 4 MiB")
    return {"path": args["path"], "content": p.read_text(errors="replace")}


def fs_list(ctx: CallContext, args: dict):
    root = ctx.workspaces.path(ctx.agent_id, args["workspace"])
    if not root.exists():
        return {"files": []}
    return {"files": sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())[:5000]}


def fs_write(ctx: CallContext, args: dict):
    p = _file(ctx, args)
    data = args["content"].encode()
    if len(data) > MAX_FILE:
        raise ToolError("content larger than 4 MiB")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return {"path": args["path"], "bytes": len(data)}


def fs_delete(ctx: CallContext, args: dict):
    p = _file(ctx, args)
    if not p.is_file():
        raise ToolError(f"{args['path']} not found")
    p.unlink()
    return {"path": args["path"], "deleted": True}


def shell_run(ctx: CallContext, args: dict):
    """argv runs in a fresh bubblewrap sandbox over a copy of the workspace (no network, quotas);
    a successful run's changeset is then applied to the workspace. A timeout or quota kill is
    reported and the call rolls back."""
    from revenueos_sandbox.supervisor import Quotas, commit, run_in_sandbox
    ws = ctx.workspaces.path(ctx.agent_id, args["workspace"])
    ws.mkdir(parents=True, exist_ok=True)
    wall = max(1, min(int(args.get("timeout_s", ctx.timeout_s)), MAX_SHELL_S))
    r = run_in_sandbox(args["argv"], ws, agent_id=ctx.agent_id, task_id=ctx.task_id,
                       quotas=Quotas(wall_seconds=wall, cpu_seconds=wall), keep_shadow=True,
                       yolo=ctx.mode == "yolo")
    out = {"status": r.status, "exit_code": r.exit_code, "stdout": r.stdout[-65536:], "stderr": r.stderr[-65536:],
           "reason": r.reason, "changes": r.changes, "changeset_hash": r.changeset_hash}
    try:
        if r.status != "ok":
            raise ToolError(r.reason or f"command {r.status} (exit {r.exit_code})", out)
        if r.changes:
            out["applied"] = commit(r, ws, r.changeset_hash)
        return out
    finally:
        if r.shadow is not None:
            import shutil
            shutil.rmtree(r.shadow.parent, ignore_errors=True)


WS = {"type": "string", "maxLength": 64}
PATH = {"type": "string", "maxLength": 1024}


def builtin_tools() -> dict[str, ToolSpec]:
    t = [
        ToolSpec("fs.read", fs_read, {"type": "object", "required": ["workspace", "path"], "additionalProperties": False,
                                      "properties": {"workspace": WS, "path": PATH}}, resources=_ws_res),
        ToolSpec("fs.list", fs_list, {"type": "object", "required": ["workspace"], "additionalProperties": False,
                                      "properties": {"workspace": WS}}, resources=_ws_res),
        ToolSpec("fs.write", fs_write, {"type": "object", "required": ["workspace", "path", "content"],
                                        "additionalProperties": False,
                                        "properties": {"workspace": WS, "path": PATH, "content": {"type": "string"}}},
                 mutating=True, resources=_ws_res),
        ToolSpec("fs.delete", fs_delete, {"type": "object", "required": ["workspace", "path"],
                                          "additionalProperties": False, "properties": {"workspace": WS, "path": PATH}},
                 risk="medium", mutating=True, resources=_ws_res),
        ToolSpec("sandbox.run", shell_run, {"type": "object", "required": ["workspace", "argv"], "additionalProperties": False,
                                          "properties": {"workspace": WS, "argv": {"type": "array", "items": {"type": "string"}},
                                                         "timeout_s": {"type": "integer"}}},
                 risk="medium", mutating=True, resources=_ws_res),
    ]
    return {s.name: s for s in t}


# ---- OmniPilot desktop tools, executed by runtime-omni for a running syscall ----------------
class OmniClient:
    def __init__(self, base_url: str, token: str | None, timeout: int = 120):
        self.base, self.token, self.timeout = base_url.rstrip("/"), token, timeout

    def _req(self, method: str, path: str, body: dict | None = None, headers: dict | None = None):
        req = urllib.request.Request(self.base + path, method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"content-type": "application/json",
                                              **({"authorization": f"Bearer {self.token}"} if self.token else {}),
                                              **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            try:
                return json.loads(e.read())
            except ValueError:
                raise ToolError(f"runtime-omni HTTP {e.code}") from None

    def tools(self) -> list[dict]:
        return self._req("GET", "/v1/tools")["tools"]

    def invoke(self, name: str, args: dict, ctx: CallContext) -> dict:
        return self._req("POST", f"/v1/tools/{name}/invoke",
                         {"task_id": ctx.task_id, "agent_id": ctx.agent_id, "args": args, "mode": ctx.mode,
                          "approval_id": ctx.approval_id},
                         headers={"x-nava-syscall": ctx.syscall_id})


def omni_tools(client: OmniClient) -> dict[str, ToolSpec]:
    out = {}
    for t in client.tools():
        name = t["name"]

        def handler(ctx, args, _n=name):
            r = client.invoke(_n, args, ctx)
            if r.get("status") != "ok":
                raise ToolError(r.get("error") or f"{_n}: {r.get('status')}", r)
            return r

        params = t.get("parameters") or {"type": "object"}
        out[f"omni.{name}"] = ToolSpec(f"omni.{name}", handler, {"type": "object", **{k: v for k, v in params.items()
                                                                                      if k in ("properties", "required")}},
                                       risk=t.get("base_risk", "low"), resources=lambda a, c: ["desktop"],
                                       delegated=True)
    return out
