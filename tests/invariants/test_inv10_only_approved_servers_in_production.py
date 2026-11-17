"""INV-10: MCP servers are experimental | approved | production; only approved/production
may be activated for production tasks."""
import pytest


class TestINV10ServerStatus:
    def test_server_cannot_be_marked_approved_without_an_approver(self, db, world):
        db.rejects("INSERT INTO tool_installations(mcp_server_name, registry_source, version, checksum, license, "
                   "resolution_mode, status) VALUES ('evil','npm','1.0.0','sha256:x','MIT','upstream','approved')",
                   "tool_installations_check")

    def test_unknown_status_is_impossible(self, db, world):
        db.rejects("INSERT INTO tool_installations(mcp_server_name, registry_source, version, checksum, license, "
                   "resolution_mode, status) VALUES ('evil','npm','1.0.0','sha256:x','MIT','upstream','trusted')",
                   "invalid input value for enum install_status")

    @pytest.mark.xfail(strict=True, raises=ImportError, reason="control lands in Phase 4 (agent-discover activation)")
    def test_experimental_server_cannot_activate_for_production_task(self, db, world):
        from revenueos_discovery.registry import ActivationRefused, activate
        with pytest.raises(ActivationRefused):
            activate(server="evil", task_environment="production")
