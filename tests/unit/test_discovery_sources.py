"""Forage's sources (spec 4.1, 4.3, 4.4) against the offline fixture that stands in for the
public endpoints: three parallel searches, enrichment, curated-list ingestion, and the
mcptoon / MCPfinder adapters."""
import importlib.util
import os
import stat
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

import dbkit
from discovery_kit import FakeAgentDiscover, pgdb  # noqa: F401
from revenueos_common.db import Database
from revenueos_discovery import sources

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def fixture_url():
    spec = importlib.util.spec_from_file_location("discovery_fixture", ROOT / "infra/discovery/fixture/server.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), mod.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


@pytest.fixture
def endpoints(fixture_url, monkeypatch):
    for name in ("REGISTRY", "SMITHERY", "NPM", "GITHUB_API", "RAW"):
        monkeypatch.setattr(sources, name, fixture_url)
    return fixture_url


def test_parallel_search_merges_registry_smithery_and_npm(endpoints):
    found, errors = sources.parallel_search("echo", 5)
    assert errors == {}
    by = {c["source"]: c for c in reversed(found) if c["name"] == "io.revenueos.fixture/echo" or c["source"] != "registry"}
    assert set(by) == {"registry", "smithery", "npm"}
    assert by["registry"]["name"] == "io.revenueos.fixture/echo" and by["registry"]["repo"] == "revenueos-fixture/echo"
    assert by["registry"]["url"].endswith("/mcp") and by["npm"]["package_type"] == "npm"
    assert by["smithery"]["uses"] == 7


def test_one_dead_registry_is_reported_and_does_not_hide_the_others(endpoints, monkeypatch):
    monkeypatch.setattr(sources, "SMITHERY", "http://127.0.0.1:9")
    found, errors = sources.parallel_search("echo", 5)
    assert set(errors) == {"smithery"} and {c["source"] for c in found} == {"registry", "npm"}


def test_enrich_adds_license_and_activity_and_tolerates_unknown_repos(endpoints):
    c = sources.enrich({"repo": "revenueos-fixture/echo"})
    assert c["license"] == "MIT" and c["archived"] is False and c["stars"] == 120 and len(c["last_push"]) == 10
    stale = sources.enrich({"repo": "revenueos-fixture/abandoned"})
    assert stale["license"] is None and stale["archived"] is True
    assert sources.enrich({"repo": "nobody/nothing"}) == {"repo": "nobody/nothing"}
    npm = sources.enrich({"package_type": "npm", "package": "@x/y", "version": "1.0.0"})   # 404: left unknown
    assert not npm.get("checksum")


def test_parse_list_reads_links_descriptions_and_star_signals():
    md = ("# title\nprose with a [link](https://github.com/not/an-entry)\n"
          "- [Alpha](https://github.com/Org/alpha) [![b](https://x/b.svg)](https://x) 🐍 - First server ⭐ 1.2K\n"
          "- **[Beta](https://github.com/org/beta/tree/main/src)** - Second\n"
          "- [Alpha again](https://github.com/org/alpha) - duplicate\n"
          "<details><summary><b><a href=\"x\">c</a></b> [Gamma](https://github.com/org/gamma) (⭐ 79K)</summary>\n"
          "- [no repo](https://example.com/x) - skipped\n")
    got = sources.parse_list(md)
    assert [(e["name"], e["repo"], e["stars"]) for e in got] == [
        ("Alpha", "Org/alpha", 1200), ("Beta", "org/beta", None), ("Gamma", "org/gamma", 79000)]
    assert got[0]["description"].startswith("First server") and got[1]["description"] == "Second"


def test_ingest_curated_sources_and_search_them(endpoints, pgdb, db):
    lst = {"name": "awesome-fixture", "kind": "awesome-list", "repo": "revenueos-fixture/list", "commit_sha": "a" * 40}
    assert sources.ingest(pgdb, lst) == 2
    assert sources.ingest(pgdb, lst) == 2                                  # re-ingest replaces, never duplicates
    reg = {"name": "official-mcp-registry", "kind": "registry", "url": endpoints, "commit_sha": None}
    assert sources.ingest(pgdb, reg) == 2
    assert db.one("SELECT entries FROM discovery_sources WHERE name = 'awesome-fixture'") == "2"
    assert db.one("SELECT count(*) FROM discovery_entries") == "4"
    hits = sources.search_curated(pgdb, "echo", 10)
    assert hits[0]["stars"] == 120 and hits[0]["source"] == "curated" and hits[0]["list"] == "awesome-fixture"
    assert {s["name"] for s in sources.CURATED} == {"official-mcp-registry", "awesome-mcp-servers-2026",
                                                    "awesome-mcp", "best-of-mcp-servers"}
    assert all(s["commit_sha"] for s in sources.CURATED if s["kind"] == "awesome-list")


def fake_mcptoon(tmp_path, body: str):
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    exe = bindir / "mcptoon"
    exe.write_text("#!/bin/sh\n" + body)
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    return str(bindir)


def test_mcptoon_adapter_parses_json_and_text_and_reports_failure(tmp_path, monkeypatch):
    home = str(tmp_path / "home")
    os.makedirs(home)
    path = fake_mcptoon(tmp_path, '''case "$*" in
  *--search\\ json*) echo 'banner'; echo '[{"name": "gh", "description": "GitHub", "source": "registry", "url": "https://x/mcp"}]';;
  *--search\\ text*) echo 'github-mcp  GitHub tools'; echo 'note: ignored';;
  *--search\\ boom*) echo 'No MCP registry reachable' >&2; exit 2;;
  *manifest*) echo '{"tools": ["a", "b"]}';;
  *) echo ok;;
esac
''')
    monkeypatch.setenv("PATH", path + os.pathsep + os.environ["PATH"])
    assert sources.search_mcptoon("json", 5, home) == [
        {"source": "mcptoon", "name": "gh", "description": "GitHub", "url": "https://x/mcp", "command": None,
         "args": None, "via": "registry"}]
    assert sources.search_mcptoon("text", 5, home)[0]["name"] == "github-mcp"
    with pytest.raises(RuntimeError, match="No MCP registry reachable"):
        sources.search_mcptoon("boom", 5, home)
    assert sources.mcptoon_manifest(home, "http://127.0.0.1:3424") == {"manifest": {"tools": ["a", "b"]}}
    path2 = fake_mcptoon(tmp_path, "echo 'plain manifest text'\n")
    monkeypatch.setenv("PATH", path2 + os.pathsep + os.environ["PATH"])
    assert sources.mcptoon_manifest(home, "http://127.0.0.1:3424")["manifest_text"] == "plain manifest text"


def test_mcpfinder_adapter_calls_its_tools_through_the_registry():
    ad = FakeAgentDiscover()
    ad.create({"name": "mcpfinder"}, enabled=True)
    got = sources.search_mcpfinder(ad, "pdf", 3)
    assert got == [{"source": "mcpfinder", "name": "found-by-mcpfinder", "description": "d", "repo": "a/b",
                    "trust": {"stars": 5}}]
    d = sources.mcpfinder_details(ad, "found-by-mcpfinder")
    assert d["details"]["tool"] == "get_server_details" and d["install"]["tool"] == "get_install_config"
    assert [c[1] for c in ad.calls] == ["search_mcp_servers", "get_server_details", "get_install_config"]
