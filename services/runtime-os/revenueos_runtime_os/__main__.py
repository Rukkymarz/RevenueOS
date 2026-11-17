"""Entrypoints: serve (default), issue-token, reap, expire-subagents."""
import argparse
import os
import sys

from revenueos_common.service import run

from . import DEFAULT_PORT


def _kernel():
    from .app import kernel
    return kernel()


def main() -> None:
    ap = argparse.ArgumentParser(prog="revenueos-runtime-os")
    sub = ap.add_subparsers(dest="cmd")
    tok = sub.add_parser("issue-token", help="issue a NAVA bearer token for an agent and store it by ref")
    tok.add_argument("agent_id")
    tok.add_argument("--ttl", type=int, default=None, help="seconds until expiry (default: none)")
    reap = sub.add_parser("reap", help="close syscalls orphaned by a crash (rollback + release locks)")
    reap.add_argument("--older-than", type=int, default=600)
    sub.add_parser("expire-subagents", help="kill JIT subagents past their TTL")
    sub.add_parser("serve")
    ns = ap.parse_args()

    if ns.cmd == "issue-token":
        from revenueos_common.secrets import KeychainStore, SecretResolver
        k = _kernel()
        token = k.issue_token(ns.agent_id, ttl_s=ns.ttl)
        ref = f"keychain://nava-agent-{ns.agent_id}"
        SecretResolver(KeychainStore(os.environ.get("REVENUEOS_KEYCHAIN_DIR", "/run/revenueos/keychain"))).put(ref, token)
        print(ref)                      # the token itself is never printed (R: secrets by reference only)
        return
    if ns.cmd == "reap":
        for sid in _kernel().gw.reap(older_than_s=ns.older_than):
            print(sid)
        return
    if ns.cmd == "expire-subagents":
        print(_kernel().db.scalar("SELECT nava_expire_subagents() AS n"))
        return

    from .app import app  # pragma: no cover - process entrypoint
    run(app, DEFAULT_PORT)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
