"""INV-09: every agent has its own email identity and browser profile; no shared human session."""
import pytest


class TestINV09Identity:
    def test_two_agents_cannot_share_a_browser_profile(self, db, world):
        path = "/var/lib/revenueos/profiles/shared/g1"
        db.q(f"INSERT INTO agent_identities(agent_id, kind, provider, profile_path) "
             f"VALUES ('{world['exec']}','browser_profile','chromium','{path}')")
        db.rejects(f"INSERT INTO agent_identities(agent_id, kind, provider, profile_path) "
                   f"VALUES ('{world['ver']}','browser_profile','chromium','{path}')", "agent_identities_profile_path_key")

    def test_browser_profile_identity_must_name_a_path(self, db, world):
        db.rejects(f"INSERT INTO agent_identities(agent_id, kind, provider) VALUES ('{world['exec']}','browser_profile','chromium')",
                   "agent_identities_check")

    def test_identity_secrets_are_references_never_values(self, db, world):
        db.rejects(f"INSERT INTO agent_identities(agent_id, kind, provider, address, secret_ref) "
                   f"VALUES ('{world['exec']}','email','stalwart','x2@agents.revenueos.test','p@ssw0rd')", "agent_identities_secret_ref_check")

    def test_attaching_to_a_human_chrome_profile_is_refused(self, db, world):
        from dbkit import SqlError
        with pytest.raises(SqlError):
            db.q(f"INSERT INTO agent_identities(agent_id, kind, provider, profile_path) "
                 f"VALUES ('{world['exec']}','browser_profile','chromium','/home/christine/.config/google-chrome/Default')")

    def test_profile_outside_the_agent_root_is_refused(self, db, world):
        db.rejects(f"INSERT INTO agent_identities(agent_id, kind, provider, profile_path) "
                   f"VALUES ('{world['exec']}','browser_profile','chromium','/tmp/profiles/x')", "outside the agent profile root")

    def test_path_traversal_out_of_the_root_is_refused(self, db, world):
        db.rejects(f"INSERT INTO agent_identities(agent_id, kind, provider, profile_path) "
                   f"VALUES ('{world['exec']}','browser_profile','chromium','/var/lib/revenueos/profiles/../../home/c/.config/google-chrome')",
                   "normalized")

    def test_executor_without_own_identity_cannot_execute(self, db, world):
        bare = db.one("INSERT INTO agents(name, role, framework, budget_monthly) VALUES ('bare','coder','langgraph',1) RETURNING id")
        t = world["task"]
        db.q(f"UPDATE tasks SET premise_bundle_id='{world['premise']}', state='RESEARCHED' WHERE id='{t}'")
        db.q(f"UPDATE tasks SET state='PLANNED' WHERE id='{t}'")
        db.q(f"UPDATE tasks SET state='AWAITING_APPROVAL' WHERE id='{t}'")
        db.rejects(f"UPDATE tasks SET executor_agent_id='{bare}', state='EXECUTING' WHERE id='{t}'",
                   "lacks its own active email and browser profile")

    def test_two_active_identities_cannot_share_an_address(self, db, world):
        db.rejects(f"INSERT INTO agent_identities(agent_id, kind, provider, address) "
                   f"VALUES ('{world['ver']}','email','stalwart','EXEC@agents.revenueos.test')",
                   "agent_identities_unique_active_address")

    def test_phone_and_calendar_need_real_addresses(self, db, world):
        db.rejects(f"INSERT INTO agent_identities(agent_id, kind, provider, address) "
                   f"VALUES ('{world['exec']}','phone','46elks','555-1234')", "E.164")
        db.rejects(f"INSERT INTO agent_identities(agent_id, kind, provider, address) "
                   f"VALUES ('{world['exec']}','calendar','stalwart','not-a-url')", "CalDAV URL")
