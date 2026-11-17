"""allmail-mcp: callers reach only their own mailboxes; reads are low risk; send and trash need a
hash-bound human approval; credentials never appear in results or receipts."""
import asyncio
import importlib
import sys

import pytest

pytest.importorskip("fastmcp")   # installed in CI; same gating as tests/unit/test_mcp_common.py

from fastmcp import Client  # noqa: E402
from fastmcp.exceptions import ToolError  # noqa: E402

from dbkit import HOST, PORT, USER  # noqa: E402
from revenueos_common.canonical import args_hash  # noqa: E402
from revenueos_common.secrets import KeychainStore  # noqa: E402

PASSWORD = "-".join(["mailbox", "pass", "x9"])


class FakeIMAP:
    capabilities = ("IMAP4rev1", "STARTTLS")
    logins = []

    def __init__(self, host, port, timeout=None):
        self.host = host

    def starttls(self, ssl_context=None):
        pass

    def login(self, user, pw):
        FakeIMAP.logins.append((self.host, user, pw == PASSWORD))

    def select(self, folder, readonly=False):
        return "OK", [b"1"]

    def uid(self, cmd, *args):
        if cmd == "search":
            return "OK", [b"3 7"]
        if cmd == "fetch":
            raw = b"From: svc@signup.test\r\nSubject: Your verification code\r\nDate: Sat, 14 Nov 2026 10:00:00 +0000\r\n\r\nCode 123456\r\n"
            return "OK", [(b"7 (UID 7)", raw)]
        return "OK", [b""]

    def logout(self):
        pass


class FakeSMTP:
    sent = []

    def __init__(self, host, port, timeout=None):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def ehlo(self):
        pass

    def has_extn(self, name):
        return True

    def starttls(self, context=None):
        pass

    def login(self, user, pw):
        assert pw == PASSWORD

    def send_message(self, msg):
        FakeSMTP.sent.append(msg)
        return {}


@pytest.fixture
def allmail(db, world, tmp_path, monkeypatch):
    for k, v in {"PGHOST": HOST, "PGPORT": PORT, "PGUSER": USER, "PGDATABASE": db.name,
                 "REVENUEOS_KEYCHAIN_DIR": str(tmp_path / "kc"), "ALLMAIL_ACCOUNTS": str(tmp_path / "accounts.yaml")}.items():
        monkeypatch.setenv(k, v)
    kc = KeychainStore(tmp_path / "kc")
    kc.put("mcp-allmail-token", "t")
    kc.put("exec-mail-password", PASSWORD)
    kc.put("gmail-ops", PASSWORD)
    db.q(f"UPDATE agent_identities SET meta = jsonb_build_object('password_ref','keychain://exec-mail-password') "
         f"WHERE agent_id='{world['exec']}' AND kind='email'")
    (tmp_path / "accounts.yaml").write_text(
        f"accounts:\n  - {{address: ops@gmail.com, provider: gmail, secret_ref: 'keychain://gmail-ops', agents: ['{world['exec']}']}}\n")
    sys.modules.pop("revenueos_mcp_allmail.server", None)
    mod = importlib.import_module("revenueos_mcp_allmail.server")
    monkeypatch.setattr(mod.imaplib, "IMAP4", FakeIMAP)
    monkeypatch.setattr(mod.imaplib, "IMAP4_SSL", lambda host, port, ssl_context=None, timeout=None: FakeIMAP(host, port))
    monkeypatch.setattr(mod.smtplib, "SMTP", FakeSMTP)
    FakeIMAP.logins, FakeSMTP.sent = [], []
    return mod


def call(server, tool, **envelope):
    async def go():
        async with Client(server.mcp) as c:
            return await c.call_tool(tool, envelope)
    return asyncio.run(go())


def test_agent_lists_its_own_selfhosted_inbox(allmail, db, world):
    res = call(allmail.server, "mail_list", task_id=world["task"], agent_id=world["exec"],
               args={"account": "exec@agents.revenueos.test"})
    msgs = res.structured_content["result"]["messages"]
    assert [m["uid"] for m in msgs] == [7, 3] and msgs[0]["subject"] == "Your verification code"
    assert FakeIMAP.logins[0] == ("stalwart", "exec", True)   # the Stalwart principal name
    assert PASSWORD not in str(res.structured_content)
    assert PASSWORD not in "".join(db.q("SELECT row_to_json(t)::text FROM tool_calls t"))


def test_agent_cannot_read_another_agents_mailbox(allmail, world):
    with pytest.raises(ToolError, match="another agent"):
        call(allmail.server, "mail_read", task_id=world["task"], agent_id=world["ver"],
             args={"account": "exec@agents.revenueos.test", "uid": 7})


def test_external_account_only_for_assigned_agents(allmail, world):
    res = call(allmail.server, "mail_read", task_id=world["task"], agent_id=world["exec"],
               args={"account": "ops@gmail.com", "uid": 7})
    assert res.structured_content["result"]["text"].strip() == "Code 123456"
    assert FakeIMAP.logins[-1][0] == "imap.gmail.com"
    with pytest.raises(ToolError, match="not assigned"):
        call(allmail.server, "mail_list", task_id=world["task"], agent_id=world["ver"], args={"account": "ops@gmail.com"})
    with pytest.raises(ToolError, match="no mailbox"):
        call(allmail.server, "mail_list", task_id=world["task"], agent_id=world["exec"], args={"account": "who@x.test"})


def test_send_needs_the_human_click_then_sends_once(allmail, db, world):
    args = {"account": "exec@agents.revenueos.test", "to": ["lead@example.com"], "subject": "Hi", "text": "Hello"}
    with pytest.raises(ToolError):
        call(allmail.server, "mail_send", task_id=world["task"], agent_id=world["exec"], args=args)
    assert FakeSMTP.sent == []
    a = db.one(f"INSERT INTO approvals(task_id, tool_call_args_hash, requested_by, expires_at, tool) "
               f"VALUES ('{world['task']}','{args_hash(args)}','agent:exec',now()+interval '5 minutes','mail_send') RETURNING id")
    db.q(f"SELECT approval_decide('{a}','human:owner',true)")
    res = call(allmail.server, "mail_send", task_id=world["task"], agent_id=world["exec"], args=args, approval_id=a)
    assert res.structured_content["result"] == {"sent": True, "refused": []}
    assert len(FakeSMTP.sent) == 1 and FakeSMTP.sent[0]["From"] == "exec@agents.revenueos.test"
    with pytest.raises(ToolError):   # single use
        call(allmail.server, "mail_send", task_id=world["task"], agent_id=world["exec"], args=args, approval_id=a)
    assert len(FakeSMTP.sent) == 1


def test_trash_approval_cannot_be_spent_on_send(allmail, db, world):
    args = {"account": "exec@agents.revenueos.test", "uid": 7}
    a = db.one(f"INSERT INTO approvals(task_id, tool_call_args_hash, requested_by, expires_at, tool) "
               f"VALUES ('{world['task']}','{args_hash(args)}','agent:exec',now()+interval '5 minutes','mail_trash') RETURNING id")
    db.q(f"SELECT approval_decide('{a}','human:owner',true)")
    res = call(allmail.server, "mail_trash", task_id=world["task"], agent_id=world["exec"], args=args, approval_id=a)
    assert res.structured_content["result"] == {"trashed": True, "uid": 7}


def test_missing_credentials_are_refused(allmail, db, world, tmp_path):
    (tmp_path / "kc" / "exec-mail-password").unlink()
    with pytest.raises(ToolError, match="not in the vault"):
        call(allmail.server, "mail_list", task_id=world["task"], agent_id=world["exec"],
             args={"account": "exec@agents.revenueos.test"})
