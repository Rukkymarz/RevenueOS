"""INV-11: all agent egress passes through the L7 proxy with secret injection.

The decision service is tested here directly; the Envoy proof (denied-and-logged and
allowed-with-injected-secret) runs against the live stack in tests/e2e. The sandbox that
removes every other route lands in Phase 2."""
import importlib
import os
import sys

import pytest

AGENT = "7a1c2e30-0001-4000-8000-000000000001"


@pytest.fixture
def authz(tmp_path, monkeypatch):
    keychain = tmp_path / "keychain"
    monkeypatch.setenv("REVENUEOS_KEYCHAIN_DIR", str(keychain))
    sys.modules.pop("revenueos_egress_authz.app", None)
    mod = importlib.import_module("revenueos_egress_authz.app")
    from revenueos_common.secrets import KeychainStore
    KeychainStore(keychain).put("upstream-echo-token", "s3cret-value-123")
    policy = {"agents": {AGENT: {"allow": ["upstream-echo:8080"]}},
              "secret_bindings": [{"host": "upstream-echo:8080", "header": "authorization", "format": "Bearer {}",
                                   "secret_ref": "keychain://upstream-echo-token", "agents": [AGENT]}]}
    return mod, policy


def test_unknown_agent_is_denied(authz):
    mod, policy = authz
    ok, reason, inject = mod.decide("not-a-uuid", "", "upstream-echo:8080", "GET", "/", policy)
    assert not ok and "agent identity" in reason and inject == {}


def test_host_outside_allowlist_is_denied(authz):
    mod, policy = authz
    ok, reason, inject = mod.decide(AGENT, "", "exfil.example:443", "GET", "/steal", policy)
    assert not ok and "not allowlisted" in reason and inject == {}


def test_allowed_host_gets_secret_injected_by_reference(authz):
    mod, policy = authz
    ok, _, inject = mod.decide(AGENT, "", "upstream-echo:8080", "GET", "/ok", policy)
    assert ok and inject == {"authorization": "Bearer s3cret-value-123"}


def test_missing_secret_fails_closed(authz, tmp_path):
    mod, policy = authz
    os.remove(tmp_path / "keychain" / "upstream-echo-token")
    ok, reason, inject = mod.decide(AGENT, "", "upstream-echo:8080", "GET", "/ok", policy)
    assert not ok and "fail closed" in reason and inject == {}


def test_secret_with_line_break_is_refused(authz):
    mod, policy = authz
    from revenueos_common.secrets import KeychainStore
    KeychainStore(os.environ["REVENUEOS_KEYCHAIN_DIR"]).put("upstream-echo-token", "x\r\nx-evil: 1")
    ok, reason, _ = mod.decide(AGENT, "", "upstream-echo:8080", "GET", "/", policy)
    assert not ok and "line break" in reason


@pytest.mark.xfail(strict=True, raises=ImportError, reason="control lands in Phase 2 (sandbox with no network route)")
def test_direct_socket_from_sandbox_fails():
    from revenueos_sandbox.supervisor import run_in_sandbox
    result = run_in_sandbox(["python3", "-c", "import socket; socket.create_connection(('1.1.1.1', 53), 3)"])
    assert result.exit_code != 0
    assert "Network is unreachable" in result.stderr
