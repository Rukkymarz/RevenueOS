"""egress-authz: the decision service behind the Envoy egress proxy.

Envoy's Lua filter calls POST /v1/check with x-egress-* headers before any
upstream connection. The policy (per-agent host allowlist + secret bindings) is
read from a YAML file; secrets are resolved by reference from the keychain.
Every decision is validated against the EgressDecision contract and written to
the audit ledger; secret values never appear in the ledger or the response
log. Response: 200 with `header=value` lines to inject, or 403 with a reason.
"""
import hashlib
import os
import re
from pathlib import Path

import yaml
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route

from revenueos_common.db import Database
from revenueos_common.secrets import KeychainStore, SecretResolver
from revenueos_common.service import create_app, postgres_check

POLICY_PATH = Path(os.environ.get("EGRESS_POLICY", "/etc/revenueos/egress-policy.yaml"))
UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
SAFE_VALUE = re.compile(r"^[^\r\n]+$")

db = Database(actor="egress-authz")
secrets = SecretResolver(KeychainStore(os.environ.get("REVENUEOS_KEYCHAIN_DIR", "/run/revenueos/keychain")))


def load_policy() -> dict:
    return yaml.safe_load(POLICY_PATH.read_text())


def _host_only(authority: str) -> str:
    return authority.lower()


def decide(agent: str, task: str, authority: str, method: str, path: str, policy: dict) -> tuple[bool, str, dict]:
    if not UUID.match(agent):
        return False, "missing or malformed agent identity", {}
    rules = policy.get("agents", {}).get(agent)
    if rules is None:
        return False, "agent has no egress policy", {}
    host = _host_only(authority)
    if host not in [h.lower() for h in rules.get("allow", [])]:
        return False, f"host {host} not allowlisted for agent", {}
    inject = {}
    for b in policy.get("secret_bindings", []):
        if b["host"].lower() == host and agent in b.get("agents", [agent]):
            value = secrets.get(b["secret_ref"])
            if value is None:
                return False, f"secret {b['secret_ref']} unavailable (fail closed)", {}
            rendered = b.get("format", "{}").format(value)
            if not SAFE_VALUE.match(rendered):
                return False, "secret value contains a line break (refused)", {}
            inject[b["header"].lower()] = rendered
    return True, "allowlisted", inject


def record(agent, task, host, method, path, allowed, reason, injected):
    from revenueos_contracts import models
    decision = {"agent_id": agent, "host": host or "?", "method": method or "?", "decision": "allow" if allowed else "deny",
                "reason": reason, "injected_secrets": len(injected)}
    if UUID.match(task or ""):
        decision["task_id"] = task
    if UUID.match(agent or ""):
        models.EgressDecision.model_validate(decision)
    payload = {**decision, "path_sha256": hashlib.sha256((path or "").encode()).hexdigest(),
               "injected_headers": sorted(injected)}
    db.scalar("SELECT audit_append($actor, $action, $target, #payload) IS NULL AS done",
              actor=agent or "unknown", action=f"egress.{decision['decision']}", target=host or "?", payload=payload)


async def check(request: Request):
    h = request.headers
    agent, task = h.get("x-egress-agent", ""), h.get("x-egress-task", "")
    host, method, path = h.get("x-egress-host", ""), h.get("x-egress-method", ""), h.get("x-egress-path", "")
    try:
        allowed, reason, inject = decide(agent, task, host, method, path, load_policy())
    except Exception as e:  # any failure denies: the proxy fails closed
        allowed, reason, inject = False, f"policy error: {type(e).__name__}", {}
    record(agent, task, host, method, path, allowed, reason, inject)
    if not allowed:
        return JSONResponse({"error": "egress denied", "reason": reason}, status_code=403)
    return PlainTextResponse("".join(f"{k}={v}\n" for k, v in inject.items()))


app = create_app("egress-authz", checks={"postgres": postgres_check(db), "policy": lambda: bool(load_policy())},
                 routes=[Route("/v1/check", check, methods=["POST"])])


def main() -> None:  # pragma: no cover
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 9100)))


if __name__ == "__main__":  # pragma: no cover
    main()
