"""NAVA managed system calls (spec C03, Phase 3).

Every tool call an agent makes goes through `Gateway.syscall`, which runs the same twelve steps
in the same order and records each one in `syscall_steps` (the database rejects any other order,
see db/migrations/0003_nava.sql):

   1 validate      tool exists, arguments match its schema
   2 authenticate  the caller's token maps to this agent; the agent may act on this task
   3 authorize     no capability deny matches (a subagent inherits its parent's denies)
   4 classify      shared risk library (3.2), declared risk as a floor
   5 policy        decide(risk, mode): critical blocks in every mode; high always asks
   6 approval      consume the approval bound to args hash + task + tool, when policy asks
   7 quota         concurrency, rate and budget per agent
   8 lock          exclusive locks on the call's resources, in sorted order
   9 snapshot      copy of every workspace the call can change, with its content hash
  10 execute       the tool runs (shell in the bubblewrap sandbox, with quotas)
  11 verify        tool result plus caller postconditions; failure means rollback
  12 record        receipt in tool_calls, audit row, span, locks released

A call that fails at any step skips to 12. A mutating call that fails at 10 or 11 is restored
from its snapshot and ends `rolled_back`; the database checks that the restored hash equals the
snapshot hash (N14).
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from revenueos_common.canonical import args_hash as _jcs_hash, redact
from revenueos_risk import classify, decide

SERVER = "runtime-os"
MODES = ("ask", "auto", "yolo")
STEP_NAMES = ("validate", "authenticate", "authorize", "classify", "policy", "approval", "quota", "lock",
              "snapshot", "execute", "verify", "record")


def args_hash(args: dict) -> str:
    """RFC 8785 hash: the same value approvals and receipts are bound to (INV-06)."""
    return _jcs_hash(args)


# --------------------------------------------------------------------------------------------
# Tool table
# --------------------------------------------------------------------------------------------
class ToolError(Exception):
    """The tool ran and failed; `output` carries what it produced."""

    def __init__(self, message: str, output: Any = None):
        super().__init__(message)
        self.output = output


@dataclass
class ToolSpec:
    name: str
    handler: Callable[["CallContext", dict], Any]
    schema: dict                                   # JSON Schema subset: object/properties/required
    risk: str = "low"                              # declared floor
    mutating: bool = False                         # changes a snapshottable workspace
    resources: Callable[[dict, "CallContext"], list[str]] = lambda a, c: []
    verify: Callable[[Any, dict], str | None] | None = None   # -> failure reason or None
    delegated: bool = False                        # the executor writes the receipt itself


@dataclass
class CallContext:
    syscall_id: str
    agent_id: str
    task_id: str
    mode: str
    approval_id: str | None
    workspaces: "Workspaces"
    trace_id: str | None = None
    timeout_s: int = 30
    extra: dict = field(default_factory=dict)


_TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "object": dict, "array": list}


def validate_args(schema: dict, args: Any) -> str | None:
    if not isinstance(args, dict):
        return "arguments must be an object"
    props = schema.get("properties", {})
    for k in schema.get("required", []):
        if k not in args:
            return f"missing required argument {k!r}"
    if schema.get("additionalProperties") is False:
        extra = sorted(set(args) - set(props))
        if extra:
            return f"unknown argument(s) {extra}"
    for k, v in args.items():
        spec = props.get(k)
        if not spec or "type" not in spec:
            continue
        t = _TYPES.get(spec["type"])
        if t and (not isinstance(v, t) or (spec["type"] in ("integer", "number") and isinstance(v, bool))):
            return f"argument {k!r} must be {spec['type']}"
        if spec["type"] == "array" and "items" in spec:
            it = _TYPES.get(spec["items"].get("type", ""))
            if it and not all(isinstance(x, it) for x in v):
                return f"argument {k!r} must be an array of {spec['items']['type']}"
        if "enum" in spec and v not in spec["enum"]:
            return f"argument {k!r} must be one of {spec['enum']}"
        if spec["type"] == "string" and "maxLength" in spec and len(v) > spec["maxLength"]:
            return f"argument {k!r} longer than {spec['maxLength']}"
    return None


# --------------------------------------------------------------------------------------------
# Workspaces, snapshots and rollback
# --------------------------------------------------------------------------------------------
def tree_hash(root: Path) -> str:
    """Content hash of a directory: sorted (path, kind, mode, sha256) records. An empty or missing
    directory hashes to the empty-tree value, so 'created by this call' rolls back to 'absent'."""
    h = hashlib.sha256()
    if root.exists():
        for p in sorted(root.rglob("*")):
            rel = p.relative_to(root).as_posix()
            if p.is_symlink():
                h.update(f"L {rel} {os.readlink(p)}\n".encode())
            elif p.is_dir():
                h.update(f"D {rel}\n".encode())
            else:
                h.update(f"F {rel} {p.stat().st_mode & 0o777:o} {hashlib.sha256(p.read_bytes()).hexdigest()}\n".encode())
    return h.hexdigest()


class Workspaces:
    """Per-agent workspaces under `root/<agent_id>/<name>`; snapshots under `snap_root/<syscall>`.
    Snapshots survive a crash so the reaper can still roll an interrupted call back."""

    def __init__(self, root: Path | str, snap_root: Path | str):
        self.root, self.snap_root = Path(root), Path(snap_root)

    def path(self, agent_id: str, name: str) -> Path:
        if not name or "/" in name or name in (".", "..") or len(name) > 64:
            raise ValueError("workspace must be a plain name")
        return self.root / agent_id / name

    @staticmethod
    def resource(agent_id: str, name: str) -> str:
        return f"ws:{agent_id}/{name}"

    def from_resource(self, res: str) -> Path | None:
        if not res.startswith("ws:"):
            return None
        agent, name = res[3:].split("/", 1)
        return self.path(agent, name)

    def snapshot(self, syscall_id: str, resources: list[str]) -> str:
        snap = self.snap_root / syscall_id
        if snap.exists():
            shutil.rmtree(snap)
        snap.mkdir(parents=True)
        manifest = {}
        for i, res in enumerate(sorted(resources)):
            src = self.from_resource(res)
            if src is None:
                continue
            existed = src.exists()
            if existed:
                shutil.copytree(src, snap / str(i), symlinks=True)
            manifest[res] = {"slot": str(i), "existed": existed, "hash": tree_hash(src)}
        (snap / "manifest.json").write_text(json.dumps(manifest, sort_keys=True))
        return self.state_hash(manifest)

    @staticmethod
    def state_hash(manifest: dict) -> str:
        return hashlib.sha256(json.dumps({k: v["hash"] for k, v in sorted(manifest.items())}).encode()).hexdigest()

    def current_hash(self, syscall_id: str) -> str:
        manifest = json.loads((self.snap_root / syscall_id / "manifest.json").read_text())
        return self.state_hash({res: {"hash": tree_hash(self.from_resource(res))} for res in manifest})

    def restore(self, syscall_id: str) -> str:
        snap = self.snap_root / syscall_id
        manifest = json.loads((snap / "manifest.json").read_text())
        for res, m in manifest.items():
            dst = self.from_resource(res)
            if dst.exists():
                shutil.rmtree(dst)
            if m["existed"]:
                shutil.copytree(snap / m["slot"], dst, symlinks=True)
        return self.current_hash(syscall_id)

    def discard(self, syscall_id: str) -> None:
        shutil.rmtree(self.snap_root / syscall_id, ignore_errors=True)

    def has_snapshot(self, syscall_id: str) -> bool:
        return (self.snap_root / syscall_id / "manifest.json").exists()


# --------------------------------------------------------------------------------------------
# Gateway
# --------------------------------------------------------------------------------------------
@dataclass
class SyscallResult:
    id: str | None
    status: str                    # committed | rolled_back | denied | failed
    step: str                      # the last step reached
    reason: str | None = None
    risk_class: str | None = None
    output: Any = None
    receipt_id: str | None = None
    approval_id: str | None = None  # a pending approval created for a call that needs one
    snapshot_hash: str | None = None
    restored_hash: str | None = None

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


class _Stop(Exception):
    def __init__(self, step: int, status: str, reason: str, detail: dict | None = None):
        super().__init__(reason)
        self.step, self.status, self.reason, self.detail = step, status, reason, detail or {}


class Gateway:
    def __init__(self, db, receipts, tools: dict[str, ToolSpec], workspaces: Workspaces, *,
                 lock_timeout_s: float = 10.0, tracer=None, approval_ttl_s: int = 3600):
        self.db, self.receipts, self.tools, self.ws = db, receipts, tools, workspaces
        self.lock_timeout_s, self.tracer, self.approval_ttl_s = lock_timeout_s, tracer, approval_ttl_s

    # ---- recording ------------------------------------------------------------------------
    def _step(self, sid: str, n: int, outcome: str, detail: dict | None = None) -> None:
        self.db.scalar("INSERT INTO syscall_steps(syscall_id, step, name, outcome, detail) "
                       "VALUES ($sid::uuid, $n::smallint, $name, $outcome, #detail) RETURNING step",
                       sid=sid, n=n, name=STEP_NAMES[n - 1], outcome=outcome, detail=detail or {})

    def _set(self, sid: str, **cols) -> None:
        sets = ", ".join(f"{k} = ${k}::{t}" for k, t in (("risk_class", "risk_class"), ("snapshot_hash", "text"),
                                                         ("restored_hash", "text"), ("receipt_id", "uuid"),
                                                         ("reason", "text"), ("status", "syscall_status"))
                         if k in cols)
        self.db.scalar(f"UPDATE syscalls SET {sets} WHERE id = $sid::uuid RETURNING id", sid=sid, **cols)

    # ---- the call -------------------------------------------------------------------------
    def syscall(self, *, caller_agent: str | None, agent_id: str, task_id: str, tool: str, args: dict,
                mode: str = "auto", approval_id: str | None = None, expect: list | None = None,
                timeout_s: int = 30, trace_id: str | None = None) -> SyscallResult:
        if mode not in MODES:
            return SyscallResult(None, "denied", "validate", f"mode must be one of {MODES}")
        spec = self.tools.get(tool)
        h = args_hash(args if isinstance(args, dict) else {"_": args})
        sid = self.db.scalar(
            "INSERT INTO syscalls(agent_id, task_id, tool, args_hash, mutating, mode) "
            "VALUES ($a::uuid, $t::uuid, $tool, $h, $m::boolean, $mode) RETURNING id",
            a=agent_id, t=task_id, tool=tool, h=h, m=bool(spec.mutating) if spec else True, mode=mode)
        ctx = CallContext(sid, agent_id, task_id, mode, approval_id, self.ws, trace_id, timeout_s)
        ctx.extra["tool"] = tool
        res = SyscallResult(sid, "running", "validate")
        span = self.tracer.start_as_current_span(f"nava.syscall {tool}") if self.tracer else None
        if span:
            span.__enter__().set_attributes({"task_id": task_id, "agent_id": agent_id, "tool": tool,
                                             "syscall_id": sid})
        try:
            self._run(spec, ctx, args, caller_agent, res, expect or [])
        except _Stop as s:
            res.status, res.reason, res.step = s.status, s.reason, STEP_NAMES[s.step - 1]
            if s.step <= 11:
                self._step(sid, s.step, "fail", {"reason": s.reason, **s.detail})
        except Exception as e:  # noqa: BLE001 - recorded by _finish as a failed call
            res.reason = f"gateway error: {type(e).__name__}: {e}"
        finally:
            self._finish(spec, ctx, args, res)
            if span:
                span.__exit__(None, None, None)
        return res

    def _run(self, spec: ToolSpec | None, ctx: CallContext, args: dict, caller: str | None,
             res: SyscallResult, expect: list) -> None:
        sid = ctx.syscall_id
        # 1 validate
        if spec is None:
            raise _Stop(1, "denied", f"unknown tool {ctx.extra['tool']!r}")
        bad = validate_args(spec.schema, args)
        if bad:
            raise _Stop(1, "denied", bad)
        self._step(sid, 1, "pass")
        # 2 authenticate
        res.step = "authenticate"
        if caller is None or caller != ctx.agent_id:
            raise _Stop(2, "denied", "caller is not authenticated as this agent")
        bound = self.db.scalar(
            """SELECT CASE
                 WHEN t.assigned_agent_id IS NULL AND t.executor_agent_id IS NULL THEN true
                 ELSE $a::uuid IN (t.assigned_agent_id, t.executor_agent_id)
                   OR EXISTS (SELECT 1 FROM nava_subagents s WHERE s.agent_id = $a::uuid
                               AND s.parent_agent_id IN (t.assigned_agent_id, t.executor_agent_id)
                               AND s.expires_at > now())
               END AS ok FROM tasks t WHERE t.id = $t::uuid""", a=ctx.agent_id, t=ctx.task_id)
        if not bound:
            raise _Stop(2, "denied", "agent is not assigned to this task")
        self._step(sid, 2, "pass", {"agent_id": ctx.agent_id})
        # 3 authorize
        res.step = "authorize"
        if not self.db.scalar("SELECT nava_allowed($a::uuid, $tool) AS ok", a=ctx.agent_id, tool=spec.name):
            raise _Stop(3, "denied", f"capability denied: {spec.name}")
        if spec.name == "mcp.call":   # INV-10 (spec 4.6): the database decides, the gateway enforces and logs
            why = self.db.scalar("SELECT tool_activation_refusal($s, $t::uuid) AS why", s=args["server"], t=ctx.task_id)
            if why:
                self.db.scalar(
                    "INSERT INTO tool_events(mcp_server_name, installation_id, task_id, agent_id, kind, detail) "
                    "VALUES ($s, (SELECT id FROM tool_installations WHERE mcp_server_name = $s ORDER BY created_at DESC LIMIT 1), "
                    "$t::uuid, $a::uuid, 'call_blocked', jsonb_build_object('reason', $w, 'syscall_id', $sid, 'tool', $tool)) "
                    "RETURNING id", s=args["server"], t=ctx.task_id, a=ctx.agent_id, w=why, sid=sid, tool=args["tool"])
                raise _Stop(3, "denied", why)
        self._step(sid, 3, "pass")
        # 4 classify
        res.step = "classify"
        risk = classify(spec.name.removeprefix("omni."), args, declared=spec.risk, context="contained")
        res.risk_class = risk.level
        self._set(sid, risk_class=risk.level)
        self._step(sid, 4, "pass", {"risk_class": risk.level, "reasons": list(risk.reasons)[:20]})
        # 5 policy
        res.step = "policy"
        action = decide(risk, ctx.mode)
        if action == "block":
            raise _Stop(5, "denied", "blocked: " + "; ".join(risk.reasons), {"action": action})
        self._step(sid, 5, "pass", {"action": action})
        # 6 approval
        res.step = "approval"
        if action == "prompt":
            if not ctx.approval_id:
                pending = self._request_approval(ctx, spec, args, risk.level)
                res.approval_id = pending
                raise _Stop(6, "denied", "approval required", {"pending_approval_id": pending})
            if spec.delegated:
                # the executor (runtime-omni) consumes it while executing; here it must be live and bound
                ok = self.db.scalar(
                    "SELECT 1 AS ok FROM approvals WHERE id = $id::uuid AND status = 'approved' "
                    "AND expires_at > now() AND tool_call_args_hash = $h AND task_id = $t::uuid "
                    "AND (tool IS NULL OR tool = $tool)",
                    id=ctx.approval_id, h=args_hash(args), t=ctx.task_id, tool=spec.name.removeprefix("omni."))
            else:
                ok = self.db.scalar("SELECT consume_approval($id::uuid, $h, $t::uuid, $tool) AS ok",
                                    id=ctx.approval_id, h=args_hash(args), t=ctx.task_id, tool=spec.name)
            if not ok:
                raise _Stop(6, "denied", "approval is missing, expired, used, or bound to other args/task/tool")
            self._step(sid, 6, "pass", {"approval_id": ctx.approval_id})
        else:
            ctx.approval_id = None
            self._step(sid, 6, "skip", {"reason": "policy allows"})
        # 7 quota
        res.step = "quota"
        over = self.db.scalar("SELECT nava_quota_check($a::uuid) AS r", a=ctx.agent_id)
        if over:
            raise _Stop(7, "denied", over)
        self._step(sid, 7, "pass")
        # 8 lock
        res.step = "lock"
        resources = sorted(set(spec.resources(args, ctx)))
        self._lock(ctx, resources)
        self._step(sid, 8, "pass" if resources else "skip", {"resources": resources})
        # 9 snapshot
        res.step = "snapshot"
        ws_res = [r for r in resources if r.startswith("ws:")]
        if spec.mutating:
            res.snapshot_hash = self.ws.snapshot(sid, ws_res)
            self._set(sid, snapshot_hash=res.snapshot_hash)
            self._step(sid, 9, "pass", {"snapshot_hash": res.snapshot_hash, "resources": ws_res})
        else:
            self._step(sid, 9, "skip", {"reason": "read-only or not snapshottable"})
        # 10 execute
        res.step = "execute"
        start = time.monotonic()
        try:
            out = spec.handler(ctx, args)
        except ToolError as e:
            res.output = e.output
            raise _Stop(10, "failed", str(e), {"latency_ms": int((time.monotonic() - start) * 1000)})
        except Exception as e:  # noqa: BLE001 - a crash is a recorded failure, never silent
            raise _Stop(10, "failed", f"{type(e).__name__}: {e}")
        res.output = out
        ctx.extra["latency_ms"] = int((time.monotonic() - start) * 1000)
        self._step(sid, 10, "pass", {"latency_ms": ctx.extra["latency_ms"]})
        # 11 verify
        res.step = "verify"
        why = spec.verify(out, args) if spec.verify else None
        why = why or check_postconditions(expect, out, ctx, args)
        if why:
            raise _Stop(11, "failed", f"verification failed: {why}")
        self._step(sid, 11, "pass", {"postconditions": len(expect)})
        res.status = "committed"

    # ---- approvals, locks ----------------------------------------------------------------
    def _request_approval(self, ctx: CallContext, spec: ToolSpec, args: dict, risk: str) -> str:
        return self.db.scalar(
            "INSERT INTO approvals(task_id, tool_call_args_hash, requested_by, expires_at, mcp_server, tool, "
            "args_preview, risk_class) VALUES ($t::uuid, $h, $who, now() + make_interval(secs => $ttl::int), "
            "$srv, $tool, #prev, $risk::risk_class) RETURNING id",
            t=ctx.task_id, h=args_hash(args), who=f"agent:{ctx.agent_id}", ttl=self.approval_ttl_s,
            srv=SERVER, tool=spec.name.removeprefix("omni."), prev=redact(args), risk=risk)

    def _lock(self, ctx: CallContext, resources: list[str]) -> None:
        deadline = time.monotonic() + self.lock_timeout_s
        for i, r in enumerate(resources):
            while True:
                got = self.db.scalar(
                    "INSERT INTO nava_locks(resource, syscall_id, ord) VALUES ($r, $sid::uuid, $i::int) "
                    "ON CONFLICT (resource) DO NOTHING RETURNING resource", r=r, sid=ctx.syscall_id, i=i)
                if got:
                    break
                if time.monotonic() >= deadline:
                    holder = self.db.scalar("SELECT syscall_id FROM nava_locks WHERE resource = $r", r=r)
                    raise _Stop(8, "failed", f"lock timeout on {r} (held by {holder})")
                time.sleep(0.05)

    # ---- step 12 ---------------------------------------------------------------------------
    def _finish(self, spec: ToolSpec | None, ctx: CallContext, args: dict, res: SyscallResult) -> None:
        sid = ctx.syscall_id
        if res.status == "running":    # an unexpected exception inside the gateway itself
            res.status, res.reason = "failed", res.reason or "gateway error"
            try:
                self._step(sid, STEP_NAMES.index(res.step) + 1, "fail", {"reason": res.reason})
            except Exception:  # noqa: BLE001
                pass
        if res.status == "failed" and spec is not None and spec.mutating and self.ws.has_snapshot(sid):
            res.restored_hash = self.ws.restore(sid)
            res.status = "rolled_back"
            self._set(sid, restored_hash=res.restored_hash)
        receipt = None
        executed = res.status in ("committed", "rolled_back") or res.step in ("execute", "verify")
        if spec is not None and executed:
            if spec.delegated and isinstance(res.output, dict) and res.output.get("receipt_id"):
                receipt = res.output["receipt_id"]
            else:
                try:
                    receipt = self.receipts.write(
                        task_id=ctx.task_id, agent_id=ctx.agent_id, server=SERVER, tool=spec.name, args=args,
                        result=_jsonable(res.output), latency_ms=ctx.extra.get("latency_ms", 0), cost=0,
                        risk_class=res.risk_class or spec.risk, approval_id=ctx.approval_id,
                        verdict={"committed": "ok", "rolled_back": "rolled_back"}.get(res.status, "error"),
                        trace_id=ctx.trace_id)
                except Exception as e:  # noqa: BLE001 - e.g. INV-06: receipt refused -> the call fails
                    res.status, res.reason = ("failed" if res.status == "committed" else res.status,
                                              f"receipt refused: {getattr(e, 'message', e)}")
                    executed = False
        if spec is not None and not executed and receipt is None:
            self.receipts.deny(task_id=ctx.task_id, agent_id=ctx.agent_id, server=SERVER, tool=spec.name,
                               args=args, risk_class=res.risk_class or spec.risk, reason=res.reason or res.status,
                               trace_id=ctx.trace_id)
        res.receipt_id = receipt
        self._step(sid, 12, "pass" if res.status == "committed" else "fail",
                   {"receipt_id": receipt, "status": res.status, "reason": res.reason})
        self._set(sid, status=res.status, receipt_id=receipt, reason=res.reason)
        if res.status in ("committed", "rolled_back"):
            self.ws.discard(sid)

    # ---- crash recovery ------------------------------------------------------------------
    def reap(self, older_than_s: int = 600) -> list[str]:
        """End syscalls left running by a crashed gateway: restore their snapshots and release
        their locks. Returns the reaped ids."""
        rows = self.db.rows(
            "SELECT s.id, s.mutating, coalesce(max(st.step), 0) AS last FROM syscalls s "
            "LEFT JOIN syscall_steps st ON st.syscall_id = s.id "
            "WHERE s.status = 'running' AND s.started_at < now() - make_interval(secs => $age::int) "
            "GROUP BY s.id, s.mutating", age=older_than_s)
        out = []
        for r in rows:
            sid, last = r["id"], int(r["last"])
            if last < 11:
                self._step(sid, last + 1, "fail", {"reason": "reaped: gateway stopped mid-call"})
            status, restored = "failed", None
            if r["mutating"] and self.ws.has_snapshot(sid):
                restored = self.ws.restore(sid)
                status = "rolled_back"
                self._set(sid, restored_hash=restored)
            self._step(sid, 12, "fail", {"status": status, "reason": "reaped"})
            self._set(sid, status=status, reason="reaped: gateway stopped mid-call")
            self.ws.discard(sid)
            out.append(sid)
        return out


def _jsonable(v):
    try:
        json.dumps(v)
        return v
    except TypeError:
        return repr(v)


def check_postconditions(expect: list, out: Any, ctx: CallContext, args: dict) -> str | None:
    """Caller postconditions, checked against the real post-state:
      {"exit_code": 0}                        shell result
      {"file_exists": "rel/path"}             in args["workspace"]
      {"file_absent": "rel/path"}
      {"file_contains": ["rel/path", "text"]}
      {"stdout_contains": "text"}
    """
    ws = None
    if isinstance(args, dict) and args.get("workspace"):
        ws = ctx.workspaces.path(ctx.agent_id, args["workspace"])
    for e in expect:
        if not isinstance(e, dict) or len(e) != 1:
            return f"malformed postcondition {e!r}"
        (k, v), = e.items()
        if k == "exit_code":
            if not isinstance(out, dict) or out.get("exit_code") != v:
                return f"exit code {out.get('exit_code') if isinstance(out, dict) else None} != {v}"
        elif k == "stdout_contains":
            if not isinstance(out, dict) or str(v) not in str(out.get("stdout", "")):
                return f"stdout lacks {v!r}"
        elif k in ("file_exists", "file_absent", "file_contains"):
            if ws is None:
                return f"{k} needs a workspace"
            rel = v[0] if k == "file_contains" else v
            p = (ws / rel).resolve()
            if not str(p).startswith(str(ws.resolve()) + os.sep):
                return f"{rel} escapes the workspace"
            if k == "file_exists" and not p.is_file():
                return f"{rel} does not exist"
            if k == "file_absent" and p.exists():
                return f"{rel} exists"
            if k == "file_contains" and (not p.is_file() or v[1] not in p.read_text(errors="replace")):
                return f"{rel} lacks {v[1]!r}"
        else:
            return f"unknown postcondition {k!r}"
    return None
