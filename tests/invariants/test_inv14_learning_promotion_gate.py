"""INV-14: learning updates need canary + holdout causal lift before promotion; reversible."""
import subprocess
import concurrent.futures as cf

import pytest

from dbkit import H, H2, HOST, PORT, USER, SqlError, advance_to_verifying, add_verification


class TestINV14PromotionNeedsLift:
    def test_skill_promotion_requires_positive_lift(self, db, world):
        db.rejects("INSERT INTO skills(agent_id, name, instructions, version, status, track) "
                   f"VALUES ('{world['exec']}','s','do x',1,'promoted','A')", "skills_check")
        db.rejects("INSERT INTO skills(agent_id, name, instructions, version, status, track, lift, lift_ci_low) "
                   f"VALUES ('{world['exec']}','s','do x',1,'promoted','A',0.1,-0.02)", "skills_check")

    def test_promoted_skill_keeps_prior_versions_for_rollback(self, db, world):
        db.q(f"INSERT INTO skills(agent_id, name, instructions, version, status, track, lift, lift_ci_low) "
             f"VALUES ('{world['exec']}','s','v1',1,'promoted','A',0.2,0.05)")
        db.q(f"INSERT INTO skills(agent_id, name, instructions, version, status, track, lift, lift_ci_low) "
             f"VALUES ('{world['exec']}','s','v2',2,'promoted','A',0.3,0.1)")
        db.rejects(f"INSERT INTO skills(agent_id, name, instructions, version, status, track) "
                   f"VALUES ('{world['exec']}','s','dup',2,'canary','A')", "skills_agent_id_name_version_key")
        assert db.one("SELECT count(*) FROM skills WHERE name='s'") == "2"
