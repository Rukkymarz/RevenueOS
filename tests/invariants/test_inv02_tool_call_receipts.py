"""INV-02: every tool call produces an immutable receipt."""
import subprocess
import concurrent.futures as cf

import pytest

from dbkit import H, H2, HOST, PORT, USER, SqlError, advance_to_verifying, add_verification


class TestINV02Receipts:
    def _call(self, db, w, risk="low", approval="NULL", args=H):
        return db.one(
            "INSERT INTO tool_calls(task_id, agent_id, mcp_server, tool, args_hash, args_redacted, "
            "result_hash, latency_ms, cost, risk_class, approval_id, verdict) VALUES "
            f"('{w['task']}','{w['exec']}','scraper','fetch','{args}','{{}}','{H2}',12,0.001,'{risk}',"
            f"{approval},'ok') RETURNING id")

    def test_receipt_is_immutable(self, db, world):
        c = self._call(db, world)
        db.rejects(f"UPDATE tool_calls SET cost=0 WHERE id='{c}'", "append-only")
        db.rejects(f"DELETE FROM tool_calls WHERE id='{c}'", "append-only")

    def test_receipt_requires_hashes_and_cost(self, db, world):
        db.rejects("INSERT INTO tool_calls(task_id, agent_id, mcp_server, tool, args_redacted, latency_ms, "
                   f"cost, risk_class, verdict) VALUES ('{world['task']}','{world['exec']}','s','t','{{}}',1,0,'low','ok')",
                   "args_hash")
        db.rejects("INSERT INTO tool_calls(task_id, agent_id, mcp_server, tool, args_hash, args_redacted, "
                   f"latency_ms, cost, risk_class, verdict) VALUES ('{world['task']}','{world['exec']}','s','t',"
                   "'not-a-hash','{}',1,0,'low','ok')", "args_hash_check")

    def test_receipt_writes_audit_entry(self, db, world):
        c = self._call(db, world)
        assert db.one(f"SELECT count(*) FROM audit_log WHERE action='tool.call' "
                      f"AND payload->>'tool_call_id'='{c}'") == "1"


# ---------------------------------------------------------------- INV-03
