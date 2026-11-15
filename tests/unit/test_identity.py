"""Identity service (C05): providers, profiles, one-command provisioning, the leads agent."""
import http.server
import json
import threading
from pathlib import Path

import pytest

from dbkit import HOST, PORT, USER
from revenueos_common.db import Database
from revenueos_common.secrets import KeychainStore, SecretResolver
from revenueos_identity import leads, leads_agent, provision, providers
from revenueos_identity.profiles import create_profile, fingerprint


# --------------------------------------------------------------------------- providers
class FakeResponse:
    def __init__(self, status, body=None, content=None):
        self.status_code, self._body = status, body
        self.content = content if content is not None else (json.dumps(body).encode() if body is not None else b"")
        self.text = self.content.decode()

    def json(self):
        return self._body


class FakeSession:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def _next(self, method, url, **kw):
        self.calls.append((method, url, kw))
        return self.responses.pop(0)

    def post(self, url, **kw):
        return self._next("POST", url, **kw)

    def get(self, url, **kw):
        return self._next("GET", url, **kw)

    def request(self, method, url, **kw):
        return self._next(method, url, **kw)


def test_agenticmail_creates_mailbox_with_master_key_and_own_password():
    http = FakeSession([FakeResponse(201, {"id": "a1", "email": "lead@agents.revenueos.test", "apiKey": "ak_x",
                                           "stalwartPrincipal": "lead"})])
    mb = providers.AgenticMail("http://am:3829", "mk_master", http).create_mailbox("lead", "agents.revenueos.test", {})
    method, url, kw = http.calls[0]
    assert (method, url) == ("POST", "http://am:3829/api/agenticmail/accounts")
    assert kw["headers"]["authorization"] == "Bearer mk_master" and kw["json"]["password"] == mb.password
    assert mb.email == "lead@agents.revenueos.test" and mb.api_key == "ak_x" and len(mb.password) >= 24
    assert mb.login == "lead"


def test_agenticmail_without_master_key_is_not_configured_and_errors_surface():
    with pytest.raises(providers.NotConfigured):
        providers.AgenticMail("http://am", None)
    bad = providers.AgenticMail("http://am", "mk", FakeSession([FakeResponse(409, {"error": "exists"})]))
    with pytest.raises(providers.ProviderError, match="409"):
        bad.create_mailbox("x", "d.test", {})


def test_caldav_discovery_follows_principal_to_calendar_home():
    principal = (b'<d:multistatus xmlns:d="DAV:"><d:response><d:propstat><d:prop><d:current-user-principal>'
                 b'<d:href>/dav/pal/lead/</d:href></d:current-user-principal></d:prop></d:propstat></d:response></d:multistatus>')
    home = (b'<d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:response><d:propstat><d:prop>'
            b'<c:calendar-home-set><d:href>/dav/cal/lead/</d:href></c:calendar-home-set></d:prop></d:propstat>'
            b'</d:response></d:multistatus>')
    http = FakeSession([FakeResponse(207, content=principal), FakeResponse(207, content=home)])
    assert providers.caldav_home("http://stalwart:8080", "lead@x.test", "pw", http) == "http://stalwart:8080/dav/cal/lead/"
    assert http.calls[0][1] == "http://stalwart:8080/.well-known/caldav" and http.calls[0][2]["auth"] == ("lead@x.test", "pw")
    with pytest.raises(providers.ProviderError):
        providers.caldav_home("http://s", "u", "p", FakeSession([FakeResponse(401, content=b"")]))


def test_hosted_fallbacks_use_their_documented_endpoints():
    am = FakeSession([FakeResponse(200, {"inbox_id": "lead@agentmail.to"})])
    assert providers.AgentMailHosted("k", am).create_inbox("lead", "Lead", "agent-1") == "lead@agentmail.to"
    assert am.calls[0][1] == "https://api.agentmail.to/v0/inboxes" and am.calls[0][2]["headers"]["authorization"] == "Bearer k"
    bu = FakeSession([FakeResponse(200, {"id": "p1"}), FakeResponse(200, {"id": "s1", "liveUrl": "u"})])
    c = providers.BrowserUseCloud("k", bu)
    assert c.create_profile("lead") == "p1" and c.create_session("p1")["id"] == "s1"
    assert bu.calls[0][1].endswith("/api/v2/profiles") and bu.calls[1][2]["json"]["profileId"] == "p1"
    assert bu.calls[0][2]["headers"]["X-Browser-Use-API-Key"] == "k"
    for ctor in (lambda: providers.AgentMailHosted(None), lambda: providers.BrowserUseCloud(""),
                 lambda: providers.ImapiBridge(None, "t")):
        with pytest.raises(providers.NotConfigured):
            ctor()
    assert providers.ImapiBridge("https://imapi.example/mcp", "t").url.endswith("/mcp")


def test_carriers_need_vault_credentials(tmp_path):
    vault = SecretResolver(KeychainStore(tmp_path / "kc"))
    for name in (None, "twilio", "46elks"):
        with pytest.raises(providers.NotConfigured):
            providers.carrier(name, vault)
    with pytest.raises(providers.ProviderError):
        providers.carrier("carrier-pigeon", vault)


def test_twilio_searches_then_buys_on_its_documented_endpoints():
    http = FakeSession([FakeResponse(200, {"available_phone_numbers": [{"phone_number": "+14045550100"}]}),
                        FakeResponse(201, {"phone_number": "+14045550100", "sid": "PN1"})])
    out = providers.Twilio("AC1", "tok", http).buy_number("US", "404")
    assert out == {"number": "+14045550100", "carrier_id": "PN1"}
    assert http.calls[0][1].endswith("/Accounts/AC1/AvailablePhoneNumbers/US/Local.json")
    assert http.calls[0][2]["params"]["AreaCode"] == "404" and http.calls[0][2]["auth"] == ("AC1", "tok")
    assert http.calls[1][1].endswith("/Accounts/AC1/IncomingPhoneNumbers.json")
    assert http.calls[1][2]["data"] == {"PhoneNumber": "+14045550100"}
    empty = providers.Twilio("AC1", "tok", FakeSession([FakeResponse(200, {"available_phone_numbers": []})]))
    with pytest.raises(providers.ProviderError, match="no US number"):
        empty.buy_number("US", None)


def test_46elks_allocates_on_its_documented_endpoint():
    http = FakeSession([FakeResponse(200, {"id": "n1", "number": "+46766860000"})])
    assert providers.FortySixElks("u", "p", http).buy_number("SE", None) == {"number": "+46766860000", "carrier_id": "n1"}
    assert http.calls[0][1] == "https://api.46elks.com/a1/numbers" and http.calls[0][2]["data"]["capabilities"] == "sms,voice"


# --------------------------------------------------------------------------- profiles
def test_profiles_are_private_and_distinct(tmp_path):
    a, b = create_profile(tmp_path, "agent-1"), create_profile(tmp_path, "agent-1")
    assert a != b and (a / "user-data").is_dir() and oct(a.stat().st_mode)[-3:] == "700"
    meta = json.loads((a / "profile.json").read_text())
    assert meta["agent_id"] == "agent-1" and meta["fingerprint"]["seed"] != json.loads((b / "profile.json").read_text())["fingerprint"]["seed"]
    assert fingerprint(42) == fingerprint(42)


# --------------------------------------------------------------------------- provisioning
class FakeMail:
    def __init__(self):
        self.created = []

    def create_mailbox(self, name, domain, metadata):
        self.created.append(name)
        return providers.Mailbox(email=f"{name}@{domain}", api_key="ak_" + "1" * 30, account_id="acc", password="p" * 24,
                                 login=name)


@pytest.fixture
def prov(db, tmp_path):
    root = tmp_path / "profiles"
    db.q(f"UPDATE settings SET value='{root}/' WHERE key='profile_root'")
    database = Database(dbname=db.name, host=HOST, port=PORT, user=USER, actor="identity-service")
    vault = SecretResolver(KeychainStore(tmp_path / "kc"))
    s = provision.Settings(profile_root=str(root), agenticmail_host="agenticmail:3829")
    return database, vault, s, db


def test_one_command_provisions_email_calendar_and_profile_with_phone_deferred(prov):
    database, vault, s, db = prov
    mail = FakeMail()
    out = provision.provision(database, vault, "leads-agent", "leads", allow_hosts=["signup-test:8090"], settings=s,
                              mail=mail, caldav=lambda url, user, pw: f"{url}/dav/cal/{user}/")
    a = out.agent_id
    assert out.identities["email"] == {"status": "active", "address": "leads-agent@agents.revenueos.test"}
    assert out.identities["calendar"]["address"].endswith("/dav/cal/leads-agent/")
    assert Path(out.identities["browser_profile"]["profile_path"]).is_dir()
    assert out.identities["phone"] == {"status": "deferred", "reason": provision.PHONE_DEFERRED}
    assert db.one(f"SELECT count(*) FROM agent_identities WHERE agent_id='{out.agent_id}' AND kind='phone'") == "0"
    # secrets only in the vault, referenced from the database
    ref = db.one(f"SELECT secret_ref FROM agent_identities WHERE agent_id='{a}' AND kind='email'")
    assert ref == f"keychain://agent-{a}-mail-api-key" and vault.get(ref) == "ak_" + "1" * 30
    assert "ak_" not in "".join(db.q("SELECT payload::text FROM audit_log"))
    # the proxy, not the agent, holds the inbox key
    assert db.one(f"SELECT format||'|'||header FROM secret_bindings WHERE secret_ref='{ref}'") == "Bearer {}|authorization"
    assert set(out.egress_hosts) == {"agenticmail:3829", "signup-test:8090"}
    assert db.one(f"SELECT count(*) FROM audit_log WHERE action='identity.active' AND target='{a}'") == "3"
    # idempotent: a second run reuses everything
    again = provision.provision(database, vault, "leads-agent", "leads", settings=s, mail=mail,
                                caldav=lambda *x: pytest.fail("calendar should be reused"))
    assert again.agent_id == a and mail.created == ["leads-agent"]
    assert db.one(f"SELECT count(*) FROM agent_identities WHERE agent_id='{a}'") == "3"


def test_naming_a_carrier_without_credentials_records_phone_pending(prov):
    database, vault, s, db = prov
    out = provision.provision(database, vault, "with-phone", "leads", settings=s, mail=FakeMail(),
                              caldav=lambda url, user, pw: f"{url}/c/", phone_carrier="twilio")
    assert out.identities["phone"]["status"] == "pending" and "Twilio" in out.identities["phone"]["reason"]
    assert db.one("SELECT status FROM credential_status WHERE integration='phone'") == "UNCONFIGURED"


def test_profile_rotation_retires_the_old_profile(prov):
    database, vault, s, db = prov
    out = provision.provision(database, vault, "rotator", "leads", settings=s, mail=FakeMail(),
                              caldav=lambda url, user, pw: f"{url}/c/")
    old = out.identities["browser_profile"]["profile_path"]
    new = provision.rotate_browser_profile(database, out.agent_id, s)
    assert new != old
    rows = db.q(f"SELECT status||'|'||profile_path||'|'||(rotated_from IS NOT NULL) FROM agent_identities "
                f"WHERE agent_id='{out.agent_id}' AND kind='browser_profile' ORDER BY created_at")
    assert rows == [f"retired|{old}|false", f"active|{new}|true"]


# --------------------------------------------------------------------------- leads agent
class _Fake(http.server.BaseHTTPRequestHandler):
    """Signup service + AgenticMail inbox in one: the email arrives after signup."""
    state = {}

    def _j(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        if self.path == "/svc/signup":
            _Fake.state["inbox"] = [{"uid": 7, "subject": "Your verification code"}]
            return self._j(202, {})
        if self.path == "/svc/verify":
            ok = body.get("code") == "123456"
            _Fake.state["verified"] = ok
            return self._j(200 if ok else 400, {"verified": ok})

    def do_GET(self):
        if self.path.startswith("/am/mail/inbox"):
            return self._j(200, {"messages": _Fake.state.get("inbox", [{"uid": 1, "subject": "old"}])})
        if self.path.startswith("/am/mail/spam"):
            return self._j(200, {"messages": [], "folder": "Junk Mail"})
        if self.path == "/am/mail/messages/7":
            return self._j(200, {"subject": "Your verification code", "text": "Code 123456. Or http://x/magic?token=abc_1"})
        if self.path.startswith("/svc/magic"):
            _Fake.state["verified"] = True
            return self._j(200, {"verified": True})
        if self.path.startswith("/svc/status"):
            return self._j(200, {"verified": _Fake.state.get("verified", False)})
        self._j(404, {})

    def log_message(self, *a):
        pass


@pytest.fixture
def fake():
    _Fake.state = {}
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_leads_agent_completes_otp_signup_and_never_prints_the_code(fake, capsys):
    assert leads_agent.main(["--email", "l@a.test", "--service", f"{fake}/svc", "--inbox", f"{fake}/am", "--timeout", "5"]) == 0
    out = capsys.readouterr().out
    steps = [json.loads(line) for line in out.splitlines()]
    assert [s["step"] for s in steps] == ["start", "inbox_access", "signup", "verification_email", "extract", "verify", "complete"]
    assert all(s["status"] == "ok" for s in steps) and "123456" not in out


def test_leads_agent_magic_link_mode(fake, capsys):
    _Fake.state = {}
    # the link in this fake email points at an unreachable host: the agent must report failure
    rc = leads_agent.run("l@a.test", f"{fake}/svc", f"{fake}/am", "magic-link", 5)
    steps = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert steps[4]["kind"] == "magic-link" and "abc_1" not in json.dumps(steps)
    assert rc != 0   # http://x is not reachable here; the real link is exercised end to end


def test_leads_agent_reports_missing_email(fake):
    _Fake.state = {"inbox": []}
    assert leads_agent.find_verification(f"{fake}/am", set(), 0) is None


def test_leads_steps_are_written_to_timeline_and_audit(db, world):
    database = Database(dbname=db.name, host=HOST, port=PORT, user=USER, actor="identity-service")
    stdout = "\n".join([json.dumps({"step": "signup", "status": "ok"}), "noise", json.dumps({"step": "complete", "status": "ok"})])
    steps = leads.record_steps(database, world["exec"], world["task"], stdout)
    assert [s["step"] for s in steps] == ["signup", "complete"]
    assert db.one(f"SELECT count(*) FROM timeline_events e JOIN timelines t ON t.id=e.timeline_id "
                  f"WHERE t.thing_id='{world['task']}'") == "2"
    assert db.one("SELECT count(*) FROM audit_log WHERE action LIKE 'leads.signup.%'") == "2"


def test_leads_signup_runs_the_agent_in_the_sandbox_with_egress(db, world, monkeypatch):
    database = Database(dbname=db.name, host=HOST, port=PORT, user=USER, actor="identity-service")
    sent = {}

    class R:
        def raise_for_status(self):
            pass

        def json(self):
            return {"status": "ok", "exit_code": 0, "stdout": json.dumps({"step": "complete", "status": "ok"}), "stderr": ""}

    def fake_post(url, json=None, timeout=None):
        sent.update(url=url, body=json)
        return R()
    monkeypatch.setattr(leads.requests, "post", fake_post)
    out = leads.leads_signup(database, world["exec"], world["task"], "http://signup-test:8090", "otp", supervisor="http://sup")
    assert out["status"] == "ok" and out["email"] == "exec@agents.revenueos.test"
    assert sent["url"] == "http://sup/v1/run" and sent["body"]["egress"] is True
    assert sent["body"]["argv"][:3] == ["python3", "-m", "revenueos_identity.leads_agent"]
    assert db.one(f"SELECT host FROM egress_rules WHERE task_id='{world['task']}'") == "signup-test:8090"


def test_leads_signup_refuses_an_agent_without_its_own_email(db, world):
    database = Database(dbname=db.name, host=HOST, port=PORT, user=USER, actor="identity-service")
    bare = db.one("INSERT INTO agents(name, role, framework, budget_monthly) VALUES ('b','x','langgraph',1) RETURNING id")
    with pytest.raises(RuntimeError, match="INV-09"):
        leads.leads_signup(database, bare, world["task"], "http://s:1")


def test_cli_dispatches_each_command(monkeypatch, capsys, tmp_path):
    from revenueos_identity import __main__ as cli
    monkeypatch.setenv("REVENUEOS_KEYCHAIN_DIR", str(tmp_path / "kc"))
    monkeypatch.setattr(provision, "provision", lambda db, vault, name, role, **kw: provision.Provisioned(agent_id="a1"))
    monkeypatch.setattr(provision, "rotate_browser_profile", lambda db, agent: "/p/new")
    monkeypatch.setattr(leads, "leads_signup", lambda db, a, t, s, m: {"status": "failed"})
    monkeypatch.setattr(provision, "request_phone", lambda db, vault, *a: {"approval_id": "ap1"})
    monkeypatch.setattr(provision, "complete_phone", lambda db, vault, ap: {"number": "+1404"})
    assert cli.main(["provision", "--name", "n", "--role", "r", "--allow", "h:1"]) == 0
    assert json.loads(capsys.readouterr().out)["agent_id"] == "a1"
    assert cli.main(["rotate-profile", "--agent-id", "a1"]) == 0
    assert json.loads(capsys.readouterr().out)["profile_path"] == "/p/new"
    assert cli.main(["leads-signup", "--agent-id", "a", "--task-id", "t", "--service", "http://s"]) == 1
    capsys.readouterr()
    assert cli.main(["request-phone", "--agent-id", "a", "--carrier", "twilio"]) == 0
    assert json.loads(capsys.readouterr().out)["approval_id"] == "ap1"
    assert cli.main(["complete-phone", "--approval-id", "ap1"]) == 0


def test_calendar_failure_is_recorded_pending_not_faked(prov):
    database, vault, s, db = prov

    def no_caldav(url, user, pw):
        raise providers.ProviderError("CalDAV PROPFIND failed: HTTP 401")
    out = provision.provision(database, vault, "cal-less", "leads", settings=s, mail=FakeMail(), caldav=no_caldav)
    assert out.identities["calendar"] == {"status": "pending", "reason": "CalDAV PROPFIND failed: HTTP 401"}
    assert out.identities["email"]["status"] == "active"



def test_phone_purchase_happens_only_after_a_human_approves_that_exact_purchase(world, prov):
    database, vault, s, db = prov
    agent = world["exec"]
    with pytest.raises(providers.NotConfigured):
        provision.request_phone(database, vault, agent, "twilio")
    vault.put("keychain://phone-twilio-account-sid", "AC1")
    vault.put("keychain://phone-twilio-auth-token", "tok")
    req = provision.request_phone(database, vault, agent, "twilio", "us", "404")
    assert req["args"] == {"agent_id": agent, "carrier": "twilio", "country": "US", "area_code": "404", "number": ""}
    http = FakeSession([FakeResponse(200, {"available_phone_numbers": [{"phone_number": "+14045550100"}]}),
                        FakeResponse(201, {"phone_number": "+14045550100", "sid": "PN1"})])
    with pytest.raises(PermissionError, match="not approved"):      # nothing bought before approval
        provision.complete_phone(database, vault, req["approval_id"], session=http)
    assert http.calls == []
    db.q(f"SELECT approval_decide('{req['approval_id']}','human:owner',true)")
    out = provision.complete_phone(database, vault, req["approval_id"], session=http)
    assert out == {"agent_id": agent, "number": "+14045550100", "carrier": "twilio"}
    assert db.one(f"SELECT address FROM agent_identities WHERE agent_id='{agent}' AND kind='phone' AND status='active'") == "+14045550100"
    with pytest.raises(PermissionError, match="reuse"):             # one approval, one purchase
        provision.complete_phone(database, vault, req["approval_id"], session=http)
    assert db.one("SELECT status FROM credential_status WHERE secret_ref='keychain://phone-twilio-account-sid'") == "READY"


def test_existing_number_is_attached_only_with_approval(world, prov):
    database, vault, s, db = prov
    with pytest.raises(ValueError):
        provision.request_phone(database, vault, world["exec"], "existing", number="404-555-0100")
    req = provision.request_phone(database, vault, world["exec"], "existing", number="+14045550123")
    db.q(f"SELECT approval_decide('{req['approval_id']}','human:owner',true)")
    assert provision.complete_phone(database, vault, req["approval_id"])["number"] == "+14045550123"
    with pytest.raises(PermissionError, match="no phone purchase approval"):
        provision.complete_phone(database, vault, "00000000-0000-4000-8000-000000000000")
