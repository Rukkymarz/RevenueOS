"""HTTP surface of the discovery service with the registry and agent-discover faked."""
import pytest
from starlette.testclient import TestClient

from discovery_kit import FakeAgentDiscover, Secrets, manual_spec, new_task, pgdb  # noqa: F401
from revenueos_discovery import app as appmod, forage, sources


@pytest.fixture
def client(pgdb, tmp_path, monkeypatch, db):
    monkeypatch.setattr(sources, "enrich", lambda c: c)
    monkeypatch.setattr(forage, "ROOT", tmp_path)
    monkeypatch.setattr(appmod, "ROOT", tmp_path)
    appmod._state.clear()
    appmod._state.update(db=pgdb, ad=FakeAgentDiscover(), secrets=Secrets({}))
    yield TestClient(appmod.app)
    appmod._state.clear()


def test_health_reports_the_daemon_and_info_lists_components(client):
    assert client.get("/health").status_code == 200
    assert client.get("/v1/info").json()["component"] == "C04"


def test_install_activate_call_approve_flow_over_http(client, db, world):
    r = client.post("/v1/forage/install", json={"spec": manual_spec("echo")})
    assert r.json()["status"] == "installed"
    prod, exp = new_task(db, "production"), new_task(db, "experimental")
    assert client.post("/v1/servers/echo/activate", json={"task_id": prod}).status_code == 403
    assert client.post("/v1/call", json={"server": "echo", "tool": "echo", "arguments": {"message": "x"},
                                         "task_id": prod}).status_code == 403
    ok = client.post("/v1/call", json={"server": "echo", "tool": "echo", "arguments": {"message": "x"}, "task_id": exp})
    assert ok.json() == {"status": "ok", "result": {"echo": "x"}}
    assert client.post("/v1/servers/echo/approve", json={"approved_by": "agent:x"}).status_code == 403
    assert client.post("/v1/servers/echo/approve", json={"approved_by": "christine"}).json()["status"] == "approved"
    assert client.post("/v1/servers/echo/activate", json={"task_id": prod}).json()["activated"] is True
    assert client.post("/v1/servers/echo/deactivate", json={}).json()["deactivated"] >= 1
    assert client.post("/v1/servers/echo/probe").json()["healthy"] is True
    assert client.get("/v1/servers/echo/metrics").json()["metrics"]
    kinds = [e["kind"] for e in client.get("/v1/servers/echo/events").json()["events"]]
    assert "activation_blocked" in kinds and "call_blocked" in kinds and "approved" in kinds
    assert client.get("/v1/servers").json()["servers"][0]["name"] == "echo"
    assert client.post("/v1/servers/echo/release", json={"approved_by": "christine"}).status_code == 200
    assert client.post("/v1/forage/learn", json={"server": "echo"}).json()["marker"] == "<!-- forage:echo -->"


def test_errors_are_typed(client):
    assert client.post("/v1/servers/ghost/probe").status_code == 404
    assert client.post("/v1/forage/learn", json={"server": "ghost"}).status_code == 404
    assert client.post("/v1/forage/search", json={}).status_code == 400            # missing query -> KeyError
    assert client.post("/v1/forage/install", json={"spec": {"name": "x", "source": "manual", "transport": "stdio",
                                                            "command": "bash", "args": ["-c", "x"]}}).json()["status"] == "denied"


def test_bootstrap_registers_pinned_components_once(client, monkeypatch):
    appmod.bootstrap()
    names = {s["name"] for s in appmod.ad().servers()}
    assert names == {"mcpfinder", "api-anything"}
    assert appmod.ad().find("api-anything")["enabled"] is False
    appmod.bootstrap()
    assert len(appmod.ad().servers()) == 2


def test_sandbox_env_names_no_secret_values(tmp_path, monkeypatch):
    monkeypatch.setattr(appmod, "ROOT", tmp_path)
    monkeypatch.setenv("PGHOST", "db")
    appmod.write_sandbox_env()
    text = (tmp_path / "sandbox-env.json").read_text()
    assert '"PGHOST": "db"' in text and "password" not in text.lower()
