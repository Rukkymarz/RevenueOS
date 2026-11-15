"""revenueos-identity: the identity service, plus its operator commands.

  revenueos-identity                         serve HTTP (/health, /v1/info)
  revenueos-identity provision --name N --role R [--allow HOST ...] [--phone-carrier 46elks|twilio]
  revenueos-identity rotate-profile --agent-id ID
  revenueos-identity leads-signup --agent-id ID --task-id ID --service URL [--mode otp|magic-link]

Output is JSON without secret values.
"""
import argparse
import json
import os
import sys

from revenueos_common.service import run

from . import DEFAULT_PORT


def _vault():
    from revenueos_common.secrets import KeychainStore, SecretResolver
    return SecretResolver(KeychainStore(os.environ.get("REVENUEOS_KEYCHAIN_DIR", "/run/revenueos/keychain")))


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:  # pragma: no cover - process entrypoint
        from .app import app
        run(app, DEFAULT_PORT)
        return 0
    from revenueos_common.db import Database
    from . import leads, provision
    p = argparse.ArgumentParser(prog="revenueos-identity")
    sub = p.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("provision")
    pr.add_argument("--name", required=True)
    pr.add_argument("--role", required=True)
    pr.add_argument("--allow", action="append", default=[])
    pr.add_argument("--phone-carrier", choices=["46elks", "twilio"])
    rp = sub.add_parser("rotate-profile")
    rp.add_argument("--agent-id", required=True)
    ls = sub.add_parser("leads-signup")
    ls.add_argument("--agent-id", required=True)
    ls.add_argument("--task-id", required=True)
    ls.add_argument("--service", required=True)
    ls.add_argument("--mode", choices=["otp", "magic-link"], default="otp")
    a = p.parse_args(argv)
    db = Database(actor="identity-service")
    if a.cmd == "provision":
        out = provision.provision(db, _vault(), a.name, a.role, allow_hosts=a.allow, phone_carrier=a.phone_carrier)
        print(json.dumps(out.__dict__, indent=2))
        return 0
    if a.cmd == "rotate-profile":
        print(json.dumps({"agent_id": a.agent_id, "profile_path": provision.rotate_browser_profile(db, a.agent_id)}))
        return 0
    out = leads.leads_signup(db, a.agent_id, a.task_id, a.service, a.mode)
    print(json.dumps(out, indent=2))
    return 0 if out["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
