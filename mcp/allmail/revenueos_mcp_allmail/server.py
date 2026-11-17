"""allmail-mcp (spec 2.1; named-not-found, so D1: native implementation on mcp-common).

One MCP surface over IMAP read and SMTP send for:
  * each agent's own self-hosted mailbox (AgenticMail on Stalwart), resolved from its active
    email identity; its password is read by reference from the vault;
  * external accounts (Gmail, iCloud, Zoho, Fastmail, any IMAP/SMTP host) listed in
    config/allmail-accounts.yaml with a secret reference and the agents allowed to use them.

A caller may only use mailboxes that belong to it. Reading is low risk. Sending and trashing are
high risk: mcp-common refuses them without a consumed, hash-bound human approval (INV-06) — the
"human click". Credentials never appear in results, receipts or logs.
"""
import email
import email.policy
import imaplib
import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from revenueos_mcp_common import create_server

PRESETS = {   # provider -> (imap host, imap port, imap ssl, smtp host, smtp port, smtp mode)
    "gmail":    ("imap.gmail.com", 993, True, "smtp.gmail.com", 587, "starttls"),
    "icloud":   ("imap.mail.me.com", 993, True, "smtp.mail.me.com", 587, "starttls"),
    "zoho":     ("imap.zoho.com", 993, True, "smtp.zoho.com", 587, "starttls"),
    "fastmail": ("imap.fastmail.com", 993, True, "smtp.fastmail.com", 465, "ssl"),
}
SELF_HOSTED = (os.environ.get("ALLMAIL_SELFHOSTED_IMAP_HOST", "stalwart"), int(os.environ.get("ALLMAIL_SELFHOSTED_IMAP_PORT", 143)),
               os.environ.get("ALLMAIL_SELFHOSTED_SMTP_HOST", "stalwart"), int(os.environ.get("ALLMAIL_SELFHOSTED_SMTP_PORT", 587)))
ACCOUNTS_FILE = Path(os.environ.get("ALLMAIL_ACCOUNTS", "/src/config/allmail-accounts.yaml"))

server = create_server("allmail", token_ref=os.environ.get("ALLMAIL_TOKEN_REF", "keychain://mcp-allmail-token"))


class AccessDenied(PermissionError):
    pass


@dataclass
class Account:
    address: str
    username: str
    password: str
    imap: tuple[str, int, bool]
    smtp: tuple[str, int, str]


def _external(address: str, agent_id: str) -> Account | None:
    if not ACCOUNTS_FILE.exists():
        return None
    for a in (yaml.safe_load(ACCOUNTS_FILE.read_text()) or {}).get("accounts", []):
        if a["address"].lower() != address.lower():
            continue
        if agent_id not in a.get("agents", []):
            raise AccessDenied(f"{address} is not assigned to this agent")
        p = PRESETS.get(a.get("provider", ""))
        imap = (a["imap_host"], int(a.get("imap_port", 993)), bool(a.get("imap_ssl", True))) if not p else p[:3]
        smtp = (a["smtp_host"], int(a.get("smtp_port", 587)), a.get("smtp_mode", "starttls")) if not p else p[3:]
        password = server.secrets.get(a["secret_ref"])
        if not password:
            raise AccessDenied(f"credentials for {address} are not in the vault")
        return Account(a["address"], a.get("username", a["address"]), password, imap, smtp)
    return None


def resolve(address: str, agent_id: str) -> Account:
    """The mailbox at `address`, only if it belongs to the calling agent."""
    row = server.db.one(
        "SELECT agent_id::text AS agent, meta->>'password_ref' AS pw, "
        "coalesce(meta->>'login', split_part(address, '@', 1)) AS login FROM agent_identities "
        "WHERE kind='email' AND status='active' AND lower(address)=lower($addr)", addr=address)
    if row is not None:
        if row["agent"] != agent_id:
            raise AccessDenied(f"{address} belongs to another agent")
        password = server.secrets.get(row["pw"]) if row["pw"] else None
        if not password:
            raise AccessDenied(f"credentials for {address} are not in the vault")
        h, p, sh, sp = SELF_HOSTED
        return Account(address, row["login"], password, (h, p, False), (sh, sp, "starttls-optional"))
    ext = _external(address, agent_id)
    if ext is None:
        raise AccessDenied(f"no mailbox {address} is configured for this agent")
    return ext


def _internal_tls() -> ssl.SSLContext:
    # Self-hosted mail inside the compose network uses Stalwart's generated certificate.
    ctx = ssl.create_default_context()
    ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
    return ctx


def _imap(acct: Account) -> imaplib.IMAP4:
    host, port, use_ssl = acct.imap
    if use_ssl:
        conn = imaplib.IMAP4_SSL(host, port, ssl_context=ssl.create_default_context(), timeout=20)
    else:
        conn = imaplib.IMAP4(host, port, timeout=20)
        if "STARTTLS" in conn.capabilities:
            conn.starttls(ssl_context=_internal_tls())
    conn.login(acct.username, acct.password)
    return conn


def _smtp(acct: Account) -> smtplib.SMTP:
    host, port, mode = acct.smtp
    if mode == "ssl":
        s = smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=20)
    else:
        s = smtplib.SMTP(host, port, timeout=20)
        s.ehlo()
        if mode == "starttls" or s.has_extn("starttls"):
            s.starttls(context=ssl.create_default_context() if mode == "starttls" else _internal_tls())
            s.ehlo()
    s.login(acct.username, acct.password)
    return s


def _folder(name: str) -> str:
    return '"' + name.replace("\\", "").replace('"', "") + '"'


class ListArgs(BaseModel):
    account: str = Field(max_length=254)
    folder: str = Field(default="INBOX", max_length=100)
    limit: int = Field(default=20, ge=1, le=200)


class ReadArgs(BaseModel):
    account: str = Field(max_length=254)
    uid: int = Field(ge=1)
    folder: str = Field(default="INBOX", max_length=100)


class SendArgs(BaseModel):
    account: str = Field(max_length=254)
    to: list[str] = Field(min_length=1, max_length=50)
    subject: str = Field(max_length=500)
    text: str = Field(max_length=100_000)


@server.tool("mail_list", risk_class="low", args_model=ListArgs)
def mail_list(args: dict, ctx: dict) -> dict:
    a = ListArgs.model_validate(args)
    conn = _imap(resolve(a.account, ctx["agent_id"]))
    try:
        conn.select(_folder(a.folder), readonly=True)
        _, data = conn.uid("search", None, "ALL")
        uids = [int(u) for u in (data[0] or b"").split()][-a.limit:]
        out = []
        for uid in reversed(uids):
            _, msg = conn.uid("fetch", str(uid), "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
            hdr = email.message_from_bytes(msg[0][1], policy=email.policy.default) if msg and msg[0] else {}
            out.append({"uid": uid, "from": str(hdr.get("from", "")), "subject": str(hdr.get("subject", "")),
                        "date": str(hdr.get("date", ""))})
        return {"folder": a.folder, "messages": out}
    finally:
        conn.logout()


@server.tool("mail_read", risk_class="low", args_model=ReadArgs)
def mail_read(args: dict, ctx: dict) -> dict:
    a = ReadArgs.model_validate(args)
    conn = _imap(resolve(a.account, ctx["agent_id"]))
    try:
        conn.select(_folder(a.folder), readonly=True)
        _, msg = conn.uid("fetch", str(a.uid), "(BODY.PEEK[])")
        if not msg or not msg[0] or not isinstance(msg[0], tuple):
            return {"found": False}
        m = email.message_from_bytes(msg[0][1], policy=email.policy.default)
        body = m.get_body(preferencelist=("plain", "html"))
        return {"found": True, "from": str(m["from"]), "subject": str(m["subject"]), "date": str(m["date"]),
                "text": body.get_content()[:100_000] if body else ""}
    finally:
        conn.logout()


@server.tool("mail_send", risk_class="high", args_model=SendArgs)
def mail_send(args: dict, ctx: dict) -> dict:
    a = SendArgs.model_validate(args)
    acct = resolve(a.account, ctx["agent_id"])
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = acct.address, ", ".join(a.to), a.subject
    msg.set_content(a.text)
    with _smtp(acct) as s:
        refused = s.send_message(msg)
    return {"sent": True, "refused": sorted(refused)}


@server.tool("mail_trash", risk_class="high", args_model=ReadArgs)
def mail_trash(args: dict, ctx: dict) -> dict:
    a = ReadArgs.model_validate(args)
    conn = _imap(resolve(a.account, ctx["agent_id"]))
    try:
        conn.select(_folder(a.folder))
        typ, _ = conn.uid("move", str(a.uid), _folder("Trash"))
        if typ != "OK":
            conn.uid("store", str(a.uid), "+FLAGS", r"(\Deleted)")
        return {"trashed": True, "uid": a.uid}
    finally:
        conn.logout()


app = server.http_app()


def main() -> None:  # pragma: no cover - process entrypoint
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8202)))


if __name__ == "__main__":  # pragma: no cover
    main()
