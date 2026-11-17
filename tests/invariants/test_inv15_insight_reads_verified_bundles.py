"""INV-15: every task carries its evidence bundle; insight queries read only verified bundles."""
import subprocess
import concurrent.futures as cf

import pytest

from dbkit import H, H2, HOST, PORT, USER, SqlError, advance_to_verifying, add_verification


class TestINV15InsightReadsVerifiedOnly:
    def test_insight_role_cannot_read_unverified_tables(self, db, world):
        db.rejects("SET ROLE revenueos_insight; SELECT count(*) FROM tasks", "permission denied")
        assert db.one("SET ROLE revenueos_insight; SELECT count(*) FROM v_verified_tasks") == "0"

    def test_verified_views_exclude_unfinished_tasks(self, db, world):
        advance_to_verifying(db, world)
        assert db.one("SELECT count(*) FROM v_verified_evidence") == "0"
        v = add_verification(db, world)
        db.q(f"UPDATE tasks SET verification_id='{v}', state='QC_PASSED' WHERE id='{world['task']}'")
        assert db.one("SELECT count(*) FROM v_verified_tasks") == "0"
        db.q(f"UPDATE tasks SET state='COMPLETED' WHERE id='{world['task']}'")
        assert db.one("SELECT count(*) FROM v_verified_tasks") == "1"
        assert db.one("SELECT count(*) FROM v_verified_evidence") == "1"
