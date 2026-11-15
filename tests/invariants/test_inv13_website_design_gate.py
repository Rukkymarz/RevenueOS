"""INV-13: website deliverables pass the design gate before QC (storage half; D1-D8 land in Phase 9)."""
import subprocess
import concurrent.futures as cf

import pytest

from dbkit import H, H2, HOST, PORT, USER, SqlError, advance_to_verifying, add_verification


class TestINV13WebsiteGateStorage:
    def test_website_needs_framework_contract_and_passed_gate(self, db, world):
        p = db.one(f"INSERT INTO projects(name, business_line, premise_bundle_id, status) "
                   f"VALUES ('site','cleaning','{world['premise']}','active') RETURNING id")
        site = db.one(f"INSERT INTO websites(project_id, repo_path) VALUES ('{p}','/r') RETURNING id")
        t = db.one(f"INSERT INTO tasks(project_id, website_id, objective, task_class, acceptance_criteria) "
                   f"VALUES ('{p}','{site}','build','website','[1]') RETURNING id")
        db.q(f"UPDATE tasks SET premise_bundle_id='{world['premise']}', state='RESEARCHED' WHERE id='{t}'")
        db.rejects(f"UPDATE tasks SET state='PLANNED' WHERE id='{t}'", "D1")
        fc = db.one(f"INSERT INTO framework_contracts(project_id, framework, routing_model, data_layer, auth_model, "
                    f"deployment_target, generator, acceptance_criteria) VALUES ('{p}','nextjs16','app','postgres',"
                    f"'none','vercel','open-pages','[1]') RETURNING id")
        db.q(f"UPDATE projects SET framework_contract_id='{fc}' WHERE id='{p}'")
        db.q(f"UPDATE tasks SET state='PLANNED' WHERE id='{t}'")
        db.q(f"UPDATE tasks SET state='AWAITING_APPROVAL' WHERE id='{t}'")
        db.q(f"UPDATE tasks SET executor_agent_id='{world['exec']}', state='EXECUTING' WHERE id='{t}'")
        db.q(f"INSERT INTO evidence(task_id, kind, uri, hash, oracle_tier, produced_by) VALUES ('{t}','shots','u','{H}','L3','pw')")
        db.rejects(f"UPDATE tasks SET state='EVIDENCE_SUBMITTED' WHERE id='{t}'", "INV-13")
        db.q(f"UPDATE websites SET gate_status='PASSED' WHERE id='{site}'")
        db.q(f"UPDATE tasks SET state='EVIDENCE_SUBMITTED' WHERE id='{t}'")


# ---------------------------------------------------------------- INV-06 storage half
