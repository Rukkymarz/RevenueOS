"""INV-03: the executor is never the sole verifier; enforced at insert."""
import subprocess
import concurrent.futures as cf

import pytest

from dbkit import H, H2, HOST, PORT, USER, SqlError, advance_to_verifying, add_verification


class TestINV03VerifierSeparation:
    def test_executor_cannot_verify_own_task(self, db, world):
        advance_to_verifying(db, world)
        db.rejects(
            "INSERT INTO verifications(task_id, verifier_agent_id, method, method_class, verdict, tier) "
            f"VALUES ('{world['task']}','{world['exec']}','gitreins','deterministic','PASS','L4')",
            "INV-03: verifier equals executor")

    def test_executor_cannot_be_assigned_verifier(self, db, world):
        db.rejects(f"UPDATE tasks SET executor_agent_id='{world['exec']}', verifier_agent_id='{world['exec']}' "
                   f"WHERE id='{world['task']}'", "inv03_verifier_not_executor")

    def test_verifying_requires_verifier(self, db, world):
        advance_to_verifying(db, world)  # sanity: normal path works
        t2 = db.one("INSERT INTO tasks(objective, task_class, acceptance_criteria) VALUES ('t','code','[1]') RETURNING id")
        w2 = dict(world, task=t2)
        t = t2
        db.q(f"UPDATE tasks SET premise_bundle_id='{world['premise']}', state='RESEARCHED' WHERE id='{t}'")
        for s in ("PLANNED", "AWAITING_APPROVAL"):
            db.q(f"UPDATE tasks SET state='{s}' WHERE id='{t}'")
        db.q(f"UPDATE tasks SET executor_agent_id='{world['exec']}', state='EXECUTING' WHERE id='{t}'")
        db.q(f"INSERT INTO evidence(task_id, kind, uri, hash, oracle_tier, produced_by) "
             f"VALUES ('{t}','r','u','{H}','L3','ci')")
        db.q(f"UPDATE tasks SET state='EVIDENCE_SUBMITTED' WHERE id='{t}'")
        db.rejects(f"UPDATE tasks SET state='VERIFYING' WHERE id='{t}'", "INV-03: distinct verifier")


# ---------------------------------------------------------------- INV-04
