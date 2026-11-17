"""INV-04: an LLM verifier may veto but never confirm."""
import subprocess
import concurrent.futures as cf

import pytest

from dbkit import H, H2, HOST, PORT, USER, SqlError, advance_to_verifying, add_verification


class TestINV04LlmMayOnlyVeto:
    def test_llm_pass_rejected(self, db, world):
        advance_to_verifying(db, world)
        db.rejects(
            "INSERT INTO verifications(task_id, verifier_agent_id, method, method_class, verdict, tier) "
            f"VALUES ('{world['task']}','{world['ver']}','gitreins','llm','PASS','L4')",
            "INV-04")

    def test_llm_pass_rejected_even_with_trigger_disabled(self, db, world):
        advance_to_verifying(db, world)
        db.rejects(
            "ALTER TABLE verifications DISABLE TRIGGER trg_verification_guard; "
            "INSERT INTO verifications(task_id, verifier_agent_id, method, method_class, verdict, tier) "
            f"VALUES ('{world['task']}','{world['ver']}','gitreins','llm','PASS','L4')",
            "inv04_llm_never_confirms")

    def test_llm_veto_accepted_and_blocks(self, db, world):
        advance_to_verifying(db, world)
        v = add_verification(db, world, verdict="VETO", method_class="llm")
        db.rejects(f"UPDATE tasks SET verification_id='{v}', state='QC_PASSED' WHERE id='{world['task']}'", "INV-01")
        db.q(f"UPDATE tasks SET state='FAILED_QC' WHERE id='{world['task']}'")
        db.q(f"UPDATE tasks SET state='EXECUTING' WHERE id='{world['task']}'")
        assert db.one(f"SELECT state FROM tasks WHERE id='{world['task']}'") == "EXECUTING"


# ---------------------------------------------------------------- state machine guards
