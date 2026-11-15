"""Phase 2 acceptance against the live compose stack: sandbox + identity-pinned egress
(REVENUEOS_E2E=1 after `docker compose -f infra/compose.yaml --profile test up --wait`)."""
import hashlib
import json
import os
import subprocess
import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.environ.get("REVENUEOS_E2E") != "1", reason="needs the running compose stack")

ROOT = Path(__file__).resolve().parents[2]
SECRETS = ROOT / "infra" / "secrets"
AGENT = "7a1c2e30-0001-4000-8000-000000000001"
TASK = "7a1c2e30-0002-4000-8000-000000000001"
COMPOSE = ["docker", "compose", "-f", str(ROOT / "infra" / "compose.yaml"), "--profile", "test"]


def psql(sql: str) -> str:
    env = {**os.environ, "PGPASSFILE": str(SECRETS / "pgpass_host")}
    r = subprocess.run(["psql", "-h", "127.0.0.1", "-U", "revenueos_owner", "-d", "revenueos", "-X", "-A", "-t", "-c", sql],
                       capture_output=True, text=True, env=env, check=True)
    return r.stdout.strip()


def sandbox_run(body: dict) -> dict:
    """POST /v1/run on the supervisor from inside its own container (it has no host port)."""
    code = ("import json,sys,urllib.request as u;"
            "r=u.urlopen(u.Request('http://localhost:8300/v1/run',data=sys.stdin.buffer.read(),"
            "headers={'content-type':'application/json'}),timeout=120);print(r.read().decode())")
    r = subprocess.run([*COMPOSE, "exec", "-T", "sandbox-supervisor", "python", "-c", code],
                       input=json.dumps(body), capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


FETCH = ("import json,urllib.request as u,urllib.error as e\n"
         "try:\n"
         "  r=u.urlopen(u.Request('{url}', headers={{'x-revenueos-agent':'{spoof}'}}), timeout=20); print(r.status); print(r.read().decode())\n"
         "except e.HTTPError as x:\n"
         "  print(x.code); print(x.read().decode())\n")


def test_sandbox_supervisor_is_healthy_with_bubblewrap():
    r = subprocess.run([*COMPOSE, "exec", "-T", "sandbox-supervisor", "python", "-c",
                        "import urllib.request as u;print(u.urlopen('http://localhost:8300/health').read().decode())"],
                       capture_output=True, text=True, timeout=60)
    assert json.loads(r.stdout)["checks"]["bubblewrap"] == "ok"


def test_direct_egress_from_sandbox_is_blocked_and_logged():
    r = sandbox_run({"agent_id": AGENT, "task_id": TASK, "egress": True,
                     "argv": ["python3", "-c", "import socket; socket.create_connection(('1.1.1.1', 443), 5)"]})
    assert r["status"] == "failed" and "Network is unreachable" in r["stderr"]
    assert psql(f"SELECT status FROM sandbox_sessions WHERE command_hash='{r['command_hash']}' "
                f"ORDER BY started_at DESC LIMIT 1") == "failed"


def test_allowed_host_via_proxy_gets_secret_the_agent_never_sees():
    secret = (SECRETS / "keychain" / "upstream-echo-token").read_text().strip()
    other = str(uuid.uuid4())
    r = sandbox_run({"agent_id": AGENT, "task_id": TASK, "egress": True,
                     "argv": ["python3", "-c", FETCH.format(url="http://upstream-echo:8080/ok", spoof=other)]})
    assert r["status"] == "ok", r
    code, body = r["stdout"].split("\n", 1)
    assert code == "200", r
    echoed = json.loads(body)
    assert echoed["authorization_sha256"] == hashlib.sha256(f"Bearer {secret}".encode()).hexdigest()
    assert echoed["agent_header_leaked"] is False
    assert secret not in r["stdout"] and secret not in r["stderr"]
    row = psql("SELECT agent_id||'|'||task_id||'|'||decision||'|'||injected_secrets||'|'||(session_id IS NOT NULL) "
               "FROM egress_log WHERE host='upstream-echo:8080' ORDER BY created_at DESC LIMIT 1")
    assert row == f"{AGENT}|{TASK}|allow|1|true"   # the spoofed agent header was stripped and re-stamped


def test_disallowed_domain_via_proxy_is_blocked_and_logged():
    marker = uuid.uuid4().hex[:8]
    r = sandbox_run({"agent_id": AGENT, "task_id": TASK, "egress": True,
                     "argv": ["python3", "-c", FETCH.format(url=f"http://exfil-{marker}.example/steal", spoof="")]})
    assert r["stdout"].split("\n", 1)[0] == "403"
    row = psql(f"SELECT agent_id||'|'||task_id||'|'||decision||'|'||reason FROM egress_log "
               f"WHERE host LIKE 'exfil-{marker}%'")
    assert row.startswith(f"{AGENT}|{TASK}|deny|") and "not allowlisted" in row
    assert psql(f"SELECT count(*) FROM audit_log WHERE action='egress.deny' AND target LIKE 'exfil-{marker}%'") == "1"


def test_host_path_write_lands_only_in_the_shadow():
    r = sandbox_run({"agent_id": AGENT, "argv": ["sh", "-c", "echo pwned > /etc/evil; echo ok > note.txt; cat /etc/evil"]})
    assert r["status"] == "failed" and r["changes"] == {"note.txt": "added"}
    r2 = subprocess.run([*COMPOSE, "exec", "-T", "sandbox-supervisor", "ls", "/etc/evil"], capture_output=True, text=True)
    assert r2.returncode != 0


def test_destructive_command_is_blocked_in_yolo_and_audited():
    r = sandbox_run({"agent_id": AGENT, "yolo": True, "argv": ["sh", "-c", "rm -rf / --no-preserve-root"]})
    assert r["status"] == "blocked" and r["exit_code"] is None
    assert psql("SELECT count(*) > 0 FROM audit_log WHERE action='sandbox.blocked'") == "t"


# --------------------------------------------------------------------------- approvals (INV-06)
API = "http://127.0.0.1:3000"


def token(name: str) -> str:
    return (SECRETS / "keychain" / f"api-token-{name}").read_text().strip()


def api(method: str, path: str, who: str, body=None):
    import requests
    return requests.request(method, f"{API}{path}", json=body, timeout=15,
                            headers={"authorization": f"Bearer {token(who)}"})


def mcp_guarded(message: str, approval_id: str | None) -> dict:
    """Call the high-risk probe tool through mcp-common from inside the orchestrator container."""
    code = ("import json,sys;from revenueos_mcp_common.client import McpClient;"
            "a=json.loads(sys.argv[1]);t=open('/run/revenueos/keychain/mcp-echo-probe-token').read().strip();"
            "c=McpClient('http://echo-probe:8201',t)\n"
            "try:\n print(json.dumps({'ok':True,'result':c.call('probe_guarded',task_id=a['task'],agent_id=a['agent'],"
            "args={'message':a['message']},approval_id=a['approval'])}))\n"
            "except Exception as e:\n print(json.dumps({'ok':False,'error':str(e)}))")
    arg = json.dumps({"task": TASK, "agent": AGENT, "message": message, "approval": approval_id})
    r = subprocess.run([*COMPOSE, "exec", "-T", "orchestrator", "python", "-c", code, arg],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def request_approval(message: str) -> str:
    r = api("POST", "/v1/approvals", "probe-agent", {"task_id": TASK, "server": "echo-probe", "tool": "probe_guarded",
                                                      "args": {"message": message}, "risk_class": "high", "ttl_s": 600})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def last_reason(approval: str) -> str:
    return psql(f"SELECT payload->>'reason' FROM audit_log WHERE target='{approval}' "
                f"AND action LIKE 'approval.%rejected' ORDER BY seq DESC LIMIT 1")


def test_high_risk_call_without_approval_is_refused():
    out = mcp_guarded("no approval", None)
    assert not out["ok"] and "approval" in out["error"]


def test_approval_flow_single_use_and_rejections_are_logged():
    msg = f"send-{uuid.uuid4().hex[:6]}"
    a = request_approval(msg)
    # the requester cannot approve its own request; an approver can
    assert api("POST", f"/v1/approvals/{a}/decision", "probe-agent", {"approve": True}).status_code == 403
    d = api("POST", f"/v1/approvals/{a}/decision", "owner", {"approve": True})
    assert d.status_code == 200 and d.json()["status"] == "approved"
    # hash mismatch: different arguments are refused, approval stays usable
    assert not mcp_guarded(msg + "-tampered", a)["ok"]
    assert last_reason(a) == "args hash mismatch"
    # exact arguments: allowed once (the API's TS hash equals mcp-common's Python hash)
    first = mcp_guarded(msg, a)
    assert first["ok"], first
    # reuse is refused
    assert not mcp_guarded(msg, a)["ok"]
    assert last_reason(a) == "reuse: already used"
    assert psql(f"SELECT status FROM approvals WHERE id='{a}'") == "used"


def test_expired_approval_is_refused_and_logged():
    msg = f"late-{uuid.uuid4().hex[:6]}"
    a = request_approval(msg)
    assert api("POST", f"/v1/approvals/{a}/decision", "owner", {"approve": True}).status_code == 200
    psql(f"UPDATE approvals SET expires_at = now() - interval '1 second' WHERE id='{a}'")   # time passes
    assert not mcp_guarded(msg, a)["ok"]
    assert last_reason(a) == "expired"
    r = api("POST", f"/v1/approvals/{a}/consume", "probe-agent", {"args": {"message": msg}})
    assert r.status_code == 409 and r.json()["reason"] == "expired"


def test_approver_list_and_role_separation():
    assert api("GET", "/v1/approvals?status=pending", "owner").status_code == 200
    assert api("GET", "/v1/approvals", "probe-agent").status_code == 403
