"""db/duckdb mirror schema loads in DuckDB and its insight views read verified tasks only (INV-15)."""
from pathlib import Path

import pytest

duckdb = pytest.importorskip("duckdb")
SCHEMA = Path(__file__).resolve().parents[2] / "db" / "duckdb" / "0001_mirror.sql"


def test_mirror_schema_and_verified_only_views():
    con = duckdb.connect()
    con.execute(SCHEMA.read_text())
    con.execute(SCHEMA.read_text())  # idempotent
    con.execute("""INSERT INTO mirror.tasks VALUES
      ('00000000-0000-0000-0000-000000000001', NULL, NULL, 'done', 'code', 'COMPLETED', NULL, NULL,
       '00000000-0000-0000-0000-0000000000a1', 'L3', 1, 4.5, now(), now(), now()),
      ('00000000-0000-0000-0000-000000000002', NULL, NULL, 'open', 'code', 'EXECUTING', NULL, NULL,
       NULL, 'L3', 1, 9.0, now(), NULL, now())""")
    con.execute("""INSERT INTO mirror.verifications VALUES
      ('00000000-0000-0000-0000-0000000000a1', '00000000-0000-0000-0000-000000000001',
       '00000000-0000-0000-0000-0000000000f1', 'gitreins', 'deterministic', 'PASS', 'L3', now())""")
    assert con.execute("SELECT count(*) FROM mirror.v_verified_tasks").fetchone()[0] == 1
    assert float(con.execute("SELECT cost_per_outcome FROM mirror.v_cost_per_verified_outcome").fetchone()[0]) == 4.5
