"""INV-01: task completion requires a QC_PASSED verification record, enforced in the database."""
import subprocess
import concurrent.futures as cf

import pytest

from dbkit import H, H2, HOST, PORT, USER, SqlError, advance_to_verifying, add_verification


class TestINV01CompletionRequiresVerification:
    def test_direct_jump_to_completed_rejected(self, db, world):
        db.rejects(f"UPDATE tasks SET state='COMPLETED' WHERE id='{world['task']}'",
                   "illegal transition DRAFT -> COMPLETED")

    def test_task_cannot_be_born_completed(self, db, world):
        db.rejects("INSERT INTO tasks(objective, task_class, state) VALUES ('x','code','COMPLETED')",
                   "created in DRAFT")

    def test_qc_passed_with_failed_verification_rejected(self, db, world):
        advance_to_verifying(db, world)
        v = add_verification(db, world, verdict="FAIL")
        db.rejects(f"UPDATE tasks SET verification_id='{v}', state='QC_PASSED' WHERE id='{world['task']}'",
                   "INV-01/INV-04")

    def test_qc_passed_below_required_tier_rejected(self, db, world):
        advance_to_verifying(db, world)
        db.q(f"UPDATE tasks SET verification_id=NULL WHERE id='{world['task']}'")
        v = add_verification(db, world, tier="L1")
        db.rejects(f"UPDATE tasks SET verification_id='{v}', state='QC_PASSED' WHERE id='{world['task']}'",
                   "tier >= L2")

    def test_verification_from_another_task_rejected(self, db, world):
        advance_to_verifying(db, world)
        other = db.one(f"INSERT INTO tasks(objective, task_class) VALUES ('other','code') RETURNING id")
        db.q(f"UPDATE tasks SET premise_bundle_id='{world['premise']}', state='RESEARCHED' WHERE id='{other}'")
        db.q(f"UPDATE tasks SET acceptance_criteria='[1]', state='PLANNED' WHERE id='{other}'")
        db.q(f"UPDATE tasks SET state='AWAITING_APPROVAL' WHERE id='{other}'")
        db.q(f"UPDATE tasks SET executor_agent_id='{world['exec']}', state='EXECUTING' WHERE id='{other}'")
        foreign = db.one(
            "INSERT INTO verifications(task_id, verifier_agent_id, method, method_class, verdict, tier) "
            f"VALUES ('{other}','{world['ver']}','gitreins','deterministic','PASS','L4') RETURNING id")
        db.rejects(f"UPDATE tasks SET verification_id='{foreign}', state='QC_PASSED' WHERE id='{world['task']}'",
                   "INV-01")

    def test_skipping_qc_passed_rejected(self, db, world):
        advance_to_verifying(db, world)
        v = add_verification(db, world)
        db.rejects(f"UPDATE tasks SET verification_id='{v}', state='COMPLETED' WHERE id='{world['task']}'",
                   "illegal transition VERIFYING -> COMPLETED")

    def test_completed_at_cannot_be_forged(self, db, world):
        db.rejects(f"UPDATE tasks SET completed_at=now() WHERE id='{world['task']}'", "completed_at")

    def test_happy_path_completes_and_is_audited(self, db, world):
        advance_to_verifying(db, world)
        v = add_verification(db, world)
        db.q(f"UPDATE tasks SET verification_id='{v}', state='QC_PASSED' WHERE id='{world['task']}'")
        db.q(f"UPDATE tasks SET state='COMPLETED' WHERE id='{world['task']}'")
        assert db.one(f"SELECT state FROM tasks WHERE id='{world['task']}'") == "COMPLETED"
        assert db.one(f"SELECT completed_at IS NOT NULL FROM tasks WHERE id='{world['task']}'") == "t"
        n = int(db.one(f"SELECT count(*) FROM task_events WHERE task_id='{world['task']}' AND event_type='transition'"))
        assert n == 8
        assert db.one("SELECT audit_verify() IS NULL") == "t"   # NULL => chain intact

    def test_completed_is_terminal(self, db, world):
        self.test_happy_path_completes_and_is_audited(db, world)
        db.rejects(f"UPDATE tasks SET state='EXECUTING' WHERE id='{world['task']}'", "terminal")


# ---------------------------------------------------------------- INV-02


class TestStateMachine:
    def test_skip_rejected(self, db, world):
        db.rejects(f"UPDATE tasks SET state='EXECUTING' WHERE id='{world['task']}'", "illegal transition")

    def test_research_requires_premise(self, db, world):
        db.rejects(f"UPDATE tasks SET state='RESEARCHED' WHERE id='{world['task']}'", "premise bundle required")

    def test_plan_requires_acceptance_criteria(self, db, world):
        t = db.one("INSERT INTO tasks(objective, task_class) VALUES ('x','code') RETURNING id")
        db.q(f"UPDATE tasks SET premise_bundle_id='{world['premise']}', state='RESEARCHED' WHERE id='{t}'")
        db.rejects(f"UPDATE tasks SET state='PLANNED' WHERE id='{t}'", "acceptance criteria")

    def test_evidence_tier_enforced(self, db, world):
        t = world["task"]
        db.q(f"UPDATE tasks SET premise_bundle_id='{world['premise']}', required_oracle_tier='L4', state='RESEARCHED' WHERE id='{t}'")
        db.q(f"UPDATE tasks SET state='PLANNED' WHERE id='{t}'")
        db.q(f"UPDATE tasks SET state='AWAITING_APPROVAL' WHERE id='{t}'")
        db.q(f"UPDATE tasks SET executor_agent_id='{world['exec']}', state='EXECUTING' WHERE id='{t}'")
        db.q(f"INSERT INTO evidence(task_id, kind, uri, hash, oracle_tier, produced_by) VALUES ('{t}','r','u','{H}','L2','ci')")
        db.rejects(f"UPDATE tasks SET state='EVIDENCE_SUBMITTED' WHERE id='{t}'", "does not meet required tier L4")

    def test_pause_resumes_only_to_prior_state(self, db, world):
        t = world["task"]
        db.q(f"UPDATE tasks SET state='BUDGET_HALTED' WHERE id='{t}'")
        db.rejects(f"UPDATE tasks SET state='EXECUTING' WHERE id='{t}'", "illegal transition")
        db.q(f"UPDATE tasks SET state='DRAFT' WHERE id='{t}'")
        assert db.one(f"SELECT resume_state IS NULL FROM tasks WHERE id='{t}'") == "t"

    def test_events_are_append_only(self, db, world):
        db.rejects("DELETE FROM task_events", "append-only")


class TestINV01RejectionsAreAudited:
    def test_illegal_transition_rejected_and_audit_entry_written(self, db, world):
        db.rejects(f"UPDATE tasks SET state='COMPLETED' WHERE id='{world['task']}'", "illegal transition")
        row = db.one(f"SELECT action || '|' || (payload->>'error') FROM audit_log "
                     f"WHERE action='task.rejected' AND target='{world['task']}'")
        assert row and row.startswith("task.rejected|state machine: illegal transition DRAFT -> COMPLETED")
        assert db.one("SELECT audit_verify() IS NULL") == "t"

    def test_insert_completed_without_verification_rejected_and_audited(self, db, world):
        db.rejects("INSERT INTO tasks(objective, task_class, state) VALUES ('x','code','COMPLETED')", "created in DRAFT")
        assert int(db.one("SELECT count(*) FROM audit_log WHERE action='task.rejected'")) >= 1
