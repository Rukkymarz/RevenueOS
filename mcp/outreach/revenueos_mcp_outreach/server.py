"""outreach MCP (C14, spec 6.3): compliant cold-email drafts and approval-gated release.

outreach_draft   (low)   builds and checks a message (identity, postal address, unsubscribe, honest subject,
                         suppression list) and stores it as a draft.
outreach_send    (high)  needs a hash-bound human approval (INV-06). Releases a draft only to recipient
                         domains in OUTREACH_SEND_DOMAINS (default: the internal test domain); any other
                         recipient is HELD, because external email is not enabled until the owner enables it.
outreach_suppress (low)  adds an address to the suppression list (unsubscribe, bounce, complaint).
A daily cap per agent protects sender reputation. Credentials are read by reference, never returned.
"""
import os
import re
import smtplib
import ssl
from email.message import EmailMessage

from pydantic import BaseModel, Field
from revenueos_mcp_common import create_server

server = create_server("outreach", token_ref=os.environ.get("OUTREACH_TOKEN_REF", "keychain://mcp-outreach-token"))
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SMTP_HOST = (os.environ.get("OUTREACH_SMTP_HOST", "stalwart"), int(os.environ.get("OUTREACH_SMTP_PORT", 587)))


def send_domains() -> set[str]:
    return {d.strip().lower() for d in os.environ.get("OUTREACH_SEND_DOMAINS", "agents.revenueos.test").split(",") if d.strip()}


def daily_cap() -> int:
    return int(os.environ.get("OUTREACH_DAILY_CAP", "25"))


class DraftArgs(BaseModel):
    to: str = Field(max_length=254)
    subject: str = Field(min_length=3, max_length=200)
    body: str = Field(min_length=20, max_length=20_000)
    sender_name: str = Field(min_length=2, max_length=100)
    postal_address: str = Field(min_length=10, max_length=300)


class SendArgs(BaseModel):
    message_id: str = Field(pattern=r"^[0-9a-fA-F-]{36}$")


class SuppressArgs(BaseModel):
    address: str = Field(max_length=254)
    reason: str = Field(default="unsubscribe", max_length=200)


def compliance(a: DraftArgs) -> list[str]:
    problems = []
    if not EMAIL.match(a.to):
        problems.append("recipient is not an email address")
    if re.match(r"^\s*(re|fw|fwd)\s*:", a.subject, re.I):
        problems.append("subject fakes a reply or forward (deceptive)")
    letters = [c for c in a.subject if c.isalpha()]
    if len(letters) > 8 and sum(c.isupper() for c in letters) / len(letters) > 0.7:
        problems.append("subject is mostly capitals")
    return problems


def footer(a: DraftArgs) -> str:
    return (f"\n\n--\n{a.sender_name}\n{a.postal_address}\n"
            "If you would rather not hear from us, reply STOP and we will not contact you again.")


@server.tool("outreach_draft", risk_class="low", args_model=DraftArgs)
def outreach_draft(args: dict, ctx: dict) -> dict:
    a = DraftArgs.model_validate(args)
    to = a.to.strip().lower()
    problems = compliance(a)
    if problems:
        raise ValueError("not compliant: " + "; ".join(problems))
    if server.db.one("SELECT 1 AS x FROM outreach_suppressions WHERE address = $a", a=to):
        mid = server.db.scalar(
            "INSERT INTO outreach_messages(task_id, agent_id, to_address, subject, body, status, note) "
            "VALUES ($t::uuid, $g::uuid, $a, $s, $b, 'suppressed', 'recipient is on the suppression list') RETURNING id",
            t=ctx["task_id"], g=ctx["agent_id"], a=to, s=a.subject, b="", )
        return {"message_id": str(mid), "status": "suppressed"}
    body = a.body.rstrip() + footer(a)
    mid = server.db.scalar(
        "INSERT INTO outreach_messages(task_id, agent_id, to_address, subject, body, status) "
        "VALUES ($t::uuid, $g::uuid, $a, $s, $b, 'draft') RETURNING id",
        t=ctx["task_id"], g=ctx["agent_id"], a=to, s=a.subject, b=body)
    return {"message_id": str(mid), "status": "draft", "checks": ["identity", "postal_address", "unsubscribe", "honest_subject", "suppression"]}


def _dispatch(agent_id: str, to: str, subject: str, body: str) -> None:
    row = server.db.one("SELECT address, meta->>'password_ref' AS pw, coalesce(meta->>'login', split_part(address,'@',1)) AS login "
                        "FROM agent_identities WHERE kind='email' AND status='active' AND agent_id = $a::uuid", a=agent_id)
    password = server.secrets.get(row["pw"]) if row and row["pw"] else None
    if not row or not password:
        raise PermissionError("the sending agent has no mailbox credentials in the vault")
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = row["address"], to, subject
    msg.set_content(body)
    ctx = ssl.create_default_context()
    ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE   # self-hosted mail inside the compose network
    with smtplib.SMTP(*SMTP_HOST, timeout=20) as s:
        s.ehlo()
        s.starttls(context=ctx)
        s.ehlo()
        s.login(row["login"], password)
        s.send_message(msg)


@server.tool("outreach_send", risk_class="high", args_model=SendArgs)
def outreach_send(args: dict, ctx: dict) -> dict:
    a = SendArgs.model_validate(args)
    m = server.db.one("SELECT id::text AS id, agent_id::text AS agent, to_address AS to_, subject, body, status "
                      "FROM outreach_messages WHERE id = $i::uuid", i=a.message_id)
    if m is None or m["agent"] != ctx["agent_id"]:
        raise PermissionError("no such draft for this agent")
    if m["status"] != "draft":
        raise ValueError(f"message is {m['status']}, not a draft")
    if server.db.one("SELECT 1 AS x FROM outreach_suppressions WHERE address = $a", a=m["to_"]):
        server.db.rows("UPDATE outreach_messages SET status='suppressed', note='suppressed before release' WHERE id=$i::uuid RETURNING id", i=m["id"])
        return {"message_id": m["id"], "status": "suppressed"}
    sent_today = server.db.scalar("SELECT count(*) AS n FROM outreach_messages WHERE agent_id=$g::uuid AND status='sent' "
                                  "AND created_at > now() - interval '1 day'", g=ctx["agent_id"])
    if int(sent_today) >= daily_cap():
        raise ValueError(f"daily cap of {daily_cap()} reached for this agent")
    if m["to_"].rsplit("@", 1)[-1] not in send_domains():
        server.db.rows("UPDATE outreach_messages SET status='held', note='external send is not enabled' WHERE id=$i::uuid RETURNING id", i=m["id"])
        return {"message_id": m["id"], "status": "held", "reason": "external send is not enabled; recipient domain is not in OUTREACH_SEND_DOMAINS"}
    _dispatch(ctx["agent_id"], m["to_"], m["subject"], m["body"])
    server.db.rows("UPDATE outreach_messages SET status='sent' WHERE id=$i::uuid RETURNING id", i=m["id"])
    return {"message_id": m["id"], "status": "sent"}


@server.tool("outreach_suppress", risk_class="low", args_model=SuppressArgs)
def outreach_suppress(args: dict) -> dict:
    a = SuppressArgs.model_validate(args)
    server.db.rows("INSERT INTO outreach_suppressions(address, reason) VALUES ($a, $r) ON CONFLICT DO NOTHING RETURNING address",
                   a=a.address.strip().lower(), r=a.reason)
    return {"suppressed": a.address.strip().lower()}


app = server.http_app()


def main() -> None:  # pragma: no cover - process entrypoint
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8205)))


if __name__ == "__main__":  # pragma: no cover
    main()
