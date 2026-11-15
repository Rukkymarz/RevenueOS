"""Phase 3 acceptance against the live stack: OmniPilot's 41 tools by remote control
(orchestrator -> runtime REST -> tool -> receipt -> span), shared risk classification."""
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
W = "/workspace/e2e"

# One call per tool, in an order where each call's preconditions exist (files, a process to kill).
CALLS = [
    ("fs.make_directory", {"path": W}),
    ("fs.write_file", {"path": f"{W}/a.txt", "content": "hello runtime"}),
    ("fs.read_file", {"path": f"{W}/a.txt"}),
    ("fs.edit_file", {"path": f"{W}/a.txt", "find_text": "hello", "replace_text": "hi"}),
    ("fs.copy_file", {"source": f"{W}/a.txt", "destination": f"{W}/b.txt"}),
    ("fs.move_file", {"source": f"{W}/b.txt", "destination": f"{W}/c.txt"}),
    ("fs.list_directory", {"path": W}),
    ("fs.search_files", {"pattern": "*.txt", "directory": W}),
    ("fs.grep", {"pattern": "runtime", "directory": W}),
    ("fs.delete_file", {"path": f"{W}/c.txt"}),
    ("shell.run_command", {"command": "echo shell-ok && sleep 300 &", "background": True}),
    ("python.run_python", {"code": "x = 6 * 7"}),
    ("processes.list_processes", {"filter": "sleep"}),
    ("processes.kill_process", {"name": "sleep"}),
    ("system.get_system_info", {}),
    ("system.get_environment_variable", {"name": "HOME"}),
    ("system.list_drives", {}),
    ("screen.get_screen_size", {}),
    ("screen.screenshot", {"attach": False}),
    ("screen.locate_image", {"image_path": f"{W}/needle.png"}),
    ("apps.list_applications", {}),
    ("apps.open_application", {"name": "xterm"}),
    ("gui.move_mouse", {"x": 200, "y": 200}),
    ("gui.click", {"x": 200, "y": 200}),
    ("gui.double_click", {"x": 210, "y": 210}),
    ("gui.right_click", {"x": 220, "y": 220}),
    ("gui.drag", {"x1": 100, "y1": 100, "x2": 300, "y2": 300}),
    ("gui.scroll", {"amount": -3}),
    ("gui.type_text", {"text": "echo typed"}),
    ("gui.press_key", {"key": "enter"}),
    ("gui.hotkey", {"keys": ["ctrl", "l"]}),
    ("clipboard.set_clipboard", {"text": "revenueos-clip"}),
    ("clipboard.get_clipboard", {}),
    ("notify.send_notification", {"message": "runtime test", "title": "RevenueOS"}),
    ("apps.open_file", {"path": f"{W}/a.txt"}),
    ("apps.close_application", {"name": "xterm"}),
    ("browser.open_url", {"url": "http://upstream-echo:8080/ok"}),
    ("web.fetch_url", {"url": "http://upstream-echo:8080/ok"}),
    ("web.http_request", {"url": "http://upstream-echo:8080/ok", "method": "GET"}),
    ("web.download_file", {"url": "http://upstream-echo:8080/ok", "destination": f"{W}/dl.json"}),
    ("web.search_web", {"query": "revenueos"}),
]
MUST_SUCCEED = {"fs.make_directory", "fs.write_file", "fs.read_file", "fs.edit_file", "fs.copy_file", "fs.move_file",
                "fs.list_directory", "fs.search_files", "fs.grep", "fs.delete_file", "shell.run_command",
                "python.run_python", "processes.list_processes", "system.get_system_info", "screen.get_screen_size",
                "screen.screenshot", "gui.move_mouse", "gui.click", "gui.type_text", "clipboard.set_clipboard",
                "clipboard.get_clipboard", "web.fetch_url", "web.http_request", "web.download_file"}


def psql(sql: str) -> str:
    env = {**os.environ, "PGPASSFILE": str(SECRETS / "pgpass_host")}
    r = subprocess.run(["psql", "-h", "127.0.0.1", "-U", "revenueos_owner", "-d", "revenueos", "-X", "-A", "-t", "-c", sql],
                       capture_output=True, text=True, env=env, check=True)
    return r.stdout.strip()


def remote(tool: str, args: dict, mode: str = "auto") -> tuple[int, dict]:
    """POST /v1/runtime/tools/{tool} on the orchestrator, from inside its container."""
    code = ("import json,sys,urllib.request as u,urllib.error as e\n"
            "b=sys.stdin.buffer.read();t=sys.argv[1]\n"
            "try:\n r=u.urlopen(u.Request(f'http://localhost:8101/v1/runtime/tools/{t}',data=b,"
            "headers={'content-type':'application/json'}),timeout=200);print(r.status);print(r.read().decode())\n"
            "except e.HTTPError as x:\n print(x.code);print(x.read().decode())\n")
    body = json.dumps({"task_id": TASK, "agent_id": AGENT, "args": args, "mode": mode})
    r = subprocess.run([*COMPOSE, "exec", "-T", "orchestrator", "python", "-c", code, tool], input=body,
                       capture_output=True, text=True, timeout=240)
    assert r.returncode == 0, r.stderr
    status, payload = r.stdout.split("\n", 1)
    return int(status), json.loads(payload)


def test_runtime_lists_omnipilots_41_tools():
    code = ("import json,urllib.request as u;t=open('/run/revenueos/keychain/runtime-omni-token').read().strip();"
            "print(u.urlopen('http://runtime-omni:8102/v1/tools').read().decode())")
    r = subprocess.run([*COMPOSE, "exec", "-T", "orchestrator", "python", "-c", code], capture_output=True, text=True)
    tools = json.loads(r.stdout)
    assert tools["count"] == 41 and {t["name"] for t in tools["tools"]} == {c[0] for c in CALLS}


def test_all_41_tools_emit_receipts_through_remote_control():
    psql(f"INSERT INTO egress_rules(agent_id, host, created_by) VALUES ('{AGENT}', 'upstream-echo:8080', 'e2e') "
         "ON CONFLICT DO NOTHING")
    results = {}
    for tool, args in CALLS:
        status, out = remote(tool, args)
        assert status == 200, (tool, status, out)
        results[tool] = out
        row = psql(f"SELECT verdict||'|'||coalesce(trace_id,'') FROM tool_calls WHERE id='{out['receipt_id']}' "
                   f"AND mcp_server='runtime-omni' AND tool='{tool}'")
        assert row, f"no receipt for {tool}"
        assert row.split("|")[1] == out["trace_id"], f"{tool}: receipt not on the orchestrator's trace"
    failed = sorted(t for t in MUST_SUCCEED if results[t]["status"] != "ok")
    assert not failed, {t: results[t]["output"][:300] for t in failed}
    assert "hi runtime" in results["fs.read_file"]["output"] or results["fs.edit_file"]["status"] == "ok"
    assert results["clipboard.get_clipboard"]["output"].strip().endswith("revenueos-clip")
    # web tools reached the upstream only through the identity-pinned proxy
    assert psql(f"SELECT count(*) > 0 FROM egress_log WHERE agent_id='{AGENT}' AND task_id='{TASK}' "
                f"AND host='upstream-echo:8080' AND decision='allow' AND session_id IS NOT NULL") == "t"


@pytest.mark.parametrize("mode", ["ask", "auto", "yolo"])
def test_rm_rf_root_is_blocked_through_remote_control_and_audited(mode):
    marker = uuid.uuid4().hex[:8]
    status, out = remote("shell.run_command", {"command": f"rm -rf / # {marker}"}, mode=mode)
    assert status == 403 and out["status"] == "blocked" and out["risk_class"] == "critical"
    assert psql(f"SELECT count(*) FROM audit_log WHERE action='tool.denied' AND target='runtime-omni/shell.run_command' "
                f"AND payload->>'reason' LIKE 'critical:%' AND created_at > now() - interval '2 minutes'") != "0"


def test_runtime_has_no_direct_route_out():
    status, out = remote("python.run_python", {"code": "import socket\ntry:\n socket.create_connection(('1.1.1.1', 443), 5)\n "
                                                       "print('CONNECTED')\nexcept OSError as e:\n print('BLOCKED', e)"})
    assert status == 200 and "BLOCKED" in out["output"] and "CONNECTED" not in out["output"]


# ---------------------------------------------------------------------------------------------
# NAVA (runtime-os): the 12-step managed syscall against the live stack (docs/NAVA.md).
# ---------------------------------------------------------------------------------------------
def nava_http(method: str, path: str, body: dict | None, token: str) -> tuple[int, dict]:
    code = ("import json,sys,urllib.request as u,urllib.error as e\n"
            "m,p,tok=sys.argv[1],sys.argv[2],sys.argv[3]\n"
            "data=sys.stdin.buffer.read() or None\n"
            "req=u.Request(f'http://runtime-os:8103{p}',data=data,method=m,"
            "headers={'content-type':'application/json','authorization':f'Bearer {tok}'})\n"
            "try:\n r=u.urlopen(req,timeout=580);print(r.status);print(r.read().decode())\n"
            "except e.HTTPError as x:\n print(x.code);print(x.read().decode())\n")
    r = subprocess.run([*COMPOSE, "exec", "-T", "orchestrator", "python", "-c", code, method, path, token],
                       input=json.dumps(body) if body is not None else "", capture_output=True, text=True, timeout=640)
    assert r.returncode == 0, r.stderr
    status, payload = r.stdout.split("\n", 1)
    return int(status), json.loads(payload)


@pytest.fixture(scope="module")
def nava_token():
    import hashlib
    import secrets as s
    tok = "nava_" + s.token_urlsafe(24)
    psql(f"INSERT INTO nava_tokens(digest, agent_id) VALUES ('{hashlib.sha256(tok.encode()).hexdigest()}', '{AGENT}') "
         "ON CONFLICT DO NOTHING")
    return tok


def test_nava_syscall_commits_with_receipt_and_12_steps(nava_token):
    status, out = nava_http("POST", "/v1/syscalls", {
        "task_id": TASK, "tool": "fs.write", "args": {"workspace": "e2e", "path": "nava.txt", "content": "governed"},
        "expect": [{"file_exists": "nava.txt"}, {"file_contains": ["nava.txt", "governed"]}]}, nava_token)
    assert status == 200 and out["status"] == "committed", out
    assert psql(f"SELECT count(*) FROM tool_calls WHERE id='{out['receipt_id']}' AND mcp_server='runtime-os'") == "1"
    assert psql(f"SELECT count(*) FROM syscall_steps WHERE syscall_id='{out['id']}'") == "12"


def test_nava_unauthenticated_and_foreign_tokens_fail_closed(nava_token):
    status, _ = nava_http("POST", "/v1/syscalls", {"task_id": TASK, "tool": "fs.list", "args": {"workspace": "e2e"}},
                          "nava_forged")
    assert status == 401


def test_nava_runaway_process_is_killed_and_reported(nava_token):
    """Acceptance 3.3: a runaway command dies at its wall-clock quota; the syscall rolls back and
    says why."""
    status, out = nava_http("POST", "/v1/syscalls", {
        "task_id": TASK, "tool": "sandbox.run", "timeout_s": 3,
        "args": {"workspace": "e2e", "argv": ["sh", "-c", "while true; do :; done"], "timeout_s": 3}}, nava_token)
    assert status in (409, 422), out
    assert out["status"] in ("rolled_back", "failed")
    assert "quota" in (out["reason"] or "") or "timeout" in (out["reason"] or ""), out
    assert psql(f"SELECT count(*) FROM syscalls WHERE id='{out['id']}' AND status IN ('rolled_back','failed') "
                "AND reason IS NOT NULL") == "1"


def test_nava_failed_mutation_rolls_back_transactionally(nava_token):
    """Acceptance 3.4: a command that mutates then fails leaves the workspace exactly as before."""
    status, _ = nava_http("POST", "/v1/syscalls", {
        "task_id": TASK, "tool": "fs.write", "args": {"workspace": "e2e", "path": "state.txt", "content": "before"}},
        nava_token)
    assert status == 200
    status, out = nava_http("POST", "/v1/syscalls", {
        "task_id": TASK, "tool": "sandbox.run",
        "args": {"workspace": "e2e", "argv": ["sh", "-c", "echo damaged > state.txt; touch junk; exit 1"]}}, nava_token)
    assert status == 409 and out["status"] == "rolled_back" and out["restored_hash"] == out["snapshot_hash"], out
    _, read = nava_http("POST", "/v1/syscalls", {
        "task_id": TASK, "tool": "fs.read", "args": {"workspace": "e2e", "path": "state.txt"}}, nava_token)
    assert read["output"]["content"] == "before"
    _, listing = nava_http("POST", "/v1/syscalls", {
        "task_id": TASK, "tool": "fs.list", "args": {"workspace": "e2e"}}, nava_token)
    assert "junk" not in listing["output"]["files"]


def test_nava_rm_rf_is_critical_in_every_mode(nava_token):
    for mode in ("ask", "auto", "yolo"):
        status, out = nava_http("POST", "/v1/syscalls", {
            "task_id": TASK, "tool": "sandbox.run", "mode": mode,
            "args": {"workspace": "e2e", "argv": ["rm", "-rf", "/"]}}, nava_token)
        assert status == 403 and out["risk_class"] == "critical", (mode, out)


def test_nava_a2a_bus_and_memory(nava_token):
    status, out = nava_http("POST", "/v1/bus/send", {"to": AGENT, "channel": "e2e", "body": {"ping": 1},
                                                     "task_id": TASK}, nava_token)
    assert status == 200 and out["seq"] >= 1
    status, inbox = nava_http("GET", "/v1/bus/inbox?after=0", None, nava_token)
    assert status == 200 and any(m["channel"] == "e2e" for m in inbox["messages"])
    status, mem = nava_http("POST", "/v1/memory", {"tier": "episodic", "key": "e2e", "value": {"ok": True}}, nava_token)
    assert status == 200 and mem["id"]


# ---------------------------------------------------------------------------------------------
# OpenMuse (spec 3.5): takeover console, unattended signup->PDF->nib->reviewed-draft pipeline.
# ---------------------------------------------------------------------------------------------
def omni_http(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    code = ("import json,sys,urllib.request as u,urllib.error as e\n"
            "tok=open('/run/revenueos/keychain/runtime-omni-token').read().strip()\n"
            "m,p=sys.argv[1],sys.argv[2]\n"
            "data=sys.stdin.buffer.read() or None\n"
            "req=u.Request(f'http://runtime-omni:8102{p}',data=data,method=m,"
            "headers={'content-type':'application/json','authorization':f'Bearer {tok}'})\n"
            "try:\n r=u.urlopen(req,timeout=600);print(r.status);print(r.read().decode())\n"
            "except e.HTTPError as x:\n print(x.code);print(x.read().decode())\n")
    r = subprocess.run([*COMPOSE, "exec", "-T", "orchestrator", "python", "-c", code, method, path],
                       input=json.dumps(body) if body is not None else "", capture_output=True, text=True, timeout=640)
    assert r.returncode == 0, r.stderr
    status, payload = r.stdout.split("\n", 1)
    return int(status), json.loads(payload)


def test_human_takeover_attaches_types_and_agent_resumes():
    """Acceptance 3.5: console attaches to the live desktop, the human types, the agent resumes."""
    # the VNC console is really listening on the desktop's loopback (RFB banner)
    probe = ("import socket;s=socket.create_connection(('127.0.0.1',5900),5);"
             "print(s.recv(12).decode());s.close()")
    r = subprocess.run([*COMPOSE, "exec", "-T", "runtime-omni", "python", "-c", probe],
                       capture_output=True, text=True, timeout=60)
    assert r.stdout.startswith("RFB "), (r.stdout, r.stderr)
    # and the noVNC web console (pinned, docs/PINS.md) serves its client on the same loopback
    web = ("import urllib.request as u;"
           "print(u.urlopen('http://127.0.0.1:6080/vnc.html',timeout=10).status)")
    r = subprocess.run([*COMPOSE, "exec", "-T", "runtime-omni", "python", "-c", web],
                       capture_output=True, text=True, timeout=60)
    assert r.stdout.strip() == "200", (r.stdout, r.stderr)

    # the agent works, a window is focused for the human to type into
    status, _ = remote("apps.open_application", {"name": "xterm"})
    assert status == 200
    status, out = omni_http("POST", "/v1/takeover/attach", {"holder": "christine"})
    assert status == 200 and out["active"] and out["vnc"]["port"] == 5900

    # while the human holds the desk, every agent tool call is paused with 423
    status, out = remote("fs.list_directory", {"path": W})
    assert status == 423 and out["status"] == "paused", out

    # the human types a real command into the focused xterm
    status, _ = omni_http("POST", "/v1/takeover/type",
                          {"holder": "christine", "text": f"echo takeover-was-here > {W}/takeover.txt"})
    assert status == 200
    status, _ = omni_http("POST", "/v1/takeover/key", {"holder": "christine", "key": "Return"})
    assert status == 200

    # release: the agent resumes and can read what the human did
    status, out = omni_http("POST", "/v1/takeover/release", {"holder": "christine"})
    assert status == 200 and not out["active"]
    import time as _t
    deadline = _t.time() + 15
    content = ""
    while _t.time() < deadline and "takeover-was-here" not in content:
        status, out = remote("fs.read_file", {"path": f"{W}/takeover.txt"})
        content = out.get("output", "") if status == 200 else ""
        _t.sleep(1)
    assert "takeover-was-here" in content, content
    assert psql("SELECT count(*) FROM audit_log WHERE action LIKE 'takeover.%'") != "0"


@pytest.fixture(scope="module")
def pipeline_agent():
    """A fresh Phase 2 identity allowed to reach the signup service through the pinned proxy."""
    name = f"muse-{uuid.uuid4().hex[:6]}"
    r = subprocess.run([*COMPOSE, "exec", "-T", "identity", "revenueos-identity", "provision",
                        "--name", name, "--role", "browser", "--allow", "signup-test:8090"],
                       capture_output=True, text=True, timeout=300)
    assert r.stdout.strip(), r.stderr
    return json.loads(r.stdout)


def test_openmuse_pipeline_signup_to_reviewed_draft_unattended(pipeline_agent):
    """Acceptance 3.1: browser signup with the Phase 2 identity, OTP from its own inbox, PDF
    download, nib fill, deterministic review, reply draft — one call, no human."""
    agent = pipeline_agent["agent_id"]
    task = psql("INSERT INTO tasks(objective, task_class, acceptance_criteria) VALUES "
                "('openmuse signup pipeline', 'identity.signup', '[{\"check\":\"pipeline\"}]') RETURNING id").splitlines()[0]
    status, out = omni_http("POST", "/v1/openmuse/pipeline/signup", {"task_id": task, "agent_id": agent})
    assert status == 200, out
    assert out["status"] == "completed" and out["review"]["verdict"] == "PASS", out
    stages = [s["stage"] for s in out["stages"]]
    assert stages == ["browser.open", "signup.submitted", "otp.extracted", "signup.verified",
                      "form.downloaded", "form.filled", "review", "reply.drafted"], stages
    assert out["draft_uid"]
    # the signup service really verified this address
    email = pipeline_agent["identities"]["email"]["address"]
    chk = ("import json,urllib.request as u;"
           f"print(u.urlopen('http://signup-test:8090/status?email={email}').read().decode())")
    r = subprocess.run([*COMPOSE, "exec", "-T", "identity", "python", "-c", chk],
                       capture_output=True, text=True, timeout=60)
    assert json.loads(r.stdout)["verified"] is True
    # receipted like everything else
    assert psql(f"SELECT count(*) FROM tool_calls WHERE id='{out['receipt_id']}' "
                "AND tool='openmuse.pipeline.signup'") == "1"
    # and the browser traffic went through the identity-pinned proxy
    assert psql(f"SELECT count(*) > 0 FROM egress_log WHERE agent_id='{agent}' AND host='signup-test:8090' "
                "AND decision='allow'") == "t"


def test_aegis_large_repo_clone_inside_sandbox(nava_token):
    """Acceptance 3.4 (Aegis): a large git clone completes inside the sandbox, over the
    identity-pinned MITM'd HTTPS proxy, without host exposure."""
    psql(f"INSERT INTO egress_rules(agent_id, host, created_by) VALUES ('{AGENT}', 'github.com:443', 'e2e'), "
         f"('{AGENT}', 'codeload.github.com:443', 'e2e') ON CONFLICT DO NOTHING")
    status, out = nava_http("POST", "/v1/syscalls", {
        "task_id": TASK, "tool": "sandbox.run", "timeout_s": 300,
        "args": {"workspace": "aegis", "timeout_s": 300,
                 "argv": ["git", "clone", "--depth", "1", "https://github.com/python/cpython", "clone"]},
        "expect": [{"exit_code": 0}, {"file_exists": "clone/README.rst"}]}, nava_token)
    assert status == 200 and out["status"] == "committed", out
    _, listing = nava_http("POST", "/v1/syscalls", {
        "task_id": TASK, "tool": "sandbox.run",
        "args": {"workspace": "aegis", "argv": ["sh", "-c", "du -sm clone | cut -f1"]}}, nava_token)
    assert int(listing["output"]["stdout"].strip() or 0) >= 50      # a genuinely large tree
    assert psql(f"SELECT count(*) > 0 FROM egress_log WHERE agent_id='{AGENT}' AND "
                "host IN ('github.com:443','codeload.github.com:443') AND decision='allow'") == "t"
