"""Phase 6 (C14): photo-generator, scraper and outreach, each driven through an MCP client so every call
leaves a tool_calls receipt (INV-02); high-risk release needs the human click (INV-06)."""
import asyncio
import importlib
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

pytest.importorskip("fastmcp")

from fastmcp import Client  # noqa: E402
from fastmcp.exceptions import ToolError  # noqa: E402

from dbkit import HOST, PORT, USER  # noqa: E402
from revenueos_common.canonical import args_hash  # noqa: E402
from revenueos_common.secrets import KeychainStore  # noqa: E402

PW = "-".join(["mail", "pass", "q7"])
PAGE = (b"<html><head><title>Acme Cleaning</title><meta name=description content='Commercial cleaning'></head><body>"
        b"<div class=hours>Mon-Fri 8-5</div><p>Call 404-555-1212 or hello@acme.example</p><a href='/contact'>Contact</a></body></html>")


class Site(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/robots.txt":
            body = b"User-agent: *\nDisallow: /private\n"
        elif self.path == "/private":
            body = PAGE
        elif self.path == "/blocked":
            self.send_response(403)
            self.end_headers()
            return
        else:
            body = PAGE
        self.send_response(200)
        self.send_header("content-type", "text/html" if self.path != "/robots.txt" else "text/plain")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):   # a fallback adapter
        n = int(self.headers.get("content-length") or 0)
        self.rfile.read(n)
        body = b'{"html": "<html><title>Rescued</title><body>via adapter</body></html>"}'
        self.send_response(200)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def site():
    srv = HTTPServer(("127.0.0.1", 0), Site)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


@pytest.fixture
def env(db, world, tmp_path, monkeypatch):
    for k, v in {"PGHOST": HOST, "PGPORT": PORT, "PGUSER": USER, "PGDATABASE": db.name,
                 "REVENUEOS_KEYCHAIN_DIR": str(tmp_path / "kc"), "PHOTO_ROOT": str(tmp_path / "photos")}.items():
        monkeypatch.setenv(k, v)
    kc = KeychainStore(tmp_path / "kc")
    kc.put("exec-mail-password", PW)
    db.q(f"UPDATE agent_identities SET meta = jsonb_build_object('password_ref','keychain://exec-mail-password') "
         f"WHERE agent_id='{world['exec']}' AND kind='email'")
    return tmp_path


def load(name):
    sys.modules.pop(name, None)
    return importlib.import_module(name)


def call(server, tool, world, args, approval=None, agent="exec"):
    async def go():
        async with Client(server.mcp) as c:
            return await c.call_tool(tool, {"task_id": world["task"], "agent_id": world[agent], "args": args,
                                            **({"approval_id": approval} if approval else {})})
    return asyncio.run(go()).structured_content["result"]


def receipts(db, tool):
    return int(db.one(f"SELECT count(*) FROM tool_calls WHERE tool='{tool}'"))


# ---------------------------------------------------------------- photo-generator
@pytest.fixture
def direction(db, world):
    pid = db.one("INSERT INTO projects(name, business_line, premise_bundle_id) "
                 f"VALUES ('site','cleaning','{world['premise']}') RETURNING id")
    return db.one("INSERT INTO design_directions(project_id, direction, rationale, palette_oklch, fonts, radius_scale, knowledge_query) "
                  f"VALUES ('{pid}','calm-clinical','{'x' * 50}', "
                  "'{\"ink\":[0.3,0.04,250],\"sky\":{\"l\":0.85,\"c\":0.06,\"h\":220},\"sun\":\"oklch(0.8 0.14 85)\"}', '{}', '{}', '{}') RETURNING id")


def test_photo_is_style_locked_and_receipted(env, db, world, direction):
    photo = load("revenueos_mcp_photo.server")
    out = call(photo.server, "photo_generate", world, {"direction_id": direction, "subject": "bright kitchen", "width": 96, "height": 54})
    assert Path(out["path"]).exists() and set(out["palette"]) == {"ink", "sky", "sun"}
    assert call(photo.server, "photo_verify", world, {"asset_id": out["asset_id"]})["verdict"] == "PASS"
    assert receipts(db, "photo_generate") == 1 and receipts(db, "photo_verify") == 1
    again = call(photo.server, "photo_generate", world, {"direction_id": direction, "subject": "bright kitchen", "width": 96, "height": 54})
    assert again["sha256"] == out["sha256"]                        # deterministic


def test_photo_off_palette_fails_and_bad_inputs_are_refused(env, db, world, direction):
    from revenueos_mcp_photo import render
    photo = load("revenueos_mcp_photo.server")
    out = call(photo.server, "photo_generate", world, {"direction_id": direction, "subject": "x", "width": 32, "height": 32})
    p = Path(out["path"])
    red = render.png(32, 32, b"".join(b"\x00" + b"\xff\x00\x00" * 32 for _ in range(32)))
    import hashlib
    other = p.with_name(hashlib.sha256(red).hexdigest() + ".png")
    other.write_bytes(red)
    aid = db.one("INSERT INTO photo_assets(direction_id, sha256, path, width, height, params) "
                 f"VALUES ('{direction}','{hashlib.sha256(red).hexdigest()}','{other}',32,32,'{{}}') RETURNING id")
    assert call(photo.server, "photo_verify", world, {"asset_id": aid})["verdict"] == "FAIL"
    other.write_bytes(b"tampered")
    assert "hash differs" in call(photo.server, "photo_verify", world, {"asset_id": aid})["reason"]
    with pytest.raises(ToolError, match="no such design direction"):
        call(photo.server, "photo_generate", world, {"direction_id": "00000000-0000-4000-8000-000000000000", "subject": "x"})
    with pytest.raises(ToolError):
        call(photo.server, "photo_generate", world, {"direction_id": direction, "subject": "x", "width": 99999})


def test_palette_parsing_and_decoding_edges():
    from revenueos_mcp_photo import render
    assert len(render.parse_palette([[0.5, 0.1, 10], [0.7, 0.1, 100]])) == 2
    for bad in ({"a": [0.5, 0.1, 10]}, {"a": "red", "b": [0.5, 0.1, 10]}):
        with pytest.raises(ValueError):
            render.parse_palette(bad)
    with pytest.raises(ValueError):
        render.decode(b"nope")
    assert render.oklch_to_srgb(1, 0, 0) == (255, 255, 255) and render.oklch_to_srgb(0, 0, 0) == (0, 0, 0)


# ---------------------------------------------------------------- scraper
def test_scraper_fetches_extracts_and_respects_robots(env, db, world, site, monkeypatch):
    monkeypatch.setenv("SCRAPER_ALLOW_HOSTS", "127.0.0.1")
    sc = load("revenueos_mcp_scraper.server")
    out = call(sc.server, "scrape_fetch", world, {"url": site + "/"})
    assert out["status"] == "ok" and out["via"] == "direct" and out["title"] == "Acme Cleaning"
    assert out["contacts"]["emails"] == ["hello@acme.example"] and out["contacts"]["phones"] == ["404-555-1212"]
    assert call(sc.server, "scrape_fetch", world, {"url": site + "/private"})["status"] == "robots_disallowed"
    assert call(sc.server, "scrape_extract", world, {"html": PAGE.decode(), "selector": "div.hours"})["matches"] == ["Mon-Fri 8-5"]
    assert receipts(db, "scrape_fetch") == 2 and receipts(db, "scrape_extract") == 1


def test_scraper_refuses_private_addresses_and_bad_selectors(env, db, world, site):
    sc = load("revenueos_mcp_scraper.server")
    with pytest.raises(ToolError, match="non-public"):
        call(sc.server, "scrape_fetch", world, {"url": site + "/"})
    with pytest.raises(ToolError, match="selector"):
        call(sc.server, "scrape_extract", world, {"html": "<p>x</p>", "selector": "a > b"})


def test_scraper_fallback_chain_reports_each_step(env, db, world, site, monkeypatch):
    monkeypatch.setenv("SCRAPER_ALLOW_HOSTS", "127.0.0.1")
    sc = load("revenueos_mcp_scraper.server")
    chain = call(sc.server, "scrape_fallbacks", world, {})["chain"]
    assert [c["name"] for c in chain] == ["agent-reach", "easyspider", "api-anything"] and not any(c["configured"] for c in chain)
    blocked = call(sc.server, "scrape_fetch", world, {"url": site + "/blocked"})
    assert blocked["status"] == "failed" and [t["status"] for t in blocked["tried"]] == [403, "not_configured", "not_configured", "not_configured"]
    monkeypatch.setenv("SCRAPER_FALLBACK_EASYSPIDER_URL", site + "/adapter")
    rescued = call(sc.server, "scrape_fetch", world, {"url": site + "/blocked"})
    assert rescued["status"] == "ok" and rescued["via"] == "easyspider" and rescued["title"] == "Rescued"
    monkeypatch.setenv("SCRAPER_FALLBACK_EASYSPIDER_URL", "http://127.0.0.1:1/none")
    assert call(sc.server, "scrape_fetch", world, {"url": site + "/blocked", "use_fallbacks": False})["status"] == "failed"
    broken = call(sc.server, "scrape_fetch", world, {"url": site + "/blocked"})
    assert any(str(t["status"]).startswith("error:") for t in broken["tried"])


def test_extract_edges():
    from revenueos_mcp_scraper import extract
    html = "<div id=a class='x y'><b>one</b><br><i>two</i></div><div class=x>three</div><script>no()</script>"
    assert extract.select(html, "#a") == ["one two"] and extract.select(html, ".x") == ["one two", "three"]
    assert extract.page(html)["text"] == "one two three"


def test_guard_blocks_metadata_and_unresolvable_hosts(env, monkeypatch):
    sc = load("revenueos_mcp_scraper.server")
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("169.254.169.254", 80))])
    with pytest.raises(PermissionError):
        sc.guard("http://metadata.example/")

    def boom(*a, **k):
        raise socket.gaierror("nope")
    monkeypatch.setattr(socket, "getaddrinfo", boom)
    with pytest.raises(ValueError, match="cannot resolve"):
        sc.guard("http://nope.example/")


# ---------------------------------------------------------------- outreach
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

    def starttls(self, context=None):
        pass

    def login(self, user, pw):
        assert pw == PW

    def send_message(self, msg):
        FakeSMTP.sent.append(msg)


DRAFT = {"to": "Lead@Corp.Example", "subject": "Cleaning for your offices", "sender_name": "Rukky, Express Cleaning Consult",
         "postal_address": "123 Peachtree Pkwy, Peachtree Corners, GA 30092",
         "body": "Hi, we clean offices across the metro area and would like to quote yours."}


@pytest.fixture
def out(env, monkeypatch):
    mod = load("revenueos_mcp_outreach.server")
    monkeypatch.setattr(mod.smtplib, "SMTP", FakeSMTP)
    FakeSMTP.sent = []
    return mod


def approve(db, world, tool, args):
    a = db.one(f"INSERT INTO approvals(task_id, tool_call_args_hash, requested_by, expires_at, tool) "
               f"VALUES ('{world['task']}','{args_hash(args)}','agent:exec',now()+interval '5 minutes','{tool}') RETURNING id")
    db.q(f"SELECT approval_decide('{a}','human:owner',true)")
    return a


def test_draft_is_compliant_and_send_needs_the_human_click(out, db, world, monkeypatch):
    monkeypatch.setenv("OUTREACH_SEND_DOMAINS", "internal.test")
    d = call(out.server, "outreach_draft", world, {**DRAFT, "to": "lead@internal.test"})
    assert d["status"] == "draft"
    body = db.one(f"SELECT replace(body, E'\\n', ' ') FROM outreach_messages WHERE id='{d['message_id']}'")
    assert "reply STOP" in body and "Peachtree Corners" in body
    args = {"message_id": d["message_id"]}
    with pytest.raises(ToolError):
        call(out.server, "outreach_send", world, args)
    assert FakeSMTP.sent == []
    sent = call(out.server, "outreach_send", world, args, approval=approve(db, world, "outreach_send", args))
    assert sent["status"] == "sent" and len(FakeSMTP.sent) == 1 and FakeSMTP.sent[0]["To"] == "lead@internal.test"
    assert receipts(db, "outreach_send") == 1 and receipts(db, "outreach_draft") == 1


def test_external_recipients_are_held_not_sent(out, db, world):
    d = call(out.server, "outreach_draft", world, DRAFT)
    args = {"message_id": d["message_id"]}
    res = call(out.server, "outreach_send", world, args, approval=approve(db, world, "outreach_send", args))
    assert res["status"] == "held" and FakeSMTP.sent == []


def test_suppression_dishonest_subjects_cap_and_ownership(out, db, world, monkeypatch):
    assert call(out.server, "outreach_suppress", world, {"address": "No@Corp.Example"})["suppressed"] == "no@corp.example"
    assert call(out.server, "outreach_draft", world, {**DRAFT, "to": "no@corp.example"})["status"] == "suppressed"
    for subject in ("RE: our call", "BUY NOW CHEAP CLEANING"):
        with pytest.raises(ToolError, match="not compliant"):
            call(out.server, "outreach_draft", world, {**DRAFT, "subject": subject})
    with pytest.raises(ToolError, match="not compliant"):
        call(out.server, "outreach_draft", world, {**DRAFT, "to": "not-an-email"})
    d = call(out.server, "outreach_draft", world, {**DRAFT, "to": "x@agents.revenueos.test"})
    args = {"message_id": d["message_id"]}
    with pytest.raises(ToolError, match="no such draft"):
        call(out.server, "outreach_send", world, args, approval=approve(db, world, "outreach_send", args), agent="ver")
    call(out.server, "outreach_suppress", world, {"address": "x@agents.revenueos.test"})
    assert call(out.server, "outreach_send", world, args, approval=approve(db, world, "outreach_send", args))["status"] == "suppressed"
    monkeypatch.setenv("OUTREACH_DAILY_CAP", "1")
    first = call(out.server, "outreach_draft", world, {**DRAFT, "to": "a@agents.revenueos.test"})["message_id"]
    a1 = {"message_id": first}
    assert call(out.server, "outreach_send", world, a1, approval=approve(db, world, "outreach_send", a1))["status"] == "sent"
    second = call(out.server, "outreach_draft", world, {**DRAFT, "to": "b@agents.revenueos.test"})["message_id"]
    a2 = {"message_id": second}
    with pytest.raises(ToolError, match="daily cap"):
        call(out.server, "outreach_send", world, a2, approval=approve(db, world, "outreach_send", a2))
    with pytest.raises(ToolError, match="not a draft"):
        call(out.server, "outreach_send", world, a1, approval=approve(db, world, "outreach_send", a1))


def test_send_without_vault_credentials_is_refused(out, db, world, tmp_path, monkeypatch):
    (tmp_path / "kc" / "exec-mail-password").unlink()
    d = call(out.server, "outreach_draft", world, {**DRAFT, "to": "z@agents.revenueos.test"})
    args = {"message_id": d["message_id"]}
    with pytest.raises(ToolError, match="vault"):
        call(out.server, "outreach_send", world, args, approval=approve(db, world, "outreach_send", args))
