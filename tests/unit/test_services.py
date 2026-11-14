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
                "social", "marketing", "qc", "insight", "learning", "media", "scrape", "outreach"}
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


def test_sandbox_supervisor_reports_kernel_capabilities():
    mod = importlib.import_module("revenueos_sandbox_supervisor.app")
    info = TestClient(mod.app).get("/v1/info").json()
    assert set(info["capabilities"]) == {"unshare", "overlayfs", "bubblewrap", "user_namespaces"}


def test_no_empty_directories_in_the_workspace():
    skip = {".git", "node_modules", "dist", ".next", "__pycache__", ".turbo", "vendor", "out", "generated"}
    empty = [str(p.relative_to(ROOT)) for p in ROOT.rglob("*")
             if p.is_dir() and not any(p.iterdir()) and not (set(p.relative_to(ROOT).parts) & skip)]
    assert not empty, f"empty directories: {empty}"
