"""Forage install and learn (spec 4.1, 4.5, 4.7): the selection policy gates the install, each server gets
its own identity, egress scope and secret scope, an install is usable at once, and secrets only ever
appear by reference."""
import json

import pytest

from discovery_kit import REMOTE_PLAN, STDIO_PLAN, FakeAgentDiscover, Secrets, manual_spec, pgdb  # noqa: F401
from revenueos_discovery import forage, registry, sources


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(forage, "ROOT", tmp_path)
    return tmp_path


@pytest.fixture(autouse=True)
def no_network_enrichment(monkeypatch):
    monkeypatch.setattr(sources, "enrich", lambda c: c)


def test_local_name_is_a_safe_slug():
    assert forage.local_name("io.github.Org/My Server!") == "my-server"
    assert forage.local_name("///") == "server"


def test_install_registers_usable_server_in_the_same_session(pgdb, root):
    ad = FakeAgentDiscover()
    out = forage.install(pgdb, ad, Secrets({}), manual_spec("echo"))
    assert out["status"] == "installed" and out["tools"] == ["echo", "add"]
    assert ad.find("echo")["enabled"] is True and registry.installation(pgdb, "echo")["active"] is True
    assert registry.installation(pgdb, "echo")["status"] == "experimental"


def test_policy_denial_installs_nothing_and_is_logged(pgdb, root):
    ad = FakeAgentDiscover()
    out = forage.install(pgdb, ad, Secrets({}), manual_spec("bad", license=None, repo="x/bad"))
    assert out["status"] == "denied" and out["reasons"] and ad.servers() == []
    assert pgdb.scalar("SELECT count(*) AS n FROM tool_events WHERE kind = 'policy_denied' AND mcp_server_name = 'bad'") == 1
    assert pgdb.scalar("SELECT count(*) AS n FROM tool_installations") == 0


def test_stdio_server_is_sandboxed_with_its_own_identity_egress_and_secret_scope(pgdb, root):
    ad = FakeAgentDiscover(plans={"io.example/files": STDIO_PLAN})
    sec = Secrets({"keychain://files-token": "s3cr3t-value"})
    spec = {"source": "registry", "name": "io.example/files", "local_name": "files",
            "secrets": {"FILES_TOKEN": "keychain://files-token"}, "license": "MIT", "last_push": "2026-10-20",
            "checksum": "sha256:" + "c" * 64}
    out = forage.install(pgdb, ad, sec, spec, agent_id=None)
    assert out["status"] == "installed", out
    row = ad.find("files")
    assert row["command"] == "revenueos-mcp-sandbox" and row["args"][:3] == ["files", "--env", "FILES_TOKEN"]
    assert ad.secrets[row["id"]] == {"FILES_TOKEN": "s3cr3t-value"}
    ident = pgdb.scalar("SELECT id AS i FROM agents WHERE name = 'mcp:files'")
    hosts = [r["host"] for r in pgdb.rows("SELECT host FROM egress_rules WHERE agent_id = $a::uuid ORDER BY host", a=ident)]
    assert hosts == ["registry.npmjs.org"]
    assert json.loads((root / "files" / "egress.json").read_text())["agent_id"] == ident
    spec_row = registry.installation(pgdb, "files")["install_spec"]
    assert "s3cr3t-value" not in json.dumps(spec_row) and spec_row["secrets"] == {"FILES_TOKEN": "keychain://files-token"}


def test_unprovisioned_secret_aborts_cleanly(pgdb, root):
    ad = FakeAgentDiscover(plans={"io.example/files": STDIO_PLAN})
    out = forage.install(pgdb, ad, Secrets({}), {"source": "registry", "name": "io.example/files", "local_name": "files",
                                                  "secrets": {"FILES_TOKEN": "keychain://missing"},
                                                  "license": "MIT", "last_push": "2026-10-20", "checksum": "sha256:" + "c" * 64})
    assert out["status"] == "denied" and "not provisioned" in out["reasons"][0] and ad.servers() == []


def test_registry_plan_blocked_by_the_registry_is_denied(pgdb, root):
    ad = FakeAgentDiscover(plans={"x/y": {**REMOTE_PLAN, "blocked": "publisher namespace not verified"}})
    out = forage.install(pgdb, ad, Secrets({}), {"source": "registry", "name": "x/y"})
    assert out["status"] == "denied" and out["reasons"] == ["publisher namespace not verified"]


def test_server_that_fails_to_start_is_installed_unhealthy_and_inactive(pgdb, root):
    ad = FakeAgentDiscover()
    ad.fail_enable.add("flaky")
    out = forage.install(pgdb, ad, Secrets({}), manual_spec("flaky", repo="example/flaky"))
    inst = registry.installation(pgdb, "flaky")
    assert out["status"] == "installed_unhealthy" and inst["active"] is False and inst["health_status"] == "UNHEALTHY"


def test_quarantine_survives_a_reinstall(pgdb, root):
    ad = FakeAgentDiscover()
    forage.install(pgdb, ad, Secrets({}), manual_spec("echo"))
    registry.mark_unhealthy(pgdb, ad, "echo", "quarantined", {}, health="QUARANTINED")
    out = forage.install(pgdb, ad, Secrets({}), manual_spec("echo"))
    assert out["status"] == "denied" and "quarantined" in out["reasons"][0]
    assert registry.installation(pgdb, "echo")["health_status"] == "QUARANTINED"


def test_pinned_bootstrap_with_observation_window_and_approver(pgdb, root):
    ad = FakeAgentDiscover()
    out = forage.install(pgdb, ad, Secrets({}), manual_spec("api-anything", observe_days=14, enable=False, repo="g/api"))
    assert out["install_status"] == "experimental" and "tools" not in out
    assert registry.installation(pgdb, "api-anything")["observe_until"] is not None
    out = forage.install(pgdb, ad, Secrets({}), manual_spec("finder", approved_by="bootstrap:docs/PINS.md"))
    assert out["install_status"] == "approved"


def test_learn_writes_usage_instructions_from_the_indexed_tools(pgdb, root):
    ad = FakeAgentDiscover()
    forage.install(pgdb, ad, Secrets({}), manual_spec("echo"))
    out = forage.learn(pgdb, ad, "echo")
    assert out["marker"] == "<!-- forage:echo -->" and "`mcp.call`" in out["instructions"]
    assert "`echo` — Echo a message back." in out["instructions"] and "required: message" in out["instructions"]
    assert "experimental" in out["instructions"]
    with pytest.raises(registry.NotInstalled):
        forage.learn(pgdb, ad, "ghost")


def test_search_merges_adapters_and_survives_one_failing(pgdb, monkeypatch):
    monkeypatch.setattr(sources, "parallel_search", lambda q, n: ([{"source": "registry", "name": "A"},
                                                                    {"source": "registry", "name": "a"}], {}))
    monkeypatch.setattr(sources, "search_mcptoon", lambda *a: (_ for _ in ()).throw(RuntimeError("mcptoon down")))
    monkeypatch.setattr(sources, "search_mcpfinder", lambda ad, q, n: [{"source": "mcpfinder", "name": "B"}])
    out = forage.search(pgdb, FakeAgentDiscover(), "x")
    assert [c["name"] for c in out["candidates"]] == ["A", "B"] and "mcptoon" in out["errors"]
    assert pgdb.scalar("SELECT count(*) AS n FROM tool_events WHERE kind = 'searched'") == 1
