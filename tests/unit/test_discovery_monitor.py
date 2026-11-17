"""Runtime monitoring (spec 4.5/4.7): sandbox traces become tool_events and a violating server is
quarantined out of the active set."""
import pytest

from discovery_kit import FakeAgentDiscover, Secrets, manual_spec, pgdb  # noqa: F401
from revenueos_discovery import forage, registry, sources
from revenueos_discovery.monitor import TraceMonitor


def test_trace_violations_are_logged_and_quarantine_the_server(pgdb, tmp_path, monkeypatch):
    monkeypatch.setattr(sources, "enrich", lambda c: c)
    monkeypatch.setattr(forage, "ROOT", tmp_path)
    ad = FakeAgentDiscover()
    forage.install(pgdb, ad, Secrets({}), manual_spec("evil"))
    trace = tmp_path / "evil" / "trace"
    trace.mkdir(parents=True)
    (trace / "1.payload").write_text("/opt/x/evil.py")
    (trace / "1.log").write_text(
        '100 execve("/opt/x/evil.py", ["evil"], 0x0) = 0\n'
        '100 connect(3, {sa_family=AF_INET, sin_port=htons(443), sin_addr=inet_addr("203.0.113.9")}, 16) = -1 ENETUNREACH (Network is unreachable)\n'
        '100 openat(AT_FDCWD, "/run/revenueos/keychain/x", O_RDONLY) = -1 ENOENT (No such file or directory)\n')
    mon = TraceMonitor(pgdb, ad, root=tmp_path)
    found = mon.scan()
    assert {v["kind"] for v in found} >= {"egress_blocked", "secret_read_blocked"}
    inst = registry.installation(pgdb, "evil")
    assert inst["health_status"] == "QUARANTINED" and inst["active"] is False and ad.find("evil")["enabled"] is False
    kinds = {r["kind"] for r in pgdb.rows("SELECT kind FROM tool_events WHERE mcp_server_name = 'evil'")}
    assert {"egress_blocked", "secret_read_blocked", "quarantined"} <= kinds
    assert mon.scan() == []                                  # unchanged trace: reported once
