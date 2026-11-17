"""Phase 2 database guards: approval decisions and logged consumption (INV-06), sandbox commit
boundary (INV-12), append-only egress log (INV-11)."""
from dbkit import H, H2


def _approval(db, world, *, requested_by="agent:exec", expires="now() + interval '10 minutes'"):
    return db.one(f"INSERT INTO approvals(task_id, tool_call_args_hash, requested_by, expires_at) "
                  f"VALUES ('{world['task']}','{H}','{requested_by}',{expires}) RETURNING id")


def _reasons(db, approval):
    return db.q(f"SELECT payload->>'reason' FROM audit_log WHERE target='{approval}' "
                f"AND action LIKE 'approval.%rejected' ORDER BY seq")


class TestApprovalDecide:
    def test_requester_cannot_approve_and_attempt_is_audited(self, db, world):
        a = _approval(db, world)
        db.rejects(f"SELECT approval_decide('{a}','agent:exec',true)", "separation of duties")
        assert any("separation of duties" in r for r in _reasons(db, a))

    def test_single_decision(self, db, world):
        a = _approval(db, world)
        assert db.one(f"SELECT approval_decide('{a}','human:christine',true)") == "approved"
        db.rejects(f"SELECT approval_decide('{a}','human:other',false)", "already approved")

    def test_expired_request_cannot_be_decided(self, db, world):
        a = _approval(db, world, expires="now() - interval '1 second'")
        db.rejects(f"SELECT approval_decide('{a}','human:christine',true)", "expired")
        assert db.one("SELECT approval_expire_sweep()") == "1"


class TestApprovalConsume:
    def _approved(self, db, world, **kw):
        a = _approval(db, world, **kw)
        db.q(f"SELECT approval_decide('{a}','human:christine',true)")
        return a

    def test_exact_hash_consumes_once_then_reuse_is_rejected_with_reason(self, db, world):
        a = self._approved(db, world)
        assert db.one(f"SELECT consume_approval('{a}','{H}')") == "t"
        assert db.one(f"SELECT consume_approval('{a}','{H}')") == "f"
        assert _reasons(db, a)[-1] == "reuse: already used"

    def test_hash_mismatch_is_rejected_with_reason(self, db, world):
        a = self._approved(db, world)
        assert db.one(f"SELECT consume_approval('{a}','{H2}')") == "f"
        assert _reasons(db, a)[-1] == "args hash mismatch"
        assert db.one(f"SELECT status FROM approvals WHERE id='{a}'") == "approved"

    def test_expired_approval_is_rejected_with_reason(self, db, world):
        a = self._approved(db, world)
        db.q(f"ALTER TABLE approvals DISABLE TRIGGER USER; UPDATE approvals SET expires_at = now() - interval '1 s' "
             f"WHERE id='{a}'; ALTER TABLE approvals ENABLE TRIGGER USER")
        assert db.one(f"SELECT consume_approval('{a}','{H}')") == "f"
        assert _reasons(db, a)[-1] == "expired"

    def test_pending_approval_cannot_be_consumed(self, db, world):
        a = _approval(db, world)
        assert db.one(f"SELECT consume_approval('{a}','{H}')") == "f"
        assert _reasons(db, a)[-1] == "not approved (pending)"


class TestSandboxCommitBoundary:
    def _session(self, db, world, status="finished"):
        return db.one(f"INSERT INTO sandbox_sessions(agent_id, backend, workspace, shadow_path, command_hash, status) "
                      f"VALUES ('{world['exec']}','bubblewrap','/w','/s','{H}','{status}') RETURNING id")

    def test_commit_without_consumed_approval_is_refused(self, db, world):
        s = self._session(db, world)
        a = _approval(db, world)
        db.rejects(f"UPDATE sandbox_sessions SET status='committed', approval_id='{a}', changeset_hash='{H}' WHERE id='{s}'",
                   "consumed approval bound to its changeset")

    def test_commit_with_approval_bound_to_changeset_succeeds(self, db, world):
        s = self._session(db, world)
        a = _approval(db, world)
        db.q(f"SELECT approval_decide('{a}','human:christine',true)")
        assert db.one(f"SELECT consume_approval('{a}','{H}')") == "t"
        db.q(f"UPDATE sandbox_sessions SET status='committed', approval_id='{a}', changeset_hash='{H}' WHERE id='{s}'")
        db.rejects(f"UPDATE sandbox_sessions SET status='discarded' WHERE id='{s}'", "session is closed")

    def test_blocked_session_cannot_be_committed(self, db, world):
        s = self._session(db, world, status="blocked")
        db.rejects(f"UPDATE sandbox_sessions SET status='finished' WHERE id='{s}'", "session is closed")


class TestEgressLog:
    def test_egress_log_is_append_only_and_audited(self, db, world):
        e = db.one(f"INSERT INTO egress_log(agent_id, method, host, path_hash, decision, reason) "
                   f"VALUES ('{world['exec']}','GET','exfil.example:443','{H}','deny','not allowlisted') RETURNING id")
        db.rejects(f"UPDATE egress_log SET decision='allow' WHERE id='{e}'", "append-only")
        db.rejects(f"DELETE FROM egress_log WHERE id='{e}'", "append-only")
        assert db.one(f"SELECT count(*) FROM audit_log WHERE action='egress.deny' AND payload->>'egress_id'='{e}'") == "1"

    def test_rules_reject_wildcards_and_paths(self, db, world):
        db.rejects(f"INSERT INTO egress_rules(agent_id, host, created_by) VALUES ('{world['exec']}','*.example.com','t')",
                   "egress_rules_host_check")
        db.rejects(f"INSERT INTO egress_rules(agent_id, host, created_by) VALUES ('{world['exec']}','a.com/x','t')",
                   "egress_rules_host_check")


class TestApprovalBinding:
    def _approved_for(self, db, world, tool):
        a = db.one(f"INSERT INTO approvals(task_id, tool_call_args_hash, requested_by, expires_at, tool) "
                   f"VALUES ('{world['task']}','{H}','agent:exec',now() + interval '5 minutes','{tool}') RETURNING id")
        db.q(f"SELECT approval_decide('{a}','human:christine',true)")
        return a

    def test_approval_cannot_be_spent_on_another_tool(self, db, world):
        a = self._approved_for(db, world, "mail_send")
        assert db.one(f"SELECT consume_approval('{a}','{H}','{world['task']}','mail_trash')") == "f"
        assert _reasons(db, a)[-1] == "bound to a different tool"
        assert db.one(f"SELECT consume_approval('{a}','{H}','{world['task']}','mail_send')") == "t"

    def test_approval_cannot_be_spent_on_another_task(self, db, world):
        a = self._approved_for(db, world, "mail_send")
        other = db.one("INSERT INTO tasks(objective, task_class, acceptance_criteria) "
                       "VALUES ('other','code','[{\"check\":\"x\"}]') RETURNING id")
        assert db.one(f"SELECT consume_approval('{a}','{H}','{other}','mail_send')") == "f"
        assert _reasons(db, a)[-1] == "bound to a different task"
