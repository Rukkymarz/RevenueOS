"""Phase 4 acceptance against the live stack (spec Acceptance 4): Forage finds, installs and uses
a server in one session and teaches the next; INV-10 blocks an unapproved server in production;
a hostile server is stopped and logged on all three counts; metrics and health probes work;
api-anything is registered experimental with a 14-day window."""
import hashlib
import json
import os
import secrets as s
import subprocess
import time
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


def http(service_url: str, method: str, path: str, body: dict | None = None, token: str | None = None,
         container: str = "orchestrator") -> tuple[int, dict]:
    code = ("import json,sys,urllib.request as u,urllib.error as e\n"
            "m,url,tok=sys.argv[1],sys.argv[2],sys.argv[3]\n"
            "data=sys.stdin.buffer.read() or None\n"
            "h={'content-type':'application/json'}\n"
            "h.update({'authorization':'Bearer '+tok} if tok else {})\n"
            "try:\n r=u.urlopen(u.Request(url,data=data,method=m,headers=h),timeout=580);print(r.status);print(r.read().decode())\n"
            "except e.HTTPError as x:\n print(x.code);print(x.read().decode())\n")
    r = subprocess.run([*COMPOSE, "exec", "-T", container, "python", "-c", code, method, service_url + path, token or ""],
                       input=json.dumps(body) if body is not None else "", capture_output=True, text=True, timeout=640)
    assert r.returncode == 0, r.stderr
    status, payload = r.stdout.split("\n", 1)
    return int(status), json.loads(payload)


def disco(method, path, body=None):
    return http("http://discovery:8104", method, path, body)


@pytest.fixture(scope="module")
def nava_token():
    tok = "nava_" + s.token_urlsafe(24)
    psql(f"INSERT INTO nava_tokens(digest, agent_id) VALUES ('{hashlib.sha256(tok.encode()).hexdigest()}', '{AGENT}') "
         "ON CONFLICT DO NOTHING")
    return tok


def syscall(token, tool, args, task=TASK):
    return http("http://runtime-os:8103", "POST", "/v1/syscalls", {"task_id": task, "tool": tool, "args": args}, token)


@pytest.fixture(scope="module")
def experimental_task():
    return psql("INSERT INTO tasks(objective, task_class, acceptance_criteria, environment) "
                "VALUES ('phase4 experimental','code','[{\"check\":\"tests_pass\"}]','experimental') RETURNING id").splitlines()[0]


def events(server, kind):
    return int(psql(f"SELECT count(*) FROM tool_events WHERE mcp_server_name = '{server}' AND kind = '{kind}'"))


def test_discovery_and_forage_are_up_with_agent_discover():
    status, out = disco("GET", "/health")
    assert status == 200 and out["status"] == "ok"


def test_gap_to_search_to_install_to_use_in_one_session_then_learned_for_the_next(nava_token, experimental_task):
    status, found = syscall(nava_token, "forage.search", {"query": "echo"})
    assert status == 200 and found["status"] == "committed", found
    names = {c["name"] for c in found["output"]["candidates"]}
    assert "io.revenueos.fixture/echo" in names
    status, inst = syscall(nava_token, "forage.install", {"spec": {"source": "registry", "name": "io.revenueos.fixture/echo",
                                                                   "local_name": "echo-fx"}})
    assert status == 200 and inst["output"]["status"] == "installed" and "echo" in inst["output"]["tools"], inst
    # usable in the same session: no restart, on an experimental task
    status, out = disco("POST", "/v1/call", {"server": "echo-fx", "tool": "echo", "arguments": {"message": "same-session"},
                                             "task_id": experimental_task})
    assert status == 200 and "same-session" in json.dumps(out["result"]), out
    # forage_learn: the instructions are in the rule file the next session reads
    status, learned = syscall(nava_token, "forage.learn", {"server": "echo-fx"})
    assert status == 200 and learned["output"]["rule_file"] == "rules/AGENTS.md", learned
    status, read = syscall(nava_token, "fs.read", {"workspace": "rules", "path": "AGENTS.md"})
    assert status == 200 and "forage:echo-fx" in json.dumps(read["output"]) and "mcp.call" in json.dumps(read["output"])


def test_inv10_blocks_unapproved_activation_in_production_then_approval_unblocks(nava_token, experimental_task):
    status, out = syscall(nava_token, "mcp.call", {"server": "echo-fx", "tool": "echo", "arguments": {"message": "x"}})
    assert status in (403, 409, 422) and out["status"] in ("denied", "blocked"), out
    assert events("echo-fx", "call_blocked") >= 1
    status, out = disco("POST", "/v1/servers/echo-fx/activate", {"task_id": TASK})
    assert status == 403 and events("echo-fx", "activation_blocked") >= 1
    assert psql("SELECT count(*) FROM audit_log WHERE action = 'tool.activate' AND created_at > now() - interval '10 minutes'") != "0" \
        or psql("SELECT count(*) FROM audit_log WHERE action LIKE 'tool.%' AND target = 'echo-fx'") != "0"
    assert disco("POST", "/v1/servers/echo-fx/approve", {"approved_by": "agent:executor"})[0] == 403
    status, out = disco("POST", "/v1/servers/echo-fx/approve", {"approved_by": "human:christine"})
    assert status == 200 and out["status"] == "approved"
    assert disco("POST", "/v1/servers/echo-fx/activate", {"task_id": TASK})[0] == 200


def test_hostile_server_is_blocked_on_network_secrets_and_sandbox_escape_and_logged():
    spec = {"source": "manual", "name": "hostile", "transport": "stdio", "command": "python3",
            "args": ["/src/infra/discovery/test-servers/malicious_server.py"], "version": "0.0.1", "license": "MIT",
            "checksum": "sha256:" + "d" * 64, "last_push": time.strftime("%Y-%m-%d"), "repo": "test/hostile"}
    status, inst = disco("POST", "/v1/forage/install", {"spec": spec})
    assert status == 200 and inst["status"] == "installed", inst
    task = psql("INSERT INTO tasks(objective, task_class, acceptance_criteria, environment) "
                "VALUES ('hostile','code','[{\"check\":\"tests_pass\"}]','experimental') RETURNING id").splitlines()[0]
    status, out = disco("POST", "/v1/call", {"server": "hostile", "tool": "attack", "arguments": {}, "task_id": task})
    assert status == 200, out
    res = out["result"]
    assert "CONNECTED" not in json.dumps(res["egress"]) and "READ" not in json.dumps(res["secrets"])
    assert "WROTE" not in json.dumps(res["writes"]) and res["env_leaks"] == []
    deadline = time.time() + 60
    while time.time() < deadline and not events("hostile", "quarantined"):
        time.sleep(2)
    for kind in ("egress_blocked", "secret_read_blocked", "sandbox_write_blocked"):
        assert events("hostile", kind) >= 1, kind
    assert psql("SELECT health_status FROM tool_installations WHERE mcp_server_name = 'hostile'") == "QUARANTINED"
    assert psql("SELECT active FROM tool_installations WHERE mcp_server_name = 'hostile'") == "f"


def test_per_tool_metrics_appear_and_a_failed_probe_removes_the_server_from_the_active_set(experimental_task):
    status, out = disco("GET", "/v1/servers/echo-fx/metrics")
    assert status == 200 and any(m.get("tool_name") == "echo" and m.get("call_count", 0) >= 1 for m in out["metrics"]), out
    spec = {"source": "manual", "name": "flaky", "transport": "stdio", "command": "python3",
            "args": ["/src/infra/discovery/test-servers/flaky_server.py"], "version": "0.0.1", "license": "MIT",
            "checksum": "sha256:" + "e" * 64, "last_push": time.strftime("%Y-%m-%d"), "repo": "test/flaky"}
    assert disco("POST", "/v1/forage/install", {"spec": spec})[1]["status"] == "installed"
    assert disco("POST", "/v1/servers/flaky/probe")[1]["healthy"] is True
    disco("POST", "/v1/call", {"server": "flaky", "tool": "break_server", "arguments": {}, "task_id": experimental_task})
    for _ in range(10):
        out = disco("POST", "/v1/servers/flaky/probe")[1]
        if not out["healthy"]:
            break
        time.sleep(2)
    assert out["healthy"] is False
    assert psql("SELECT active||'|'||health_status FROM tool_installations WHERE mcp_server_name = 'flaky'") == "false|UNHEALTHY"
    assert events("flaky", "health_failed") >= 1


def test_api_anything_is_registered_experimental_with_a_14_day_window():
    row = psql("SELECT status||'|'||(observe_until > now() + interval '13 days')::text||'|'||(approved_by IS NULL)::text "
               "FROM tool_installations WHERE mcp_server_name = 'api-anything'")
    assert row == "experimental|true|true", row
    status, out = disco("POST", "/v1/servers/api-anything/approve", {"approved_by": "human:christine"})
    assert status == 409 and "observation" in json.dumps(out)
    assert psql("SELECT status FROM tool_installations WHERE mcp_server_name = 'mcpfinder'") == "approved"
