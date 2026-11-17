"""The agent-discover REST client against a small stand-in that enforces the daemon's own
rules (docs/API.md of the pinned commit): a per-launch token on every mutating request, JSON
bodies, and a new token after a restart."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from revenueos_discovery.agent_discover import AgentDiscover, AgentDiscoverError

STATE = {"token": "t1", "servers": {}, "next": 1, "log": []}


class Daemon(BaseHTTPRequestHandler):
    def _send(self, body, status=200):
        data = json.dumps(body).encode() if body is not None else b""
        self.send_response(status)
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        p = self.path.split("?")[0]
        if p == "/api/health":
            return self._send({"status": "ok"})
        if p == "/api/token":
            return self._send({"token": STATE["token"], "header": "x-agent-discover-token"})
        if p == "/api/servers":
            return self._send(list(STATE["servers"].values()))
        if p == "/api/install/plan":
            return self._send({"server": "x", "query": self.path.split("?")[1]})
        if p == "/api/browse":
            return self._send({"servers": []})
        if p.endswith("/metrics"):
            return self._send([{"tool_name": "echo", "call_count": 2}])
        sid = int(p.rsplit("/", 1)[1])
        return self._send({**STATE["servers"][sid], "tools": [{"name": "echo"}]}) if sid in STATE["servers"] \
            else self._send({"error": "Server not found"}, 404)

    def _mutate(self):
        if self.headers.get("x-agent-discover-token") != STATE["token"]:
            return self._send({"error": "TOKEN_REQUIRED"}, 403)
        n = int(self.headers.get("content-length") or 0)
        body = json.loads(self.rfile.read(n)) if n else {}
        p = self.path.split("?")[0]
        STATE["log"].append((self.command, self.path, body))
        if self.command == "POST" and p == "/api/servers":
            if not body.get("name"):
                return self._send("plain text failure", 400)
            sid = STATE["next"]
            STATE["next"] += 1
            STATE["servers"][sid] = {**body, "id": sid}
            return self._send(STATE["servers"][sid], 201)
        if self.command == "DELETE":
            STATE["servers"].pop(int(p.rsplit("/", 1)[1]), None)
            return self._send(None, 200)
        if p.endswith("/health"):
            return self._send({"status": "healthy", "latency_ms": 4})
        return self._send({"ok": True})

    do_POST = do_PUT = do_DELETE = _mutate

    def log_message(self, *_):
        pass


@pytest.fixture
def client():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Daemon)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    STATE.update(token="t1", servers={}, next=1, log=[])
    yield AgentDiscover(port=srv.server_address[1])
    srv.shutdown()


def test_lifecycle_calls_carry_the_token_and_json(client):
    assert client.healthy()
    s = client.create({"name": "echo", "transport": "stdio", "command": "revenueos-mcp-sandbox"}, enabled=False)
    assert s["id"] == 1 and client.find("echo")["command"] == "revenueos-mcp-sandbox" and client.find("nope") is None
    assert client.enable(1) == {"ok": True} and client.disable(1) == {"ok": True}
    assert client.probe(1)["status"] == "healthy"
    assert client.metrics(1)[0]["call_count"] == 2 and client.tools(1) == [{"name": "echo"}]
    client.put_secret(1, "FILES TOKEN", "s3cret")
    assert STATE["log"][-1] == ("PUT", "/api/servers/1/secrets/FILES%20TOKEN?new=1", {"value": "s3cret"})
    assert "source=registry" in client.plan("registry", "io.x/y", "1.0.0", "y")["query"]
    assert client.browse("pdf") == {"servers": []} and client.registry_sync() == {"ok": True}
    client.delete(1)
    assert client.servers() == []


def test_a_restarted_daemon_gets_a_fresh_token_once_and_errors_are_typed(client):
    client.create({"name": "a"})
    STATE["token"] = "t2"                       # the daemon restarted
    assert client.create({"name": "b"})["name"] == "b"
    with pytest.raises(AgentDiscoverError) as e:
        client.tools(99)
    assert e.value.status == 404 and "not found" in str(e.value)
    with pytest.raises(AgentDiscoverError, match="plain text failure"):
        client.create({})


def test_unreachable_daemon_is_unhealthy_not_an_exception():
    assert AgentDiscover(port=9).healthy() is False


def test_call_tool_relays_through_the_meta_tool(client, monkeypatch):
    seen = {}

    class Raw:
        def __init__(self, url, timeout_s):
            seen["url"], seen["timeout"] = url, timeout_s

        async def acall(self, tool, args):
            seen["call"] = (tool, args)
            return {"echo": "hi"}

    import revenueos_mcp_common
    monkeypatch.setattr(revenueos_mcp_common, "RawMcpClient", Raw, raising=False)
    assert client.call_tool("echo", "echo", {"message": "hi"}, timeout_s=5) == {"echo": "hi"}
    assert seen["call"] == ("call_tool", {"server": "echo", "tool": "echo", "arguments": {"message": "hi"}})
    assert seen["url"] == client.base and seen["timeout"] == 5
