#!/usr/bin/env python3
"""Offline, non-secret-leaking RevenueOS release preflight.

Checks the *source package*. Live infrastructure is a separate release gate.
Exit status 1 means the package must not be described as build-ready.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def check_release(root: Path) -> dict:
    checks: list[dict[str, str | bool]] = []

    def add(name: str, passed: bool, message: str) -> None:
        checks.append({"name": name, "passed": passed, "detail": message})

    package = root / "apps/web/package.json"
    lock = root / "apps/web/package-lock.json"
    manifest = json.loads(package.read_text()) if package.exists() else {}
    add("web_package", bool(manifest.get("dependencies", {}).get("next")),
        "Next.js application manifest present" if manifest else "Missing Next.js package manifest")
    add("web_lockfile", lock.is_file() and lock.stat().st_size > 1000 if lock.exists() else False,
        "Dependency lockfile present" if lock.is_file() else
        "Generate a genuine lockfile with: cd apps/web && npm install --package-lock-only")
    add("production_compose", (root / "compose.prod.yaml").is_file(),
        "Single-host production recipe is available; Render uses a different service topology")
    prod_compose = (root / "compose.prod.yaml").read_text() if (root / "compose.prod.yaml").exists() else ""
    add("production_auth", 'command: ["start",' in prod_compose and "start-dev" not in prod_compose,
        "Keycloak configured for production mode" if 'command: ["start",' in prod_compose else "Review Keycloak start mode")
    add("production_redis", "REDIS_URL: redis://redis:6379/0" in prod_compose,
        "Redis wired to the production API" if "REDIS_URL: redis://redis:6379/0" in prod_compose else "Missing Redis integration")
    add("api_migrations", (root / "apps/api/alembic/versions/0003_approval_review_hash.py").exists(),
        "Database migrations present" if (root / "apps/api/alembic/versions/0003_approval_review_hash.py").exists() else "Missing migration")
    add("postgres_rls_ci", (root / "scripts/test_postgres_rls.py").is_file(),
        "RLS test harness present (must pass in CI against PostgreSQL)")
    add("license", (root / "LICENSE").is_file() and "MIT" in (root / "LICENSE").read_text(),
        "MIT source license present")
    exposed = [str(p.relative_to(root)) for p in root.rglob(".env.production")]
    add("no_bundled_prod_secrets", not exposed, "No private production environment bundled" if not exposed else "Remove private .env.production files")
    legacy = [
        root / "apps/api/revenueos/config.py", root / "apps/api/revenueos/routers/workflows.py",
        root / "apps/api/revenueos/plugins/registry.py", root / "compose.prod.yaml",
    ]
    forbidden = ("QUOTE_WEBHOOK_SECRET", "QUOTE_INTEGRATION_BUSINESS_ID", '/integrations/quotes/events', 'cleaning_quote')
    leftovers = [str(p.relative_to(root)) for p in legacy if p.is_file() and any(term in p.read_text() for term in forbidden)]
    add("standalone_isolation", not leftovers and (root / "docs/STANDALONE_DEPLOYMENT.md").exists(),
        "No legacy CRM integration in service/config source" if not leftovers else "Legacy integration remains: " + ", ".join(leftovers))
    # Deployment evidence cannot be determined offline. Never call an unbuilt package production ready.
    results = {
        "checks": checks,
        "source_preflight_passed": all(x["passed"] for x in checks),
        "live_gates_required": [
            "Frontend npm ci, lint, typecheck and build",
            "PostgreSQL migration and RLS smoke test",
            "Keycloak OIDC + enforced MFA browser test",
            "Hosted HTTPS URL, backups, restore drill and alerts",
            "Approved production hosting budget, secrets and provider integration tests",
        ],
    }
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true", help="Print machine-readable status without secrets")
    args = parser.parse_args()
    result = check_release(args.root.resolve())
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        for c in result["checks"]:
            symbol = "PASS" if c["passed"] else "BLOCKED"
            print(f"[{symbol}] {c['name']}: {c['detail']}")
        print("SOURCE PRE-FLIGHT:", "PASS" if result["source_preflight_passed"] else "BLOCKED")
        print("LIVE RELEASE GATES: unverified (see docs/RENDER_CONNECTOR_HANDOFF.md)")
    return 0 if result["source_preflight_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
