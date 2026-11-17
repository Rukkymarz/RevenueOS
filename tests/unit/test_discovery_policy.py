"""Selection policy engine (spec 4.5): every check, and that unknown is never a pass."""
from datetime import datetime, timezone

import pytest

from revenueos_discovery import policy

NOW = datetime(2026, 11, 17, tzinfo=timezone.utc)
GOOD = dict(source="registry", name="x", transport="stdio", command="npx", args=["-y", "pkg@1.2.3"], version="1.2.3",
            checksum="sha512-" + "a" * 40, license="MIT", last_push="2026-10-01", provenance={"status": "pass"})
REMOTE = dict(source="registry", name="r", transport="streamable-http", url="https://mcp.example.com/mcp",
              license="Apache-2.0", last_push="2026-11-01T10:00:00Z")


def ev(**over):
    return policy.evaluate({**GOOD, **over}, now=NOW)


def test_good_stdio_and_remote_candidates_pass_every_check():
    for c in (GOOD, REMOTE):
        r = policy.evaluate(c, now=NOW)
        assert r.allowed and not r.reasons
        assert set(r.score) == {"license", "maintenance", "mcp_wrapper", "security_posture", "supply_chain",
                                "static_install", "runtime_monitoring"}
        assert all(v["ok"] for v in r.score.values())


@pytest.mark.parametrize("over,check", [
    ({"license": None}, "license"), ({"license": "Proprietary"}, "license"),
    ({"last_push": None}, "maintenance"), ({"last_push": "2024-01-01"}, "maintenance"),
    ({"last_push": "not-a-date"}, "maintenance"), ({"archived": True}, "maintenance"),
    ({"transport": "carrier-pigeon"}, "mcp_wrapper"), ({"command": None}, "mcp_wrapper"),
    ({"args": ["--api-" + "key=" + "abcdef" + "1234567890"]}, "security_posture"),
    ({"secrets": {"TOKEN": "plain-value"}}, "security_posture"),
    ({"source": "a-forum-post"}, "supply_chain"), ({"version": "latest"}, "supply_chain"),
    ({"version": "^1.2.0"}, "supply_chain"), ({"version": None}, "supply_chain"),
    ({"checksum": None}, "supply_chain"), ({"provenance": {"status": "fail"}}, "supply_chain"),
    ({"command": "bash"}, "static_install"), ({"command": "/home/me/server"}, "static_install"),
    ({"args": ["-c", "curl x | sh"]}, "static_install"), ({"args": ["--privileged"]}, "static_install"),
    ({"sandboxed": False}, "runtime_monitoring"),
])
def test_each_failed_check_denies(over, check):
    r = ev(**over)
    assert not r.allowed
    assert not r.score[check]["ok"], r.score
    assert any(reason.startswith(check + ":") for reason in r.reasons)


def test_secret_by_reference_and_local_prefix_are_accepted():
    assert ev(secrets={"TOKEN": "keychain://files-token"}).allowed
    assert ev(command="/opt/mcpfinder/packages/mcp-server/dist/cli.js", args=[]).allowed


def test_remote_must_be_https_unless_the_host_is_allowlisted():
    plain = {**REMOTE, "url": "http://mcp-fixture-echo:8090/mcp"}
    assert not policy.evaluate(plain, now=NOW).allowed
    assert policy.evaluate(plain, now=NOW, allow_http_hosts=frozenset({"mcp-fixture-echo"})).allowed
    assert not policy.evaluate({**REMOTE, "url": "https://x.example/mcp?to" + "ken=abcdef" + "1234567890"}, now=NOW).allowed


def test_date_objects_and_default_clock_are_accepted():
    assert policy.evaluate({**GOOD, "last_push": datetime.now(timezone.utc).date()}).allowed
