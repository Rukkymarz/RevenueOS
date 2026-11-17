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


def _egress_session(agent_id: str, task_id: str):
    from revenueos_common import egress_identity
    from revenueos_common.db import Database
    from revenueos_common.secrets import KeychainStore, SecretResolver
    from revenueos_sandbox.egress import EgressSession
    from revenueos_sandbox.records import egress_hooks
    from revenueos_sandbox.tls import EgressCA
    secrets = SecretResolver(KeychainStore(os.environ.get("REVENUEOS_KEYCHAIN_DIR", "/run/revenueos/keychain")))
    key = secrets.get(egress_identity.KEY_REF)
    if not key:
        raise ToolError("egress identity key unavailable (fail closed)")
    host, _, port = os.environ.get("EGRESS_PROXY", "envoy:10000").rpartition(":")
    opened, closed = egress_hooks(Database(actor="runtime-os"))
    return EgressSession(agent_id, task_id, key, (host, int(port)), on_open=opened, on_close=closed,
                         ca=EgressCA.from_vault(secrets))


def shell_run(ctx: CallContext, args: dict):
    """argv runs in a fresh bubblewrap sandbox over a copy of the workspace (no network, quotas);
    a successful run's changeset is then applied to the workspace. A timeout or quota kill is
    reported and the call rolls back."""
    from revenueos_sandbox.supervisor import Quotas, commit, run_in_sandbox
    ws = ctx.workspaces.path(ctx.agent_id, args["workspace"])
    ws.mkdir(parents=True, exist_ok=True)
    wall = max(1, min(int(args.get("timeout_s", ctx.timeout_s)), MAX_SHELL_S))
    # CPU budget sits just above the wall clock so a runaway is reported as the wall-clock
    # timeout it is, while a multi-threaded burner is still bounded.
    kw = dict(agent_id=ctx.agent_id, task_id=ctx.task_id, quotas=Quotas(wall_seconds=wall, cpu_seconds=wall + 5),
              keep_shadow=True, yolo=ctx.mode == "yolo", engine=args.get("engine", "bubblewrap"))
    if args.get("network"):
        # The sandbox's only route out: an identity-pinned egress session for this agent and task
        # (rules, secret injection and logging happen at the proxy, as for every agent process).
        with _egress_session(ctx.agent_id, ctx.task_id) as session:
            r = run_in_sandbox(args["argv"], ws, egress=session, **kw)
    else:
        r = run_in_sandbox(args["argv"], ws, **kw)
    out = {"status": r.status, "exit_code": r.exit_code, "stdout": r.stdout[-65536:], "stderr": r.stderr[-65536:],
           "reason": r.reason, "changes": r.changes, "changeset_hash": r.changeset_hash}
    try:
        if r.status != "ok":
            raise ToolError(r.reason or f"command {r.status} (exit {r.exit_code})", out)
        if r.changes:
            out["applied"] = commit(r, ws, r.changeset_hash)
        return out
    finally:
        if r.shadow_root is not None:
            import shutil
            shutil.rmtree(r.shadow_root, ignore_errors=True)


WS = {"type": "string", "maxLength": 64}
PATH = {"type": "string", "maxLength": 1024}


async def _call_playwright_mcp(tool: str, args: dict, url: str, timeout_s: float = 30.0):
    """A plain MCP client call — unlike McpClient, no RevenueOS envelope: playwright-mcp is a
    real third-party MCP server and its tools (browser_navigate, browser_click, ...) take their
    own native arguments directly, the same as any generic MCP client would send them.

    Spec 1.3: the MCP SDK is only ever imported inside packages/mcp-common
    (tests/connectivity/test_mcp_boundary.py), so this goes through mcp-common's
    `RawMcpClient` rather than importing `fastmcp` here directly."""
    from revenueos_mcp_common import RawMcpClient
    return await RawMcpClient(url, timeout_s=timeout_s).acall(tool, args)


def browser_call(ctx: CallContext, args: dict):
    """Proxies one call to the pinned playwright-mcp server (C02, docs/PINS.md) over its own
    HTTP MCP transport — a real, invokable domain, not a docs-only pin. `tool` is any tool name
    playwright-mcp itself exposes (browser_navigate, browser_click, browser_snapshot, ...);
    `args` are that tool's own native arguments, passed through unvalidated here since
    playwright-mcp validates its own schema at the boundary."""
    import asyncio
    url = os.environ.get("PLAYWRIGHT_MCP_URL", "http://playwright-mcp:8931")
    try:
        return asyncio.run(_call_playwright_mcp(args["tool"], args.get("args") or {}, url,
                                                timeout_s=min(int(args.get("timeout_s", 60)), MAX_SHELL_S)))
    except Exception as e:
        raise ToolError(f"playwright-mcp call failed: {type(e).__name__}: {e}") from None


def _discovery(path: str, body: dict, timeout: int = 180) -> dict:
    """runtime-os is the only caller of the discovery service's write surface (C04): an agent
    reaches Forage and installed MCP servers through these syscalls, never directly."""
    import json
    import urllib.error
    import urllib.request
    url = os.environ.get("DISCOVERY_URL", "http://discovery:8104") + path
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            reason = json.loads(e.read()).get("reason", f"HTTP {e.code}")
        except ValueError:
            reason = f"HTTP {e.code}"
        raise ToolError(f"discovery: {reason}") from None
    except OSError as e:
        raise ToolError(f"discovery unreachable: {type(e).__name__}: {e}") from None


def forage_search(ctx: CallContext, args: dict):
    return _discovery("/v1/forage/search", {"query": args["query"], "limit": int(args.get("limit", 10))})


def forage_install(ctx: CallContext, args: dict):
    out = _discovery("/v1/forage/install", {"spec": args["spec"], "agent_id": ctx.agent_id, "task_id": ctx.task_id})
    if out.get("status") == "denied":
        raise ToolError("install denied by the selection policy: " + "; ".join(out.get("reasons", [])))
    return out


RULE_FILE = "AGENTS.md"


def forage_learn(ctx: CallContext, args: dict):
    """Writes the server's usage instructions into the agent rule file (workspace `rules`), one
    marked block per server, replaced in place on re-learn. The next session reads the file."""
    out = _discovery("/v1/forage/learn", {"server": args["server"]})
    ws = ctx.workspaces.path(ctx.agent_id, args.get("workspace", "rules"))
    ws.mkdir(parents=True, exist_ok=True)
    f = ws / RULE_FILE
    text = f.read_text() if f.exists() else "# Agent rules\n"
    start, end = out["marker"], out["marker"].replace("forage:", "/forage:")
    block = f"{start}\n{out['instructions']}{end}\n"
    if start in text and end in text:
        text = text[:text.index(start)] + block + text[text.index(end) + len(end):].lstrip("\n")
    else:
        text = text.rstrip("\n") + "\n\n" + block
    f.write_text(text)
    return {"server": args["server"], "rule_file": f"{args.get('workspace', 'rules')}/{RULE_FILE}", "bytes": len(text)}


def mcp_call(ctx: CallContext, args: dict):
    """One call to an installed MCP server. INV-10 was already checked at gateway step 3; the
    discovery service checks it again and relays through agent-discover."""
    out = _discovery("/v1/call", {"server": args["server"], "tool": args["tool"], "arguments": args.get("arguments") or {},
                                  "task_id": ctx.task_id, "agent_id": ctx.agent_id,
                                  "timeout_s": min(int(args.get("timeout_s", 60)), MAX_SHELL_S)})
    return out.get("result")


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
                                                         "timeout_s": {"type": "integer"},
                                                         "network": {"type": "boolean"},
                                                         # engine="aegis" (C03, named — docs/PINS.md) runs argv through the
                                                         # pinned aegis-os binary instead of our own direct bwrap call; see
                                                         # infra/sandbox-supervisor/revenueos_sandbox/aegis.py.
                                                         "engine": {"type": "string", "enum": ["bubblewrap", "aegis"]}}},
                 risk="medium", mutating=True, resources=_ws_res),
        # C02 playwright-mcp (named, pinned — docs/PINS.md): a thin, generic MCP passthrough,
        # not 20+ hand-wired ToolSpecs — playwright-mcp validates its own tools' native argument
        # shapes at its own boundary. "browser" is a shared lock resource: a persistent browser
        # profile can only be driven by one call at a time (playwright-mcp's own documented
        # constraint), so concurrent calls from the same agent serialize instead of racing.
        # C04 (Phase 4): Forage and the governed call path for installed MCP servers. Installing is
        # medium, not high: what it produces is an experimental server in its own sandbox that
        # INV-10 keeps away from production tasks until a human approves it.
        ToolSpec("forage.search", forage_search, {"type": "object", "required": ["query"], "additionalProperties": False,
                                                  "properties": {"query": {"type": "string", "maxLength": 200},
                                                                 "limit": {"type": "integer"}}}),
        ToolSpec("forage.install", forage_install, {"type": "object", "required": ["spec"], "additionalProperties": False,
                                                    "properties": {"spec": {"type": "object"}}},
                 risk="medium", resources=lambda a, c: ["forage:install"]),
        ToolSpec("forage.learn", forage_learn, {"type": "object", "required": ["server"], "additionalProperties": False,
                                                "properties": {"server": {"type": "string", "maxLength": 64},
                                                               "workspace": WS}},
                 mutating=True, resources=lambda a, c: [c.workspaces.resource(c.agent_id, a.get("workspace", "rules"))]),
        ToolSpec("mcp.call", mcp_call, {"type": "object", "required": ["server", "tool"], "additionalProperties": False,
                                        "properties": {"server": {"type": "string", "maxLength": 64},
                                                       "tool": {"type": "string", "maxLength": 128},
                                                       "arguments": {"type": "object"},
                                                       "timeout_s": {"type": "integer"}}},
                 risk="medium", resources=lambda a, c: [f"mcp:{a.get('server')}"]),
        ToolSpec("browser.call", browser_call, {"type": "object", "required": ["tool", "args"],
                                                "additionalProperties": False,
                                                "properties": {"tool": {"type": "string", "maxLength": 64},
                                                               "args": {"type": "object"},
                                                               "timeout_s": {"type": "integer"}}},
                 risk="medium", mutating=False, resources=lambda a, c: ["browser"]),
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
