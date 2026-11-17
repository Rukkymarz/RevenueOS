"""Phase 6 acceptance against the live stack (spec Acceptance 6): every C14 tool, called through an MCP
client, leaves a tool_calls receipt; the photo is locked to the design direction and verifies; the
scraper fetches and extracts a page; outreach drafts are compliant and the send needs the human click
(and an external recipient is held)."""
import json
import os
import subprocess

import pytest

from test_phase4_stack import AGENT, COMPOSE, TASK, psql

pytestmark = pytest.mark.skipif(os.environ.get("REVENUEOS_E2E") != "1", reason="needs the running compose stack")

CODE = ("import json,sys;from revenueos_mcp_common.client import McpClient;from revenueos_common.canonical import args_hash\n"
        "svc,port,tool,args,appr=sys.argv[1:6]\n"
        "t=open(f'/run/revenueos/keychain/mcp-{svc}-token').read().strip()\n"
        "c=McpClient(f'http://{svc}:{port}',t);a=json.loads(args)\n"
        "if tool=='hash':\n print(json.dumps({'hash':args_hash(a)}));sys.exit(0)\n"
        "try:\n r=c.call(tool,task_id=sys.argv[6],agent_id=sys.argv[7],args=a,approval_id=appr or None);print(json.dumps({'ok':r}))\n"
        "except Exception as e:\n print(json.dumps({'error':str(e)}))\n")


def mcp(svc, port, tool, args, approval="", agent=AGENT, task=TASK):
    r = subprocess.run([*COMPOSE, "exec", "-T", "orchestrator", "python", "-c", CODE, svc, str(port), tool, json.dumps(args), approval, task, agent],
                       capture_output=True, text=True, timeout=240)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def receipts(tool):
    return int(psql(f"SELECT count(*) FROM tool_calls WHERE tool='{tool}' AND verdict='ok'"))


@pytest.fixture(scope="module")
def direction():
    premise = psql("INSERT INTO research_runs(target, pack) VALUES ('c14','local-services') RETURNING id").splitlines()[0]
    bundle = psql("INSERT INTO premise_bundles(research_run_id, claims, missing_data) VALUES "
                  f"('{premise}', '[{{\"text\":\"x\",\"label\":\"verified\",\"source_ids\":[\"s1\"]}}]', '[]') RETURNING id").splitlines()[0]
    pid = psql(f"INSERT INTO projects(name, business_line, premise_bundle_id) VALUES ('c14-site','cleaning','{bundle}') RETURNING id").splitlines()[0]
    return psql("INSERT INTO design_directions(project_id, direction, rationale, palette_oklch, fonts, radius_scale, knowledge_query) "
                f"VALUES ('{pid}','calm-clinical','{'x' * 50}','{{\"ink\":[0.3,0.04,250],\"sky\":[0.85,0.06,220],\"sun\":[0.8,0.14,85]}}','{{}}','{{}}','{{}}') RETURNING id").splitlines()[0]


def test_photo_generator_is_style_locked_and_receipted(direction):
    before = receipts("photo_generate")
    out = mcp("photo-generator", 8203, "photo_generate", {"direction_id": direction, "subject": "bright office", "width": 160, "height": 90})
    assert "ok" in out, out
    asset = out["ok"]["result"]["asset_id"]
    assert set(out["ok"]["result"]["palette"]) == {"ink", "sky", "sun"}
    ver = mcp("photo-generator", 8203, "photo_verify", {"asset_id": asset})
    assert ver["ok"]["result"]["verdict"] == "PASS", ver
    assert receipts("photo_generate") == before + 1 and receipts("photo_verify") >= 1


def test_scraper_fetches_and_extracts_and_is_receipted():
    out = mcp("scraper", 8204, "scrape_fetch", {"url": "http://discovery-fixture:8085/site/acme"})
    res = out["ok"]["result"]
    assert res["status"] == "ok" and res["title"] == "Acme Offices" and res["contacts"]["emails"] == ["hello@acme.example"], out
    ex = mcp("scraper", 8204, "scrape_extract", {"html": "<div class=a>hi</div>", "selector": "div.a"})
    assert ex["ok"]["result"]["matches"] == ["hi"]
    assert mcp("scraper", 8204, "scrape_fallbacks", {})["ok"]["result"]["chain"][0]["name"] == "agent-reach"
    assert receipts("scrape_fetch") >= 1 and receipts("scrape_extract") >= 1 and receipts("scrape_fallbacks") >= 1


def test_outreach_draft_then_human_click_then_external_is_held():
    draft = {"to": "prospect@external-corp.example", "subject": "Cleaning for your offices", "sender_name": "Rukky, Express Cleaning Consult",
             "postal_address": "123 Peachtree Pkwy, Peachtree Corners, GA 30092",
             "body": "Hi, we clean offices across the metro area and would like to quote yours."}
    d = mcp("outreach", 8205, "outreach_draft", draft)["ok"]["result"]
    assert d["status"] == "draft"
    args = {"message_id": d["message_id"]}
    refused = mcp("outreach", 8205, "outreach_send", args)
    assert "error" in refused and "approval" in refused["error"].lower(), refused
    h = subprocess.run([*COMPOSE, "exec", "-T", "orchestrator", "python", "-c", CODE, "outreach", "8205", "hash", json.dumps(args), "", TASK, AGENT],
                       capture_output=True, text=True, timeout=120)
    digest = json.loads(h.stdout.strip().splitlines()[-1])["hash"]
    appr = psql("INSERT INTO approvals(task_id, tool_call_args_hash, requested_by, expires_at, tool) "
                f"VALUES ('{TASK}','{digest}','agent:probe',now()+interval '5 minutes','outreach_send') RETURNING id").splitlines()[0]
    psql(f"SELECT approval_decide('{appr}','human:owner',true)")
    sent = mcp("outreach", 8205, "outreach_send", args, approval=appr)
    assert sent["ok"]["result"]["status"] == "held", sent      # external send is not enabled
    assert psql(f"SELECT status FROM outreach_messages WHERE id='{d['message_id']}'") == "held"
    assert receipts("outreach_draft") >= 1 and receipts("outreach_send") >= 1
