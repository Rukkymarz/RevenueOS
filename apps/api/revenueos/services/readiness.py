"""Fail closed when the deployed database role can bypass tenant isolation."""
from sqlalchemy import text


def verify_database(engine, production=False):
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
        if not production:
            return
        if connection.dialect.name != "postgresql":
            raise RuntimeError("Production requires PostgreSQL")
        role = connection.execute(text("SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname=current_user")).one()
        if role.rolname != "revenueos_app" or role.rolsuper or role.rolbypassrls:
            raise RuntimeError("Unsafe runtime database role")
        tables = ('leads','contacts','clients','opportunities','tasks','campaigns','proposals','websites',
                  'media_jobs','approvals','message_drafts','audit_events','integration_events','knowledge',
                  'workflows','agent_memory','ai_runs')
        rows = connection.execute(text("""SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
            pg_get_userbyid(c.relowner) AS owner FROM pg_class c
            JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind='r'""")).all()
        safe = {row.relname for row in rows if row.relrowsecurity and row.relforcerowsecurity and row.owner != role.rolname}
        if not set(tables).issubset(safe):
            raise RuntimeError("Database migrations or tenant policies are missing")
        if connection.scalar(text("SELECT version_num FROM alembic_version")) != "0003":
            raise RuntimeError("Database migration version is not current")
