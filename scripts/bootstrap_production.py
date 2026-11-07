#!/usr/bin/env python3
"""Generate local, git-ignored single-node production bootstrap configuration."""
import argparse
import json
import os
from pathlib import Path
import re
import secrets

ROOT = Path(__file__).resolve().parents[1]


def domain(value: str) -> str:
    value = value.lower().strip()
    if not re.fullmatch(r"(?=.{4,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", value):
        raise argparse.ArgumentTypeError("Public DNS hostname required")
    if value.endswith(".example") or value.endswith(".test"):
        raise argparse.ArgumentTypeError("Choose a domain you control; reserved domains cannot receive TLS")
    return value


def build_realm(app_url: str) -> dict:
    realm = json.loads((ROOT / "infra/keycloak/revenueos-realm.json").read_text())
    realm["verifyEmail"] = True
    realm["sslRequired"] = "all"
    client = next(c for c in realm["clients"] if c["clientId"] == "revenueos-web")
    client["rootUrl"] = app_url
    client["redirectUris"] = [f"{app_url}/"]
    client["webOrigins"] = [app_url]
    client.pop("clientAuthenticatorType", None)  # public client with PKCE, no client secret
    realm["requiredActions"] = [
        {"alias": "CONFIGURE_TOTP", "name": "Configure OTP", "providerId": "CONFIGURE_TOTP", "enabled": True, "defaultAction": True},
        {"alias": "VERIFY_EMAIL", "name": "Verify Email", "providerId": "VERIFY_EMAIL", "enabled": True, "defaultAction": True},
    ]
    return realm


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-domain", type=domain, required=True)
    parser.add_argument("--auth-domain", type=domain, required=True)
    parser.add_argument("--admin-email", required=True)
    args = parser.parse_args()
    if args.app_domain == args.auth_domain:
        parser.error("Choose separate app and authentication hostnames")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", args.admin_email):
        parser.error("A valid administrator email is required")
    env_path = ROOT / ".env.production"
    realm_path = ROOT / "infra/keycloak/revenueos-production-realm.json"
    if env_path.exists() or realm_path.exists():
        parser.error("Existing configuration detected; never overwrite credentials automatically")
    env = {
        "APP_DOMAIN": args.app_domain,
        "AUTH_DOMAIN": args.auth_domain,
        "BOOTSTRAP_ADMIN_EMAIL": args.admin_email.lower(),
        "DB_ROOT_PASSWORD": secrets.token_hex(32),
        "APP_DB_PASSWORD": secrets.token_hex(32),
        "KEYCLOAK_DB_PASSWORD": secrets.token_hex(32),
        "KEYCLOAK_ADMIN_PASSWORD": secrets.token_hex(32),
        "METRICS_TOKEN": secrets.token_hex(32),
        "UNSUBSCRIBE_SECRET": secrets.token_hex(32),
        "RESEND_API_KEY": "",
        "RESEND_FROM": "",
        "OUTREACH_POSTAL_ADDRESS": "",
        "AI_ENABLED": "false",
    }
    # File mode 0600 from creation; never print or commit values.
    fd = os.open(env_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as file:
        file.write("\n".join(f"{k}={v}" for k, v in env.items()) + "\n")
    realm_path.write_text(json.dumps(build_realm(f"https://{args.app_domain}"), indent=2) + "\n")
    print("Private production environment and realm files created. Review deployment guide before running Compose.")


if __name__ == "__main__":
    main()
