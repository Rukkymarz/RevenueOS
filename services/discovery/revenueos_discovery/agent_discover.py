"""agent-discover (keshrath/agent-discover, pinned — docs/PINS.md) is the registry of record
(spec 4.2): its SQLite store holds which MCP servers are installed, indexed and enabled, their
per-server secrets, health and per-tool metrics. This module runs its daemon next to the
discovery service and talks to it over its own loopback REST API and MCP endpoint. Governance
(policy, INV-10, sandboxing) lives in RevenueOS and decides what this client is asked to do."""
import asyncio
import json
import os
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

ENTRY = os.environ.get("AGENT_DISCOVER_ENTRY", "/opt/agent-discover/dist/index.js")


class AgentDiscoverError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(f"agent-discover {status}: {message}")
        self.status = status


class AgentDiscover:
    def __init__(self, port: int | None = None):
        self.port = int(port or os.environ.get("AGENT_DISCOVER_PORT", 3424))
        self.base = f"http://127.0.0.1:{self.port}"
        self._token: tuple[str, str] | None = None
        self._proc: subprocess.Popen | None = None

    # -- daemon -----------------------------------------------------------------------------
    def start_daemon(self, data_dir: str, registry_url: str | None = None, wait_s: int = 60) -> None:
        env = {"PATH": os.environ.get("PATH", ""), "HOME": data_dir, "AGENT_DISCOVER_DATA_DIR": data_dir,
               "AGENT_DISCOVER_PORT": str(self.port), "AGENT_DISCOVER_IDLE_MS": "0",
               "AGENT_DISCOVER_SESSION_IDLE_MS": "0", "AGENT_DISCOVER_MODE": "proxy",
               "AGENT_DISCOVER_SECRETS": "file", "AGENT_DISCOVER_AUDIT_ARGS": "0",
               "REVENUEOS_MCP_ROOT": os.environ.get("REVENUEOS_MCP_ROOT", "/var/lib/revenueos/mcp")}
        if registry_url:
            env["AGENT_DISCOVER_REGISTRY_URL"] = registry_url
        os.makedirs(data_dir, exist_ok=True)

        def spawn():
            self._proc = subprocess.Popen(["node", ENTRY, "daemon"], env=env, stdin=subprocess.DEVNULL)

        def supervise():  # pragma: no cover - long-running
            while True:
                spawn()
                self._proc.wait()
                self._token = None
                time.sleep(2)

        threading.Thread(target=supervise, daemon=True, name="agent-discover").start()
        deadline = time.time() + wait_s
        while time.time() < deadline:
            if self.healthy():
                return
            time.sleep(0.5)
        raise AgentDiscoverError(0, "daemon did not become healthy")

    def healthy(self) -> bool:
        try:
            return self._req("GET", "/api/health").get("status") == "ok"
        except (AgentDiscoverError, OSError):
            return False

    # -- REST -------------------------------------------------------------------------------
    def _req(self, method: str, path: str, body: dict | None = None, timeout: int = 60, retry: bool = True):
        headers = {"accept": "application/json"}
        data = None
        if method != "GET":
            if self._token is None:
                t = self._req("GET", "/api/token")
                self._token = (t.get("header", "x-agent-discover-token"), t["token"])
            headers[self._token[0]] = self._token[1]
            data = json.dumps(body or {}).encode()
            headers["content-type"] = "application/json"
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            raw = e.read().decode(errors="replace")
            if e.code == 403 and retry and method != "GET":      # daemon restarted: new token
                self._token = None
                return self._req(method, path, body, timeout, retry=False)
            try:
                parsed = json.loads(raw)
                msg = parsed.get("error", raw) if isinstance(parsed, dict) else str(parsed)
            except ValueError:
                msg = raw
            raise AgentDiscoverError(e.code, str(msg)[:500]) from None

    def servers(self) -> list[dict]:
        out = self._req("GET", "/api/servers")
        return out if isinstance(out, list) else out.get("servers", [])

    def find(self, name: str) -> dict | None:
        return next((s for s in self.servers() if s.get("name") == name), None)

    def create(self, spec: dict, enabled: bool = False) -> dict:
        return self._req("POST", "/api/servers", {**spec, "enabled": enabled}, timeout=120)

    def delete(self, server_id) -> None:
        self._req("DELETE", f"/api/servers/{server_id}")

    def enable(self, server_id) -> dict:
        return self._req("POST", f"/api/servers/{server_id}/enable", timeout=120)

    def disable(self, server_id) -> dict:
        return self._req("POST", f"/api/servers/{server_id}/disable")

    def probe(self, server_id) -> dict:
        return self._req("POST", f"/api/servers/{server_id}/health", timeout=60)

    def metrics(self, server_id) -> list[dict]:
        return self._req("GET", f"/api/servers/{server_id}/metrics")

    def tools(self, server_id) -> list[dict]:
        return self._req("GET", f"/api/servers/{server_id}").get("tools", [])

    def put_secret(self, server_id, key: str, value: str) -> None:
        self._req("PUT", f"/api/servers/{server_id}/secrets/{urllib.parse.quote(key)}?new=1", {"value": value})

    def plan(self, source: str, name: str, version: str | None = None, local_name: str | None = None) -> dict:
        q = {"source": source, "name": name}
        if version:
            q["version"] = version
        if local_name:
            q["local_name"] = local_name
        return self._req("GET", "/api/install/plan?" + urllib.parse.urlencode(q), timeout=60)

    def browse(self, query: str, limit: int = 10) -> dict:
        return self._req("GET", "/api/browse?" + urllib.parse.urlencode({"query": query, "limit": limit}), timeout=60)

    def registry_sync(self) -> dict:
        return self._req("POST", "/api/registry/sync", timeout=300)

    # -- MCP --------------------------------------------------------------------------------
    def call_tool(self, server: str, tool: str, arguments: dict, timeout_s: float = 60.0):
        """Relay one call through agent-discover's own `call_tool` meta tool, so its pool, its
        per-tool metrics and its audit log all see it (spec 4.2)."""
        from revenueos_mcp_common import RawMcpClient
        client = RawMcpClient(self.base, timeout_s=timeout_s)
        return asyncio.run(client.acall("call_tool", {"server": server, "tool": tool, "arguments": arguments}))
