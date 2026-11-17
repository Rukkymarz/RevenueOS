"""Governance of record for installed MCP servers (spec 4.2, 4.6): approval status, activation,
health and the event log. agent-discover holds what is installed and connected; this decides
what may be used. INV-10 itself is a database function and trigger (0004_discovery.sql), so
this module asks the database and logs the answer rather than deciding on its own."""
import json

from revenueos_common.db import DatabaseError


class ActivationRefused(Exception):
    pass


class NotInstalled(KeyError):
    pass


def event(db, server: str, kind: str, detail: dict | None = None, *, task_id=None, agent_id=None) -> None:
    db.rows("INSERT INTO tool_events(mcp_server_name, installation_id, task_id, agent_id, kind, detail) "
            "VALUES ($s, (SELECT id FROM tool_installations WHERE mcp_server_name = $s ORDER BY created_at DESC LIMIT 1), "
            "nullif($t, '')::uuid, nullif($a, '')::uuid, $k, $d::jsonb) RETURNING id",
            s=server, t=task_id or "", a=agent_id or "", k=kind, d=json.dumps(detail or {}, default=str))


def installation(db, server: str) -> dict:
    row = db.one("SELECT id, mcp_server_name AS name, registry_source, version, checksum, license, status, "
                 "approved_by, health_status, active, observe_until, agent_id, install_spec, policy_score, created_at "
                 "FROM tool_installations WHERE mcp_server_name = $s ORDER BY created_at DESC LIMIT 1", s=server)
    if row is None:
        raise NotInstalled(server)
    return row


def refusal(db, server: str, task_id: str) -> str | None:
    return db.scalar("SELECT tool_activation_refusal($s, $t::uuid) AS why", s=server, t=task_id)


def activate(db, ad, *, server: str, task_id: str, agent_id: str | None = None) -> dict:
    """Make `server` usable for `task_id`. A server that is not approved or production cannot be
    activated for a production task: the attempt is blocked and logged (INV-10, spec 4.6)."""
    why = refusal(db, server, task_id)
    if why:
        event(db, server, "activation_blocked", {"reason": why}, task_id=task_id, agent_id=agent_id)
        db.rows("SELECT audit_reject('tool.activate', $s, $p::jsonb) AS x", s=server,
                p=json.dumps({"task_id": task_id, "reason": why}))
        raise ActivationRefused(why)
    inst = installation(db, server)
    try:
        db.rows("INSERT INTO tool_activations(installation_id, task_id, agent_id) "
                "VALUES ($i::uuid, $t::uuid, nullif($a, '')::uuid) ON CONFLICT DO NOTHING RETURNING id",
                i=inst["id"], t=task_id, a=agent_id or "")
    except DatabaseError as e:            # the trigger refused it between our check and the insert
        event(db, server, "activation_blocked", {"reason": e.message()[:300]}, task_id=task_id, agent_id=agent_id)
        raise ActivationRefused(e.message()) from None
    if ad is not None and not inst["active"]:
        set_active(db, ad, server, True)
    event(db, server, "activated", {"status": inst["status"]}, task_id=task_id, agent_id=agent_id)
    return {"server": server, "task_id": task_id, "status": inst["status"], "activated": True}


def deactivate(db, server: str, task_id: str | None = None) -> int:
    rows = db.rows("UPDATE tool_activations a SET deactivated_at = now() FROM tool_installations i "
                   "WHERE a.installation_id = i.id AND i.mcp_server_name = $s AND a.deactivated_at IS NULL "
                   "AND ($t = '' OR a.task_id = nullif($t, '')::uuid) RETURNING a.id", s=server, t=task_id or "")
    if rows:
        event(db, server, "deactivated", {"activations": len(rows)}, task_id=task_id)
    return len(rows)


def set_active(db, ad, server: str, active: bool) -> None:
    """Tools appear and disappear by enabling or disabling the server in agent-discover (4.2)."""
    entry = ad.find(server)
    if entry is None:
        raise NotInstalled(server)
    (ad.enable if active else ad.disable)(entry["id"])
    db.rows("UPDATE tool_installations SET active = $v::boolean WHERE mcp_server_name = $s RETURNING id",
            v=active, s=server)


def approve(db, server: str, approver: str, to: str = "approved") -> dict:
    """experimental -> approved -> production. The database refuses a missing approver, a skipped
    step and a promotion inside the observation window."""
    if to not in ("approved", "production"):
        raise ValueError("status must be approved or production")
    if not approver or approver.startswith("agent:"):
        raise PermissionError("a server is approved by a human or a pinned bootstrap, never by an agent")
    row = db.one("UPDATE tool_installations SET status = $st::install_status, approved_by = $by "
                 "WHERE id = (SELECT id FROM tool_installations WHERE mcp_server_name = $s ORDER BY created_at DESC LIMIT 1) "
                 "RETURNING id, status", st=to, by=approver, s=server)
    if row is None:
        raise NotInstalled(server)
    event(db, server, "approved" if to == "approved" else "promoted", {"by": approver, "status": to})
    return {"server": server, "status": row["status"], "approved_by": approver}


def release(db, server: str, approver: str) -> dict:
    """A human clears an unhealthy or quarantined server for use again."""
    if not approver or approver.startswith("agent:"):
        raise PermissionError("only a human releases a quarantined server")
    row = db.one("UPDATE tool_installations SET health_status = 'UNKNOWN' WHERE mcp_server_name = $s RETURNING id", s=server)
    if row is None:
        raise NotInstalled(server)
    event(db, server, "approved", {"by": approver, "released": True})
    return {"server": server, "health_status": "UNKNOWN"}


def mark_unhealthy(db, ad, server: str, kind: str, detail: dict, health: str = "UNHEALTHY") -> None:
    """Unhealthy or quarantined: out of the active tool set, live activations ended, logged."""
    db.rows("UPDATE tool_installations SET active = false, health_status = $h WHERE mcp_server_name = $s RETURNING id",
            h=health, s=server)
    if ad is not None:
        entry = ad.find(server)
        if entry is not None:
            try:
                ad.disable(entry["id"])
            except Exception:  # noqa: BLE001 - the database already took it out of use
                pass
    deactivate(db, server)
    event(db, server, kind, detail)


def probe(db, ad, server: str) -> dict:
    entry = ad.find(server)
    if entry is None:
        raise NotInstalled(server)
    try:
        res = ad.probe(entry["id"])
    except Exception as e:  # noqa: BLE001
        res = {"status": "error", "error": f"{type(e).__name__}: {e}"}
    ok = res.get("status") in ("ok", "healthy", "connected") and not res.get("error")
    if ok:
        db.rows("UPDATE tool_installations SET health_status = 'HEALTHY' WHERE mcp_server_name = $s "
                "AND health_status IN ('UNKNOWN', 'HEALTHY') RETURNING id", s=server)
        event(db, server, "health_ok", {"latency_ms": res.get("latency_ms")})
    else:
        mark_unhealthy(db, ad, server, "health_failed", {"probe": res})
    return {"server": server, "healthy": ok, "probe": res}


def call(db, ad, *, server: str, tool: str, arguments: dict, task_id: str, agent_id: str | None = None,
         timeout_s: float = 60.0):
    """One governed call. INV-10 is checked on every call, not only at activation, so a server
    demoted or quarantined after activation stops working at once."""
    why = refusal(db, server, task_id)
    if why:
        event(db, server, "call_blocked", {"tool": tool, "reason": why}, task_id=task_id, agent_id=agent_id)
        raise ActivationRefused(why)
    live = db.scalar("SELECT 1 AS x FROM tool_activations a JOIN tool_installations i ON i.id = a.installation_id "
                     "WHERE i.mcp_server_name = $s AND a.task_id = $t::uuid AND a.deactivated_at IS NULL", s=server, t=task_id)
    if not live:
        activate(db, ad, server=server, task_id=task_id, agent_id=agent_id)
    return ad.call_tool(server, tool, arguments or {}, timeout_s=timeout_s)


def metrics(ad, server: str) -> list[dict]:
    entry = ad.find(server)
    if entry is None:
        raise NotInstalled(server)
    return ad.metrics(entry["id"])


def listing(db) -> list[dict]:
    return db.rows("SELECT DISTINCT ON (mcp_server_name) mcp_server_name AS name, registry_source, version, license, "
                   "status, approved_by, health_status, active, observe_until, created_at FROM tool_installations "
                   "ORDER BY mcp_server_name, created_at DESC")
