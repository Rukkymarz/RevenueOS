"""INV-06: high/critical tool calls need a hash-bound, expiring, single-use human approval."""
import subprocess
import concurrent.futures as cf

import pytest

from dbkit import H, H2, HOST, PORT, USER, SqlError, advance_to_verifying, add_verification


class TestINV06Approvals:
    def _approval(self, db, w, args=H, expires="now() + interval '10 minutes'", by="'owner'"):
        return db.one("INSERT INTO approvals(task_id, tool_call_args_hash, requested_by, approved_by, expires_at, status) "
                      f"VALUES ('{w['task']}','{args}','agent:exec',{by},{expires},'approved') RETURNING id")

    def _high_call(self, db, w, approval, args=H):
        return db.q("INSERT INTO tool_calls(task_id, agent_id, mcp_server, tool, args_hash, args_redacted, "
                    f"latency_ms, cost, risk_class, approval_id, verdict) VALUES ('{w['task']}','{w['exec']}',"
                    f"'outreach','send','{args}','{{}}',5,0,'high',{approval},'ok')")

    def test_high_risk_without_approval_rejected(self, db, world):
        db.rejects(self._sql_no_approval(world), "INV-06")

    def _sql_no_approval(self, w):
        return ("INSERT INTO tool_calls(task_id, agent_id, mcp_server, tool, args_hash, args_redacted, "
                f"latency_ms, cost, risk_class, verdict) VALUES ('{w['task']}','{w['exec']}','outreach','send',"
                f"'{H}','{{}}',5,0,'critical','ok')")

    def test_consumed_approval_allows_exactly_one_call(self, db, world):
        a = self._approval(db, world)
        assert db.one(f"SELECT consume_approval('{a}','{H}')") == "t"
        self._high_call(db, world, f"'{a}'")
        assert db.one(f"SELECT consume_approval('{a}','{H}')") == "f"      # single use
        db.rejects(self._sql_reuse(world, a), "INV-06")

    def _sql_reuse(self, w, a):
        return ("INSERT INTO tool_calls(task_id, agent_id, mcp_server, tool, args_hash, args_redacted, "
                f"latency_ms, cost, risk_class, approval_id, verdict) VALUES ('{w['task']}','{w['exec']}',"
                f"'outreach','send','{H}','{{}}',5,0,'high','{a}','ok')")

    def test_mutated_arguments_rejected(self, db, world):
        a = self._approval(db, world)
        assert db.one(f"SELECT consume_approval('{a}','{H2}')") == "f"

    def test_expired_approval_rejected(self, db, world):
        a = self._approval(db, world, expires="now() - interval '1 second'")
        assert db.one(f"SELECT consume_approval('{a}','{H}')") == "f"

    def test_self_approval_rejected(self, db, world):
        db.rejects("INSERT INTO approvals(task_id, tool_call_args_hash, requested_by, approved_by, expires_at, status) "
                   f"VALUES ('{world['task']}','{H}','alice','alice',now()+interval '1 hour','approved')",
                   "approvals_check")


# ---------------------------------------------------------------- INV-14 / INV-15 storage halves
