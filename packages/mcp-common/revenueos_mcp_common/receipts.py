"""Receipts (INV-02) and approval consumption (INV-06), written to Postgres.

A tool call that cannot write its receipt does not return a result: the
receipt is part of the call, not a side effect that may be dropped.
"""
import hashlib
import json

from revenueos_common.canonical import args_hash, redact
from revenueos_common.db import Database


class ApprovalRequired(Exception):
    pass


def result_hash(result) -> str:
    try:
        from revenueos_common.canonical import canonical_json
        blob = canonical_json(result)
    except (ValueError, TypeError):
        blob = json.dumps(result, default=str, sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()


class Receipts:
    def __init__(self, db: Database):
        self.db = db

    def consume_approval(self, approval_id: str | None, args: dict, risk_class: str,
                         task_id: str | None = None, tool: str | None = None) -> str | None:
        if risk_class not in ("high", "critical"):
            return approval_id
        if not approval_id:
            raise ApprovalRequired(f"{risk_class} tool call requires a hash-bound approval")
        ok = self.db.scalar("SELECT consume_approval($id::uuid, $h, nullif($task,'')::uuid, nullif($tool,'')) AS ok",
                            id=approval_id, h=args_hash(args), task=task_id or "", tool=tool or "")
        if not ok:
            raise ApprovalRequired("approval is missing, expired, already used, or bound to different arguments, task or tool")
        return approval_id

    def deny(self, *, task_id, agent_id, server, tool, args, risk_class, reason, trace_id) -> None:
        self.db.scalar(
            "SELECT audit_append($agent_id, 'tool.denied', $target, #payload) IS NULL AS done",
            agent_id=agent_id, target=f"{server}/{tool}",
            payload={"task_id": task_id, "args_hash": args_hash(args), "risk_class": risk_class,
                     "reason": reason, "trace_id": trace_id})

    def write(self, *, task_id, agent_id, server, tool, args, result, latency_ms, cost, risk_class,
              approval_id, verdict, trace_id) -> str:
        return self.db.scalar(
            """INSERT INTO tool_calls(task_id, agent_id, mcp_server, tool, args_hash, args_redacted, result_hash,
                                      latency_ms, cost, risk_class, approval_id, verdict, trace_id)
               VALUES ($task_id::uuid, $agent_id::uuid, $server, $tool, $args_hash, #args_redacted,
                       NULLIF($result_hash, ''), $latency_ms::int, $cost::numeric, $risk_class::risk_class,
                       NULLIF($approval_id, '')::uuid, $verdict, $trace_id)
               RETURNING id""",
            task_id=task_id, agent_id=agent_id, server=server, tool=tool, args_hash=args_hash(args),
            args_redacted=redact(args), result_hash=result_hash(result) if result is not None else "",
            latency_ms=int(latency_ms), cost=cost, risk_class=risk_class, approval_id=approval_id or "",
            verdict=verdict, trace_id=trace_id or "")
