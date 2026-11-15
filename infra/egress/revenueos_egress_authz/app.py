"""egress-authz: the decision service behind the Envoy egress proxy (INV-11).

Envoy's Lua filter calls POST /v1/check with x-egress-* headers before any upstream
connection. A request is allowed only when all of these hold:

  1. identity pinning: the sandbox supervisor's forwarder signed the session, agent, task and
     timestamp (HMAC, keychain://egress-identity-hmac), the stamp is fresh, and the session row
     is open and belongs to that agent and task. An agent cannot name itself or another agent.
  2. the host is in the agent's egress rules, either agent-wide or for this task (Postgres
     egress_rules);
  3. every secret bound to the host resolves (by reference) and is header-safe; otherwise the
     request fails closed.

Every decision, allow or deny, is an egress_log row (append-only; a trigger writes the audit
entry with agent, task, host and reason). Secret values never leave this process except as the
injected header lines returned to Envoy. Response: 200 with `header=value` lines to inject, or
403 with a reason.
"""
import hashlib
import os
import re
import time

from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route

from revenueos_common import egress_identity
from revenueos_common.db import Database
from revenueos_common.secrets import KeychainStore, SecretResolver
from revenueos_common.service import create_app, postgres_check

UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
SAFE_VALUE = re.compile(r"^[^\r\n]+$")
POLICY_TTL_S = 2.0

db = Database(actor="egress-authz")
secrets: SecretResolver | None = None   # built on first use, so importing never touches the keychain


def _secrets() -> SecretResolver:
    global secrets
    if secrets is None:
        secrets = SecretResolver(KeychainStore(os.environ.get("REVENUEOS_KEYCHAIN_DIR", "/run/revenueos/keychain")))
    return secrets
_cache: dict = {"at": 0.0, "policy": None}


def load_policy(database: Database | None = None) -> dict:
    """{"agents": {agent: {"allow": [hosts], "tasks": {task: [hosts]}}}, "secret_bindings": [...]}"""
    d = database or db
    policy: dict = {"agents": {}, "secret_bindings": []}
    for r in d.rows("SELECT agent_id::text AS agent, task_id::text AS task, host FROM egress_rules"):
        a = policy["agents"].setdefault(r["agent"], {"allow": [], "tasks": {}})
        (a["tasks"].setdefault(r["task"], []) if r["task"] else a["allow"]).append(r["host"])
    for r in d.rows("SELECT host, header, format, secret_ref, coalesce(agent_ids::text[], '{}') AS agents FROM secret_bindings"):
        binding = {"host": r["host"], "header": r["header"], "format": r["format"], "secret_ref": r["secret_ref"]}
        if r["agents"]:
            binding["agents"] = r["agents"]
        policy["secret_bindings"].append(binding)
    return policy


def cached_policy() -> dict:
    if _cache["policy"] is None or time.monotonic() - _cache["at"] > POLICY_TTL_S:
        _cache.update(policy=load_policy(), at=time.monotonic())
    return _cache["policy"]


def decide(agent: str, task: str, authority: str, method: str, path: str, policy: dict) -> tuple[bool, str, dict]:
    if not UUID.match(agent):
        return False, "missing or malformed agent identity", {}
    rules = policy.get("agents", {}).get(agent)
    if rules is None:
        return False, "agent has no egress policy", {}
    host = authority.lower()
    allowed = {h.lower() for h in rules.get("allow", [])} | {h.lower() for h in rules.get("tasks", {}).get(task, [])}
    if host not in allowed:
        return False, f"host {host} not allowlisted for agent" + (" or task" if task else ""), {}
    inject = {}
    for b in policy.get("secret_bindings", []):
        if b["host"].lower() == host and agent in b.get("agents", [agent]):
            value = _secrets().get(b["secret_ref"])
            if value is None:
                return False, f"secret {b['secret_ref']} unavailable (fail closed)", {}
            rendered = b.get("format", "{}").replace("{}", value)
            if not SAFE_VALUE.match(rendered):
                return False, "secret value contains a line break (refused)", {}
            if b["header"].lower() in inject:
                return False, f"ambiguous secret bindings for {b['header']} (fail closed)", {}
            inject[b["header"].lower()] = rendered
    return True, "allowlisted", inject


def pinned_identity(session: str, agent: str, task: str, ts: str, sig: str, database: Database | None = None) -> str | None:
    """None when the request carries an authentic, fresh stamp for an open session it matches."""
    key = _secrets().get(egress_identity.KEY_REF)
    if not key:
        return "egress identity key unavailable (fail closed)"
    reason = egress_identity.verify(key, session, agent, task, ts, sig)
    if reason:
        return reason
    if not UUID.match(session):
        return "malformed session id"
    row = (database or db).one(
        "SELECT agent_id::text AS agent, coalesce(task_id::text, '') AS task, closed_at IS NULL AS open "
        "FROM egress_sessions WHERE id = $id::uuid", id=session)
    if row is None:
        return "unknown egress session"
    if not row["open"]:
        return "egress session closed"
    if row["agent"] != agent or row["task"] != task:
        return "session does not belong to this agent and task"
    return None


def record(session, agent, task, host, method, path, allowed, reason, injected, database: Database | None = None):
    from revenueos_contracts import models
    decision = {"agent_id": agent, "host": host or "?", "method": method or "?", "decision": "allow" if allowed else "deny",
                "reason": reason, "injected_secrets": len(injected)}
    if UUID.match(task or ""):
        decision["task_id"] = task
    if UUID.match(agent or ""):
        models.EgressDecision.model_validate(decision)
    (database or db).scalar(
        "INSERT INTO egress_log(session_id, agent_id, task_id, method, host, path_hash, decision, reason, injected_secrets) "
        "SELECT s.id, a.id, t.id, $method, $host, $path_hash, $decision, $reason, ($injected)::int "
        "FROM (SELECT 1) one "
        "LEFT JOIN egress_sessions s ON s.id::text = $session "
        "LEFT JOIN agents a ON a.id::text = $agent "
        "LEFT JOIN tasks t ON t.id::text = $task RETURNING id",
        session=session or "", agent=agent or "", task=task or "", method=decision["method"], host=decision["host"],
        path_hash=hashlib.sha256((path or "").encode()).hexdigest(), decision=decision["decision"],
        reason=reason, injected=str(len(injected)))


async def check(request: Request):
    h = request.headers
    session, agent, task = h.get("x-egress-session", ""), h.get("x-egress-agent", ""), h.get("x-egress-task", "")
    host, method, path = h.get("x-egress-host", ""), h.get("x-egress-method", ""), h.get("x-egress-path", "")
    inject: dict = {}
    try:
        reason = pinned_identity(session, agent, task, h.get("x-egress-ts", ""), h.get("x-egress-sig", ""))
        if reason:
            allowed = False
        else:
            allowed, reason, inject = decide(agent, task, host, method, path, cached_policy())
    except Exception as e:  # any failure denies: the proxy fails closed
        allowed, reason, inject = False, f"policy error: {type(e).__name__}", {}
    record(session, agent, task, host, method, path, allowed, reason, inject)
    if not allowed:
        return JSONResponse({"error": "egress denied", "reason": reason}, status_code=403)
    return PlainTextResponse("".join(f"{k}={v}\n" for k, v in inject.items()))


app = create_app("egress-authz", checks={"postgres": postgres_check(db),
                                         "identity_key": lambda: bool(_secrets().get(egress_identity.KEY_REF))},
                 routes=[Route("/v1/check", check, methods=["POST"])])


def main() -> None:  # pragma: no cover
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 9100)))


if __name__ == "__main__":  # pragma: no cover
    main()
