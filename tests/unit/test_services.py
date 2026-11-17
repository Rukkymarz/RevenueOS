"""Every service and infra process has a real entrypoint and a contract-shaped /health (spec 1.1)."""
import importlib
from pathlib import Path

import pytest
from starlette.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
SERVICES = sorted(d.name for d in (ROOT / "services").iterdir() if d.is_dir())
HEALTH_KEYS = {"service", "status", "version", "checks"}


def test_every_service_directory_from_the_layout_exists():
    expected = {"orchestrator", "runtime-omni", "runtime-os", "identity", "discovery", "pm", "research", "web",
                "social", "marketing", "qc", "insight", "learning", "media", "scrape", "outreach",
                "ambient-watchers"}
    assert set(SERVICES) == expected


@pytest.mark.parametrize("name", SERVICES)
def test_service_health_and_info(name):
    pkg = "revenueos_" + name.replace("-", "_")
    mod = importlib.import_module(f"{pkg}.app")
    meta = importlib.import_module(pkg)
    importlib.import_module(f"{pkg}.__main__")  # entrypoint imports cleanly
    c = TestClient(mod.app)
    r = c.get("/health")
    assert r.status_code == 200, r.text
    body = r.json()
    assert HEALTH_KEYS <= set(body) and body["service"] == name and body["status"] == "ok"
    info = c.get("/v1/info").json()
    assert info["component"] == meta.COMPONENT and info["hosts"], f"{name} hosts no components"


def test_sandbox_supervisor_info():
    mod = importlib.import_module("revenueos_sandbox_supervisor.app")
    assert TestClient(mod.app).get("/v1/info").json()["backend"] == "bubblewrap"


def test_no_empty_directories_in_the_workspace():
    skip = {".git", "node_modules", "dist", ".next", "__pycache__", ".turbo", "vendor", "out", "generated"}
    empty = [str(p.relative_to(ROOT)) for p in ROOT.rglob("*")
             if p.is_dir() and not any(p.iterdir()) and not (set(p.relative_to(ROOT).parts) & skip)]
    assert not empty, f"empty directories: {empty}"


def test_orchestrator_remote_control_forwards_with_token_and_trace(monkeypatch, tmp_path):
    pytest.importorskip("fastmcp")   # telemetry comes from mcp-common; installed in CI
    import json as _json

    import httpx
    from revenueos_common.secrets import KeychainStore
    mod = importlib.import_module("revenueos_orchestrator.app")
    monkeypatch.setenv("REVENUEOS_KEYCHAIN_DIR", str(tmp_path / "kc"))
    c = TestClient(mod.app)
    body = {"task_id": "t", "agent_id": "a", "args": {}}
    assert c.post("/v1/runtime/tools/fs.read_file", json=body).status_code == 503   # no token: closed
    KeychainStore(tmp_path / "kc").put("runtime-omni-token", "tok-123")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(url=str(request.url), auth=request.headers["authorization"], body=_json.loads(request.content))
        return httpx.Response(403, json={"status": "blocked", "risk_class": "critical"})
    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    r = c.post("/v1/runtime/tools/shell.run_command", json=body)
    assert r.status_code == 403 and r.json()["status"] == "blocked" and len(r.json()["trace_id"]) == 32
    assert seen["url"].endswith("/v1/tools/shell.run_command/invoke") and seen["auth"] == "Bearer tok-123"
    assert seen["body"]["traceparent"].startswith("00-")
