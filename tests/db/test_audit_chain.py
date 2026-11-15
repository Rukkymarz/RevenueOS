"""Audit ledger: append-only, hash-chained, serialized, tamper-evident (spec 1.6/1.7)."""
import subprocess
import concurrent.futures as cf

import pytest

from dbkit import H, H2, HOST, PORT, USER, SqlError, advance_to_verifying, add_verification


class TestAuditChain:
    def test_forged_hash_is_overwritten(self, db, world):
        db.q("INSERT INTO audit_log(seq, prev_hash, hash, actor, action, target) "
             "VALUES (999,'forged','forged','x','y','z')")
        assert db.one("SELECT count(*) FROM audit_log WHERE hash='forged' OR seq=999") == "0"
        assert db.one("SELECT audit_verify() IS NULL") == "t"

    def test_update_delete_truncate_forbidden(self, db, world):
        db.rejects("UPDATE audit_log SET actor='evil'", "append-only")
        db.rejects("DELETE FROM audit_log", "append-only")
        db.rejects("TRUNCATE audit_log", "append-only")

    def test_tampering_is_detected(self, db, world):
        # Superuser bypasses the trigger; verification must still catch it.
        seq = db.one("SELECT max(seq) FROM audit_log")
        db.q("ALTER TABLE audit_log DISABLE TRIGGER trg_audit_append_only; "
             f"UPDATE audit_log SET actor='evil' WHERE seq={seq}; "
             "ALTER TABLE audit_log ENABLE TRIGGER trg_audit_append_only")
        assert db.one("SELECT audit_verify()") == seq

    def test_concurrent_writers_do_not_fork_chain(self, db, world):
        def writer(i):
            sql = "".join(f"SELECT audit_append('w{i}','load','t{j}','{{}}'::jsonb);" for j in range(100))
            return subprocess.run(["psql", "-h", HOST, "-p", PORT, "-U", USER, "-d", db.name,
                                   "-v", "ON_ERROR_STOP=1", "-X", "-q", "-c", sql],
                                  capture_output=True, text=True).returncode
        with cf.ThreadPoolExecutor(4) as ex:
            assert list(ex.map(writer, range(4))) == [0, 0, 0, 0]
        assert db.one("SELECT max(seq) = count(*) FROM audit_log") == "t"
        assert db.one("SELECT audit_verify() IS NULL") == "t"
