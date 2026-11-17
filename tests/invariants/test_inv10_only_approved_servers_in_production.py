"""INV-10: MCP servers are experimental | approved | production; only approved/production
may be activated for production tasks."""

class TestINV10ServerStatus:
    def test_server_cannot_be_marked_approved_without_an_approver(self, db, world):
        db.rejects("INSERT INTO tool_installations(mcp_server_name, registry_source, version, checksum, license, "
                   "resolution_mode, status) VALUES ('evil','npm','1.0.0','sha256:x','MIT','upstream','approved')",
                   "tool_installations_check")

    def test_unknown_status_is_impossible(self, db, world):
        db.rejects("INSERT INTO tool_installations(mcp_server_name, registry_source, version, checksum, license, "
                   "resolution_mode, status) VALUES ('evil','npm','1.0.0','sha256:x','MIT','upstream','trusted')",
                   "invalid input value for enum install_status")

    def test_experimental_server_cannot_activate_for_production_task(self, db, world):
        """The database function is the control; the service asks it and logs the answer
        (full path with the service: tests/unit/test_discovery_registry.py)."""
        db.q("INSERT INTO tool_installations(mcp_server_name, registry_source, version, checksum, license, "
             "resolution_mode) VALUES ('evil','npm','1.0.0','sha256:x','MIT','upstream')")
        why = db.one(f"SELECT tool_activation_refusal('evil', '{world['task']}')")
        assert why and "experimental" in why
        db.rejects(f"INSERT INTO tool_activations(installation_id, task_id) SELECT id, '{world['task']}' "
                   "FROM tool_installations WHERE mcp_server_name = 'evil'", "INV-10")

    def test_an_experimental_server_may_not_skip_to_production(self, db, world):
        db.q("INSERT INTO tool_installations(mcp_server_name, registry_source, version, checksum, license, "
             "resolution_mode) VALUES ('evil','npm','1.0.0','sha256:x','MIT','upstream')")
        db.rejects("UPDATE tool_installations SET status = 'production', approved_by = 'x' WHERE mcp_server_name = 'evil'",
                   "INV-10")
