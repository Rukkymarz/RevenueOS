"""INV-10 and the governance of record (spec 4.2, 4.6): activation, approval, the observation
window, health, per-call re-checks and the event log, against the production triggers."""
import pytest

from discovery_kit import FakeAgentDiscover, manual_spec, new_task, pgdb  # noqa: F401
from revenueos_discovery import forage, registry
from discovery_kit import Secrets


@pytest.fixture(autouse=True)
def mcp_root(tmp_path, monkeypatch):
    monkeypatch.setattr(forage, "ROOT", tmp_path)


@pytest.fixture
def ad():
    return FakeAgentDiscover()


@pytest.fixture
def installed(pgdb, ad):
    out = forage.install(pgdb, ad, Secrets({}), manual_spec("echo"))
    assert out["status"] == "installed" and out["install_status"] == "experimental"
    return out


def kinds(db, server="echo"):
    return [r["kind"] for r in db.rows("SELECT kind FROM tool_events WHERE mcp_server_name = $s ORDER BY created_at, id", s=server)]


def test_experimental_server_cannot_activate_for_a_production_task(db, pgdb, ad, installed, world):
    task = new_task(db, "production")
    with pytest.raises(registry.ActivationRefused):
        registry.activate(pgdb, ad, server="echo", task_id=task)
    assert "activation_blocked" in kinds(pgdb)
    assert int(db.one("SELECT count(*) FROM tool_activations")) == 0


def test_experimental_server_activates_for_an_experimental_task(db, pgdb, ad, installed, world):
    task = new_task(db, "experimental")
    assert registry.activate(pgdb, ad, server="echo", task_id=task)["activated"] is True
    assert "activated" in kinds(pgdb) and ad.find("echo")["enabled"] is True


def test_approval_then_production_activation_works_and_an_agent_cannot_approve(db, pgdb, ad, installed, world):
    task = new_task(db, "production")
    with pytest.raises(PermissionError):
        registry.approve(pgdb, "echo", "agent:executor")
    registry.approve(pgdb, "echo", "christine")
    assert registry.activate(pgdb, ad, server="echo", task_id=task)["status"] == "approved"
    registry.approve(pgdb, "echo", "christine", to="production")
    assert registry.installation(pgdb, "echo")["status"] == "production"
    with pytest.raises(ValueError):
        registry.approve(pgdb, "echo", "christine", to="experimental")


def test_promotion_inside_the_observation_window_is_refused_by_the_database(db, pgdb, ad, world):
    forage.install(pgdb, ad, Secrets({}), manual_spec("watched", repo="example/watched"), )
    pgdb.rows("UPDATE tool_installations SET observe_until = now() + interval '14 days' WHERE mcp_server_name = 'watched' RETURNING id")
    with pytest.raises(Exception) as e:
        registry.approve(pgdb, "watched", "christine")
    assert "observ" in str(e.value).lower()
    db.rejects("UPDATE tool_installations SET observe_until = now() WHERE mcp_server_name = 'watched'", "observ")
    assert registry.installation(pgdb, "watched")["status"] == "experimental"


def test_unknown_server_and_unknown_task_are_refused(db, pgdb, ad, world):
    task = new_task(db, "experimental")
    assert registry.refusal(pgdb, "ghost", task)
    with pytest.raises(registry.NotInstalled):
        registry.installation(pgdb, "ghost")
    with pytest.raises(registry.NotInstalled):
        registry.set_active(pgdb, ad, "ghost", True)


def test_failed_probe_marks_unhealthy_removes_from_active_set_and_ends_activations(db, pgdb, ad, installed, world):
    task = new_task(db, "experimental")
    registry.activate(pgdb, ad, server="echo", task_id=task)
    ok = registry.probe(pgdb, ad, "echo")
    assert ok["healthy"] and registry.installation(pgdb, "echo")["health_status"] == "HEALTHY"
    ad.unhealthy.add("echo")
    bad = registry.probe(pgdb, ad, "echo")
    inst = registry.installation(pgdb, "echo")
    assert not bad["healthy"] and inst["health_status"] == "UNHEALTHY" and inst["active"] is False
    assert ad.find("echo")["enabled"] is False
    assert db.one("SELECT count(*) FROM tool_activations WHERE deactivated_at IS NULL") == "0"
    assert "health_failed" in kinds(pgdb)
    with pytest.raises(registry.ActivationRefused):
        registry.activate(pgdb, ad, server="echo", task_id=task)
    registry.release(pgdb, "echo", "christine")
    with pytest.raises(PermissionError):
        registry.release(pgdb, "echo", "agent:x")


def test_call_rechecks_inv10_every_time_and_logs_metrics(db, pgdb, ad, installed, world):
    task = new_task(db, "experimental")
    assert registry.call(pgdb, ad, server="echo", tool="echo", arguments={"message": "hi"}, task_id=task) == {"echo": "hi"}
    assert registry.metrics(ad, "echo")[0]["call_count"] == 1
    registry.mark_unhealthy(pgdb, ad, "echo", "quarantined", {"x": 1}, health="QUARANTINED")
    with pytest.raises(registry.ActivationRefused):
        registry.call(pgdb, ad, server="echo", tool="echo", arguments={}, task_id=task)
    assert "call_blocked" in kinds(pgdb)
    with pytest.raises(registry.NotInstalled):
        registry.metrics(ad, "ghost")
    assert registry.listing(pgdb)[0]["name"] == "echo"


def test_deactivate_is_scoped_and_logged(db, pgdb, ad, installed, world):
    task = new_task(db, "experimental")
    registry.activate(pgdb, ad, server="echo", task_id=task)
    assert registry.deactivate(pgdb, "echo", task) == 1 and registry.deactivate(pgdb, "echo") == 0
    assert "deactivated" in kinds(pgdb)


def test_tool_events_are_append_only(db, pgdb, ad, installed, world):
    db.rejects("DELETE FROM tool_events", "append-only")
    db.rejects("UPDATE tool_events SET kind = 'installed'", "append-only")
