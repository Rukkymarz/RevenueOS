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
