"""Schema guards outside the fifteen invariants: research labels, pins, secret references."""
import subprocess
import concurrent.futures as cf

import pytest

from dbkit import H, H2, HOST, PORT, USER, SqlError, advance_to_verifying, add_verification


class TestResearchAndPins:
    def test_unlabeled_claim_rejected(self, db, world):
        rr = db.one("INSERT INTO research_runs(target, pack) VALUES ('t','saas') RETURNING id")
        db.rejects(f"INSERT INTO premise_bundles(research_run_id, claims, missing_data) "
                   f"VALUES ('{rr}','[{{\"text\":\"x\"}}]','[]')", "C07")
        db.rejects(f"INSERT INTO premise_bundles(research_run_id, claims, missing_data) "
                   f"VALUES ('{rr}','[{{\"text\":\"x\",\"label\":\"verified\"}}]','[]')", "verified claim without source_ids")

    def test_project_needs_premise_to_leave_draft(self, db, world):
        db.rejects("INSERT INTO projects(name, business_line, status) VALUES ('p','x','active')", "projects_check")

    def test_upstream_pin_cannot_be_fabricated_shape(self, db, world):
        db.rejects("INSERT INTO pins(project_name, resolution_mode, evidence_uri) VALUES ('LangGraph','upstream','docs/pins/x.md')",
                   "pins_check")
        db.rejects("INSERT INTO pins(project_name, repo_url, commit_sha, license, resolution_mode, evidence_uri) "
                   "VALUES ('x','https://github.com/a/b','abc123','MIT','upstream','e')", "commit_sha")

    def test_literal_secret_rejected(self, db, world):
        db.rejects(f"INSERT INTO agent_identities(agent_id, kind, provider, address, secret_ref) "
                   f"VALUES ('{world['exec']}','email','stalwart','x2@agents.revenueos.test','hunter2')", "agent_identities_secret_ref_check")


# ---------------------------------------------------------------- audit chain (C18)
