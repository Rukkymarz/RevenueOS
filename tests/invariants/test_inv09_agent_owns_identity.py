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
        db.rejects(f"INSERT INTO agent_identities(agent_id, kind, provider, secret_ref) "
                   f"VALUES ('{world['exec']}','email','stalwart','p@ssw0rd')", "agent_identities_secret_ref_check")

    @pytest.mark.xfail(strict=True, reason="control lands in Phase 2 (identity guard migration)")
    def test_attaching_to_a_human_chrome_profile_is_refused(self, db, world):
        from dbkit import SqlError
        with pytest.raises(SqlError):
            db.q(f"INSERT INTO agent_identities(agent_id, kind, provider, profile_path) "
                 f"VALUES ('{world['exec']}','browser_profile','chromium','/home/christine/.config/google-chrome/Default')")
