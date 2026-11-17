"""Shared fakes for the Phase 4 unit tests: an in-memory stand-in for agent-discover's REST
surface (the real daemon is Node and runs only in the compose stack, tests/e2e/test_phase4_stack.py)."""
import itertools


class FakeAgentDiscover:
    base = "http://127.0.0.1:3424"

    def __init__(self, plans=None):
        self._ids = itertools.count(1)
        self.rows: dict[int, dict] = {}
        self.secrets: dict[int, dict] = {}
        self.calls: list[tuple] = []
        self.plans = plans or {}
        self.fail_enable: set[str] = set()
        self.unhealthy: set[str] = set()
        self.tool_defs = [{"name": "echo", "description": "Echo a message back.\nSecond line.",
                           "input_schema": {"required": ["message"], "properties": {"message": {}}}},
                          {"name": "add", "description": "", "inputSchema": {"properties": {"a": {}, "b": {}}}}]

    def healthy(self):
        return True

    def servers(self):
        return list(self.rows.values())

    def find(self, name):
        return next((s for s in self.rows.values() if s["name"] == name), None)

    def create(self, spec, enabled=False):
        i = next(self._ids)
        self.rows[i] = {**spec, "id": i, "enabled": enabled}
        return self.rows[i]

    def delete(self, server_id):
        self.rows.pop(server_id, None)

    def enable(self, server_id):
        if self.rows[server_id]["name"] in self.fail_enable:
            raise RuntimeError("index failed: server did not start")
        self.rows[server_id]["enabled"] = True
        return self.rows[server_id]

    def disable(self, server_id):
        self.rows[server_id]["enabled"] = False
        return self.rows[server_id]

    def probe(self, server_id):
        if self.rows[server_id]["name"] in self.unhealthy:
            return {"status": "unhealthy", "error": "connection closed"}
        return {"status": "healthy", "latency_ms": 3}

    def metrics(self, server_id):
        name = self.rows[server_id]["name"]
        n = sum(1 for c in self.calls if c[0] == name)
        return [{"tool_name": "echo", "call_count": n, "error_count": 0, "avg_latency_ms": 2}] if n else []

    def tools(self, server_id):
        return self.tool_defs

    def put_secret(self, server_id, key, value):
        self.secrets.setdefault(server_id, {})[key] = value

    def plan(self, source, name, version=None, local_name=None):
        return self.plans[name]

    def call_tool(self, server, tool, arguments, timeout_s=60.0):
        entry = self.find(server)
        if entry is None or not entry["enabled"]:
            raise RuntimeError(f"{server} is not enabled")
        self.calls.append((server, tool, arguments))
        if server == "mcpfinder":
            return {"servers": [{"name": "found-by-mcpfinder", "description": "d", "repository": "https://github.com/a/b",
                                 "stars": 5}]} if tool == "search_mcp_servers" else {"tool": tool, **arguments}
        return {"echo": arguments.get("message")}


class Secrets:
    def __init__(self, values):
        self.values = values

    def get(self, ref):
        return self.values.get(ref)


REMOTE_PLAN = {"server": "echo", "registry_name": "io.revenueos.fixture/echo", "source": "registry",
               "description": "Echo", "version": "1.0.0", "transport": "streamable-http",
               "url": "https://mcp.example.com/mcp", "requirements": [], "warnings": [],
               "provenance": {"checks": [{"status": "pass", "detail": "listed"}]},
               "input": {"repository": "https://github.com/revenueos-fixture/echo"}}
STDIO_PLAN = {"server": "files", "registry_name": "io.example/files", "source": "registry", "description": "Files",
              "version": "2.1.0", "transport": "stdio", "command": "npx", "args": ["-y", "@example/files-mcp@2.1.0"],
              "requirements": [{"kind": "env", "key": "FILES_TOKEN", "required": True, "present": False}],
              "warnings": [], "provenance": {"checks": [{"status": "pass", "detail": "published by owner"}]},
              "input": {"repository": "https://github.com/example/files", "package_name": "@example/files-mcp"}}


import pytest  # noqa: E402

import dbkit  # noqa: E402
from revenueos_common.db import Database  # noqa: E402


@pytest.fixture
def pgdb(db):
    return Database(dbname=db.name, host=dbkit.HOST, port=dbkit.PORT, user=dbkit.USER, actor="discovery-test")


def new_task(db, environment="production"):
    return db.one("INSERT INTO tasks(objective, task_class, acceptance_criteria, environment) "
                  f"VALUES ('use a server','code','[{{\"check\":\"tests_pass\"}}]','{environment}') RETURNING id")


def manual_spec(name="echo", **over):
    spec = {"source": "manual", "name": name, "transport": "streamable-http", "url": "https://mcp.example.com/mcp",
            "version": "1.0.0", "license": "MIT", "last_push": "2026-10-01", "checksum": "sha256:" + "a" * 64,
            "repo": "example/echo", "description": "Echo"}
    spec.update(over)
    return spec
