#!/usr/bin/env python3
"""CI-only PostgreSQL migration/row-security smoke test.

Requires isolated, disposable PostgreSQL 16+ with pgvector installed and env
CI_POSTGRES_ADMIN_URL, CI_POSTGRES_APP_URL. NEVER point at production data.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.exc import DBAPIError

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "apps/api"


def main() -> int:
    if os.getenv("CI") != "true" or os.getenv("REVENUEOS_EPHEMERAL_DATABASE") != "true":
        raise SystemExit("CI-only isolated database check; requires CI=true and REVENUEOS_EPHEMERAL_DATABASE=true")
    admin_url = os.environ["CI_POSTGRES_ADMIN_URL"]
    app_url = os.environ["CI_POSTGRES_APP_URL"]
    if "localhost" not in admin_url and "127.0.0.1" not in admin_url:
        raise SystemExit("Refusing RLS test on a non-local admin database")
    if "localhost" not in app_url and "127.0.0.1" not in app_url:
        raise SystemExit("Refusing RLS test on a non-local application database")
    from sqlalchemy.engine import make_url
    admin_host, app_host = make_url(admin_url).host, make_url(app_url).host
    if admin_host not in ("localhost", "127.0.0.1") or app_host not in ("localhost", "127.0.0.1"):
        raise SystemExit("Non-local database host is forbidden")
    from revenueos.models import Business, Lead, Membership

    admin = create_engine(admin_url)
    app = create_engine(app_url)
    with admin.begin() as conn:
        # This can run only against the disposable CI database provisioned by Actions.
        conn.execute(text("CREATE ROLE revenueos_app LOGIN PASSWORD 'revenueos-ci-app-password' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS"))
        conn.execute(text("GRANT CONNECT ON DATABASE revenueos TO revenueos_app"))
    env = dict(os.environ)
    env["DATABASE_URL"] = admin_url
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=API, env=env, check=True)

    tenants = [str(uuid4()), str(uuid4())]
    try:
        with Session(admin) as db:
            for i, tenant in enumerate(tenants):
                db.add(Business(id=tenant, name=f"ci-rls-{i}"))
                db.add(Lead(business_id=tenant, business_name=f"ci-lead-{i}"))
            db.add(Membership(business_id=tenants[0], subject="ci-owner", email="ci@example.org", role="admin"))
            db.commit()

        with app.connect() as conn:
            with conn.begin():
                # The application role cannot see tenant-owned records before setting scope.
                assert conn.scalar(text("SELECT count(*) FROM leads")) == 0
                conn.execute(text("SELECT set_config('app.business_id', :tenant, true)"), {"tenant": tenants[0]})
                assert conn.scalar(text("SELECT count(*) FROM leads")) == 1
                assert conn.scalar(text("SELECT business_name FROM leads")) == "ci-lead-0"
                # The row-security policy must reject cross-tenant inserts, not just filters.
                try:
                    with conn.begin_nested():
                        conn.execute(text("INSERT INTO leads (id,business_id,business_name,industry,stage,source,metrics,grade,score_confidence,opted_out,created_at) VALUES (:id,:business_id,'blocked','other','new','manual','{}'::json,'Unscored',0,false,now())"),
                                     {"id": str(uuid4()), "business_id": tenants[1]})
                except DBAPIError:
                    pass
                else:
                    raise AssertionError("Cross-tenant INSERT was permitted")
            with conn.begin():
                # Transaction-local session setting must not leak across commits.
                assert conn.scalar(text("SELECT count(*) FROM leads")) == 0
                conn.execute(text("SELECT set_config('app.business_id', :tenant, true)"), {"tenant": tenants[1]})
                assert conn.scalar(text("SELECT business_name FROM leads")) == "ci-lead-1"
        with admin.connect() as conn:
            policy_count = conn.scalar(text("""SELECT count(*) FROM pg_class
                WHERE relname IN ('leads','contacts','clients','opportunities','tasks','campaigns',
                'proposals','websites','media_jobs','approvals','message_drafts','audit_events',
                'integration_events','knowledge','workflows','agent_memory','ai_runs')
                AND relrowsecurity AND relforcerowsecurity"""))
            assert policy_count == 17, f"Expected RLS FORCE on 17 tables, found {policy_count}"
        from revenueos.services.readiness import verify_database
        verify_database(app, production=True)
        # Exercise the real API transaction and membership dependencies under
        # the unprivileged runtime role, rather than SQLite's permissive model.
        from fastapi.testclient import TestClient
        from revenueos.main import app as api
        from revenueos.db import get_db
        from revenueos.security import authenticate, Principal
        def session():
            with Session(app, expire_on_commit=False) as db:
                yield db
        api.dependency_overrides[get_db] = session
        api.dependency_overrides[authenticate] = lambda: Principal("ci-owner", "ci@example.org", True)
        try:
            with TestClient(api) as client:
                headers = {"X-Business-Id": tenants[0]}
                assert client.get("/api/v1/leads", headers={"X-Business-Id": tenants[1]}).status_code == 403
                created = client.post("/api/v1/leads", headers=headers, json={"business_name": "CI transaction probe"})
                assert created.status_code == 201, created.text
                id_ = created.json()["id"]
                updated = client.patch(f"/api/v1/leads/{id_}", headers=headers, json={"stage": "qualified"})
                assert updated.status_code == 200 and updated.json()["stage"] == "qualified", updated.text
                task = client.post("/api/v1/tasks", headers=headers, json={"title": "CI task", "lead_id": id_})
                assert task.status_code == 201, task.text
                assert client.patch(f"/api/v1/tasks/{task.json()['id']}", headers=headers, json={"status": "done"}).status_code == 200
                assert client.get("/api/v1/audit-events", headers=headers).status_code == 200
        finally:
            api.dependency_overrides.clear()
        print("PASS: PostgreSQL migrations, non-superuser privileges, tenant RLS and transaction reset")
        return 0
    finally:
        with Session(admin) as db:
            from revenueos.db import Base
            for table in reversed(Base.metadata.sorted_tables):
                if "business_id" in table.c:
                    db.execute(table.delete().where(table.c.business_id.in_(tenants)))
            db.query(Business).filter(Business.id.in_(tenants)).delete(synchronize_session=False)
            db.commit()
        app.dispose()
        admin.dispose()


if __name__ == "__main__":
    sys.exit(main())
