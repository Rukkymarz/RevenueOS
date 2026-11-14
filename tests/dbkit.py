"""Database test kit (imported by tests/conftest.py): every test gets a fresh database cloned from a migrated template.

Talks to a real Postgres 16 through psql so the triggers and constraints under
test are the production ones. Configure with REVENUEOS_PG_HOST / _PORT / _USER.
"""
import os
import subprocess
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = sorted((ROOT / "db" / "migrations").glob("*.sql"))
HOST = os.environ.get("REVENUEOS_PG_HOST", "/tmp/pgsock")
PORT = os.environ.get("REVENUEOS_PG_PORT", "5433")
USER = os.environ.get("REVENUEOS_PG_USER", "postgres")
TEMPLATE = "revenueos_tpl"


class SqlError(Exception):
    pass


def _psql(db, sql=None, file=None, check=True):
    cmd = ["psql", "-h", HOST, "-p", PORT, "-U", USER, "-d", db,
           "-v", "ON_ERROR_STOP=1", "-X", "-q", "-A", "-t"]
    cmd += ["-f", str(file)] if file else ["-c", sql]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise SqlError(r.stderr.strip())
    return r


@pytest.fixture(scope="session")
def template_db():
    _psql("postgres", f"DROP DATABASE IF EXISTS {TEMPLATE}")
    _psql("postgres", f"CREATE DATABASE {TEMPLATE}")
    for m in MIGRATIONS:
        _psql(TEMPLATE, file=m)
    yield TEMPLATE


class DB:
    def __init__(self, name):
        self.name = name

    def q(self, sql):
        """Run SQL; return list of rows (pipe-separated strings)."""
        out = _psql(self.name, sql).stdout.strip()
        return [line for line in out.splitlines() if line]

    def one(self, sql):
        rows = self.q(sql)
        return rows[0] if rows else None

    def rejects(self, sql, match):
        """Assert the database rejects sql with an error containing match."""
        with pytest.raises(SqlError) as e:
            self.q(sql)
        assert match in str(e.value), f"expected {match!r}, got {e.value!r}"
        return str(e.value)


@pytest.fixture
def db(template_db):
    name = "t_" + uuid.uuid4().hex[:12]
    _psql("postgres", f"CREATE DATABASE {name} TEMPLATE {template_db}")
    yield DB(name)
    _psql("postgres", f"DROP DATABASE {name} WITH (FORCE)", check=False)


H = "a" * 64   # a valid sha256-shaped hex digest
H2 = "b" * 64


@pytest.fixture
def world(db):
    """Two agents, a research run with a labeled premise, and one DRAFT task."""
    w = {}
    w["exec"] = db.one("INSERT INTO agents(name, role, framework, budget_monthly) "
                       "VALUES ('executor','coder','langgraph',100) RETURNING id")
    w["ver"] = db.one("INSERT INTO agents(name, role, framework, budget_monthly) "
                      "VALUES ('verifier','qc','langgraph',100) RETURNING id")
    rr = db.one("INSERT INTO research_runs(target, pack) VALUES ('acme','local-services') RETURNING id")
    w["premise"] = db.one(
        "INSERT INTO premise_bundles(research_run_id, claims, missing_data) VALUES "
        f"('{rr}', '[{{\"text\":\"x\",\"label\":\"verified\",\"source_ids\":[\"s1\"]}}]', '[]') RETURNING id")
    w["task"] = db.one(
        "INSERT INTO tasks(objective, task_class, acceptance_criteria) "
        "VALUES ('ship it','code','[{\"check\":\"tests_pass\"}]') RETURNING id")
    return w


def advance_to_verifying(db, w, tier="L3"):
    t = w["task"]
    db.q(f"UPDATE tasks SET premise_bundle_id='{w['premise']}', state='RESEARCHED' WHERE id='{t}'")
    db.q(f"UPDATE tasks SET state='PLANNED' WHERE id='{t}'")
    db.q(f"UPDATE tasks SET state='AWAITING_APPROVAL' WHERE id='{t}'")
    db.q(f"UPDATE tasks SET executor_agent_id='{w['exec']}', state='EXECUTING' WHERE id='{t}'")
    db.q(f"INSERT INTO evidence(task_id, kind, uri, hash, oracle_tier, produced_by) "
         f"VALUES ('{t}','test-report','s3://e/1','{H}','{tier}','ci')")
    db.q(f"UPDATE tasks SET state='EVIDENCE_SUBMITTED' WHERE id='{t}'")
    db.q(f"UPDATE tasks SET verifier_agent_id='{w['ver']}', state='VERIFYING' WHERE id='{t}'")


def add_verification(db, w, verdict="PASS", method_class="deterministic", tier="L3", verifier=None):
    v = verifier or w["ver"]
    return db.one(
        "INSERT INTO verifications(task_id, verifier_agent_id, method, method_class, verdict, tier) "
        f"VALUES ('{w['task']}','{v}','gitreins','{method_class}','{verdict}','{tier}') RETURNING id")
