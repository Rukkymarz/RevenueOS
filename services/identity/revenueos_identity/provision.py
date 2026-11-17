"""One-command agent identity provisioning (spec 2.1, Acceptance 2): email, calendar, browser
profile and phone, plus the egress rules the agent needs to reach its own inbox.

Every identity is an agent_identities row (the INV-09 guard and audit trigger apply); secrets go
to the vault by reference and never to the database, logs or output. The agent's own mail API
key is bound to the AgenticMail host in secret_bindings, so the egress proxy injects it and the
agent itself never holds it.
"""
import os
from dataclasses import dataclass, field
from pathlib import Path

from revenueos_common.db import Database
from revenueos_common.secrets import SecretResolver

from . import providers
from .profiles import create_profile


@dataclass
class Settings:
    agenticmail_url: str = os.environ.get("AGENTICMAIL_URL", "http://agenticmail:3829")
    agenticmail_host: str = os.environ.get("AGENTICMAIL_EGRESS_HOST", "agenticmail:3829")
    stalwart_url: str = os.environ.get("STALWART_URL", "http://stalwart:8080")
    mail_domain: str = os.environ.get("REVENUEOS_MAIL_DOMAIN", "agents.revenueos.test")
    profile_root: str = os.environ.get("REVENUEOS_PROFILE_ROOT", "/var/lib/revenueos/profiles")
    master_key_ref: str = "keychain://agenticmail-master-key"


PHONE_DEFERRED = "phone descoped by the owner (2026-11-15); enable with --phone-carrier twilio|46elks"


@dataclass
class Provisioned:
    agent_id: str
    identities: dict = field(default_factory=dict)   # kind -> {status, address|profile_path, reason?}
    egress_hosts: list = field(default_factory=list)


def _identity(db: Database, agent_id, kind, provider, *, status="active", address=None, profile_path=None,
              secret_ref=None, meta=None) -> str:
    return db.scalar(
        "INSERT INTO agent_identities(agent_id, kind, provider, status, address, profile_path, secret_ref, meta) "
        "VALUES ($agent::uuid, $kind::identity_kind, $provider, $status, nullif($address,''), nullif($path,''), "
        "nullif($ref,''), #meta) RETURNING id",
        agent=agent_id, kind=kind, provider=provider, status=status, address=address or "", path=profile_path or "",
        ref=secret_ref or "", meta=meta or {})


def _active(db: Database, agent_id: str, kind: str) -> dict | None:
    return db.one("SELECT id::text AS id, address, profile_path FROM agent_identities "
                  "WHERE agent_id=$a::uuid AND kind=$k::identity_kind AND status='active' ORDER BY created_at LIMIT 1",
                  a=agent_id, k=kind)


def provision(db: Database, vault: SecretResolver, name: str, role: str, *, allow_hosts=(), phone_carrier=None,
              settings: Settings | None = None, mail=None, caldav=providers.caldav_home) -> Provisioned:
    s = settings or Settings()
    agent_id = db.scalar(
        "INSERT INTO agents(name, role, framework, budget_monthly) VALUES ($name, $role, 'langgraph', 50) "
        "ON CONFLICT (name) DO UPDATE SET updated_at = now() RETURNING id", name=name, role=role)
    out = Provisioned(agent_id=agent_id)

    # Email (AgenticMail on Stalwart): agent key and mailbox password go to the vault only.
    email = _active(db, agent_id, "email")
    key_ref, pw_ref = f"keychain://agent-{agent_id}-mail-api-key", f"keychain://agent-{agent_id}-mail-password"
    if email is None:
        am = mail or providers.AgenticMail(s.agenticmail_url, vault.get(s.master_key_ref))
        mb = am.create_mailbox(name, s.mail_domain, {"revenueos_agent_id": agent_id})
        vault.put(key_ref, mb.api_key)
        vault.put(pw_ref, mb.password)
        _identity(db, agent_id, "email", "agenticmail", address=mb.email, secret_ref=key_ref,
                  meta={"account_id": mb.account_id, "password_ref": pw_ref, "login": mb.login})
    email = db.one("SELECT address, coalesce(meta->>'login', split_part(address, '@', 1)) AS login FROM agent_identities "
                   "WHERE agent_id=$a::uuid AND kind='email' AND status='active' ORDER BY created_at LIMIT 1", a=agent_id)
    out.identities["email"] = {"status": "active", "address": email["address"]}

    # Calendar: the mailbox's own CalDAV home on Stalwart, discovered with its own credentials.
    cal = _active(db, agent_id, "calendar")
    if cal is None:
        try:
            url = caldav(s.stalwart_url, email["login"], vault.get(pw_ref))
        except providers.ProviderError as e:   # recorded with its reason, never faked
            _identity(db, agent_id, "calendar", "stalwart-caldav", status="pending", meta={"reason": str(e)})
            out.identities["calendar"] = {"status": "pending", "reason": str(e)}
        else:
            _identity(db, agent_id, "calendar", "stalwart-caldav", address=url, secret_ref=pw_ref)
            out.identities["calendar"] = {"status": "active", "address": url}
    else:
        out.identities["calendar"] = {"status": "active", "address": cal["address"]}

    # Browser profile: private directory under the profile root (INV-09 guard checks the path).
    prof = _active(db, agent_id, "browser_profile")
    if prof is None:
        path = create_profile(s.profile_root, agent_id)
        _identity(db, agent_id, "browser_profile", "chromium", profile_path=str(path))
        prof = {"profile_path": str(path)}
    out.identities["browser_profile"] = {"status": "active", "profile_path": prof["profile_path"]}

    # Phone: descoped by the owner on 2026-11-15. Provisioning skips it unless a carrier is named;
    # even then it never buys a number: request-phone / complete-phone do that only after a human
    # approves that exact purchase (INV-06).
    phone = _active(db, agent_id, "phone")
    if phone is not None:
        out.identities["phone"] = {"status": "active", "address": phone["address"]}
    elif not phone_carrier:
        out.identities["phone"] = {"status": "deferred", "reason": PHONE_DEFERRED}
    else:
        try:
            providers.carrier(phone_carrier, vault)
            reason = f"{phone_carrier} configured; the number purchase needs an approved request (request-phone)"
        except providers.NotConfigured as e:
            reason = str(e)
            db.scalar("SELECT credential_report('phone', $ref, 'UNCONFIGURED') IS NULL AS ok",
                      ref=providers.CARRIER_REFS[phone_carrier][0])
        if db.one("SELECT id FROM agent_identities WHERE agent_id=$a::uuid AND kind='phone' AND status='pending'",
                  a=agent_id) is None:
            _identity(db, agent_id, "phone", phone_carrier, status="pending", meta={"reason": reason})
        out.identities["phone"] = {"status": "pending", "reason": reason}

    # Egress: the agent's own inbox (its key injected by the proxy) plus any task hosts.
    for host in [s.agenticmail_host, *allow_hosts]:
        db.scalar("INSERT INTO egress_rules(agent_id, host, created_by) VALUES ($a::uuid, $h, 'identity-service') "
                  "ON CONFLICT DO NOTHING RETURNING id", a=agent_id, h=host.lower())
        out.egress_hosts.append(host.lower())
    db.scalar("INSERT INTO secret_bindings(secret_ref, host, header, format, agent_ids) "
              "VALUES ($ref, $host, 'authorization', 'Bearer {}', ARRAY[$a]::uuid[]) "
              "ON CONFLICT (host, header, secret_ref) DO NOTHING RETURNING id",
              ref=key_ref, host=s.agenticmail_host, a=agent_id)
    return out


def rotate_browser_profile(db: Database, agent_id: str, settings: Settings | None = None) -> str:
    """New profile first, then retire the old one, so the agent is never without a profile."""
    s = settings or Settings()
    old = _active(db, agent_id, "browser_profile")
    path = create_profile(s.profile_root, agent_id)
    db.scalar(
        "INSERT INTO agent_identities(agent_id, kind, provider, profile_path, rotated_from) "
        "VALUES ($a::uuid, 'browser_profile', 'chromium', $p, nullif($old,'')::uuid) RETURNING id",
        a=agent_id, p=str(path), old=old["id"] if old else "")
    if old:
        db.scalar("UPDATE agent_identities SET status='retired' WHERE id=$id::uuid RETURNING id", id=old["id"])
    return str(path)


PHONE_TOOL = "phone_purchase"
E164 = r"^\+[1-9][0-9]{6,14}$"


def request_phone(db: Database, vault: SecretResolver, agent_id: str, carrier: str, country: str = "US",
                  area_code: str | None = None, number: str | None = None) -> dict:
    """Open a critical approval for one exact phone purchase (or for attaching an existing number
    the owner controls, e.g. a Google Voice number on the agent's own Google account)."""
    import re
    if carrier == "existing":
        if not number or not re.match(E164, number):
            raise ValueError("an existing number must be given in E.164 form, e.g. +14045551234")
    else:
        providers.carrier(carrier, vault)   # NotConfigured without vault credentials
        number = None
    args = {"agent_id": agent_id, "carrier": carrier, "country": country.upper(), "area_code": area_code or "",
            "number": number or ""}
    from revenueos_common.canonical import args_hash
    task = db.scalar("INSERT INTO tasks(objective, task_class, acceptance_criteria) VALUES ($o, 'identity.phone', "
                     "'[{\"check\":\"phone_identity_active\"}]'::jsonb) RETURNING id",
                     o=f"Provision a phone number for agent {agent_id} via {carrier}")
    approval = db.scalar(
        "INSERT INTO approvals(task_id, tool_call_args_hash, requested_by, expires_at, mcp_server, tool, args_preview, risk_class) "
        "VALUES ($t::uuid, $h, 'service:identity', now() + interval '1 hour', 'identity', $tool, #args, 'critical') RETURNING id",
        t=task, h=args_hash(args), tool=PHONE_TOOL, args=args)
    return {"approval_id": approval, "task_id": task, "args": args}


def complete_phone(db: Database, vault: SecretResolver, approval_id: str, session=None) -> dict:
    """Spend the approval on exactly the requested purchase, then record the active identity."""
    from revenueos_common.canonical import args_hash
    row = db.one("SELECT task_id::text AS task, args_preview AS args FROM approvals WHERE id=$id::uuid AND tool=$tool",
                 id=approval_id, tool=PHONE_TOOL)
    if row is None:
        raise PermissionError("no phone purchase approval with that id")
    args = row["args"]
    ok = db.scalar("SELECT consume_approval($id::uuid, $h, $t::uuid, $tool) AS ok", id=approval_id, h=args_hash(args),
                   t=row["task"], tool=PHONE_TOOL)
    if ok not in (True, "t", "true"):
        why = db.scalar("SELECT payload->>'reason' FROM audit_log WHERE target=$id AND action='approval.consume_rejected' "
                        "ORDER BY seq DESC LIMIT 1", id=approval_id)
        raise PermissionError(f"phone purchase not approved: {why or 'refused'}")
    if args["carrier"] == "existing":
        bought = {"number": args["number"], "carrier_id": ""}
    else:
        bought = providers.carrier(args["carrier"], vault, session).buy_number(args["country"], args["area_code"] or None)
    agent = args["agent_id"]
    db.scalar("UPDATE agent_identities SET status='retired' WHERE agent_id=$a::uuid AND kind='phone' AND status='pending' "
              "RETURNING id", a=agent)
    _identity(db, agent, "phone", args["carrier"], address=bought["number"],
              meta={"carrier_id": bought["carrier_id"], "approval_id": approval_id})
    if args["carrier"] in providers.CARRIER_REFS:
        db.scalar("SELECT credential_report('phone', $ref, 'READY') IS NULL AS ok", ref=providers.CARRIER_REFS[args["carrier"]][0])
    return {"agent_id": agent, "number": bought["number"], "carrier": args["carrier"]}
