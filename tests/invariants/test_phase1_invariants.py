"""Phase 1 adversarial suite: each test attempts a violation and asserts rejection.

Covers INV-01, INV-02, INV-03, INV-04 (Phase 1 exit), plus the storage halves of
INV-06, INV-13, INV-14, INV-15, the state machine, and the audit chain.
"""
import subprocess
import concurrent.futures as cf

from conftest import H, H2, HOST, PORT, USER, advance_to_verifying, add_verification


# ---------------------------------------------------------------- INV-01
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
class TestINV02Receipts:
    def _call(self, db, w, risk="low", approval="NULL", args=H):
        return db.one(
            "INSERT INTO tool_calls(task_id, agent_id, mcp_server, tool, args_hash, args_redacted, "
            "result_hash, latency_ms, cost, risk_class, approval_id, verdict) VALUES "
            f"('{w['task']}','{w['exec']}','scraper','fetch','{args}','{{}}','{H2}',12,0.001,'{risk}',"
            f"{approval},'ok') RETURNING id")

    def test_receipt_is_immutable(self, db, world):
        c = self._call(db, world)
        db.rejects(f"UPDATE tool_calls SET cost=0 WHERE id='{c}'", "append-only")
        db.rejects(f"DELETE FROM tool_calls WHERE id='{c}'", "append-only")

    def test_receipt_requires_hashes_and_cost(self, db, world):
        db.rejects("INSERT INTO tool_calls(task_id, agent_id, mcp_server, tool, args_redacted, latency_ms, "
                   f"cost, risk_class, verdict) VALUES ('{world['task']}','{world['exec']}','s','t','{{}}',1,0,'low','ok')",
                   "args_hash")
        db.rejects("INSERT INTO tool_calls(task_id, agent_id, mcp_server, tool, args_hash, args_redacted, "
                   f"latency_ms, cost, risk_class, verdict) VALUES ('{world['task']}','{world['exec']}','s','t',"
                   "'not-a-hash','{}',1,0,'low','ok')", "args_hash_check")

    def test_receipt_writes_audit_entry(self, db, world):
        c = self._call(db, world)
        assert db.one(f"SELECT count(*) FROM audit_log WHERE action='tool.call' "
                      f"AND payload->>'tool_call_id'='{c}'") == "1"


# ---------------------------------------------------------------- INV-03
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
class TestINV06Approvals:
    def _approval(self, db, w, args=H, expires="now() + interval '10 minutes'", by="'owner'"):
        return db.one("INSERT INTO approvals(task_id, tool_call_args_hash, requested_by, approved_by, expires_at, status) "
                      f"VALUES ('{w['task']}','{args}','agent:exec',{by},{expires},'approved') RETURNING id")

    def _high_call(self, db, w, approval, args=H):
        return db.q("INSERT INTO tool_calls(task_id, agent_id, mcp_server, tool, args_hash, args_redacted, "
                    f"latency_ms, cost, risk_class, approval_id, verdict) VALUES ('{w['task']}','{w['exec']}',"
                    f"'outreach','send','{args}','{{}}',5,0,'high',{approval},'ok')")

    def test_high_risk_without_approval_rejected(self, db, world):
        db.rejects(self._sql_no_approval(world), "INV-06")

    def _sql_no_approval(self, w):
        return ("INSERT INTO tool_calls(task_id, agent_id, mcp_server, tool, args_hash, args_redacted, "
                f"latency_ms, cost, risk_class, verdict) VALUES ('{w['task']}','{w['exec']}','outreach','send',"
                f"'{H}','{{}}',5,0,'critical','ok')")

    def test_consumed_approval_allows_exactly_one_call(self, db, world):
        a = self._approval(db, world)
        assert db.one(f"SELECT consume_approval('{a}','{H}')") == "t"
        self._high_call(db, world, f"'{a}'")
        assert db.one(f"SELECT consume_approval('{a}','{H}')") == "f"      # single use
        db.rejects(self._sql_reuse(world, a), "INV-06")

    def _sql_reuse(self, w, a):
        return ("INSERT INTO tool_calls(task_id, agent_id, mcp_server, tool, args_hash, args_redacted, "
                f"latency_ms, cost, risk_class, approval_id, verdict) VALUES ('{w['task']}','{w['exec']}',"
                f"'outreach','send','{H}','{{}}',5,0,'high','{a}','ok')")

    def test_mutated_arguments_rejected(self, db, world):
        a = self._approval(db, world)
        assert db.one(f"SELECT consume_approval('{a}','{H2}')") == "f"

    def test_expired_approval_rejected(self, db, world):
        a = self._approval(db, world, expires="now() - interval '1 second'")
        assert db.one(f"SELECT consume_approval('{a}','{H}')") == "f"

    def test_self_approval_rejected(self, db, world):
        db.rejects("INSERT INTO approvals(task_id, tool_call_args_hash, requested_by, approved_by, expires_at, status) "
                   f"VALUES ('{world['task']}','{H}','alice','alice',now()+interval '1 hour','approved')",
                   "approvals_check")


# ---------------------------------------------------------------- INV-14 / INV-15 storage halves
class TestLearningAndInsightStorage:
    def test_skill_promotion_requires_positive_lift(self, db, world):
        db.rejects("INSERT INTO skills(agent_id, name, instructions, version, status, track) "
                   f"VALUES ('{world['exec']}','s','do x',1,'promoted','A')", "skills_check")
        db.rejects("INSERT INTO skills(agent_id, name, instructions, version, status, track, lift, lift_ci_low) "
                   f"VALUES ('{world['exec']}','s','do x',1,'promoted','A',0.1,-0.02)", "skills_check")

    def test_insight_role_cannot_read_unverified_tables(self, db, world):
        db.rejects("SET ROLE revenueos_insight; SELECT count(*) FROM tasks", "permission denied")
        assert db.one("SET ROLE revenueos_insight; SELECT count(*) FROM v_verified_tasks") == "0"


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
        db.rejects(f"INSERT INTO agent_identities(agent_id, kind, provider, secret_ref) "
                   f"VALUES ('{world['exec']}','email','stalwart','hunter2')", "agent_identities_secret_ref_check")


# ---------------------------------------------------------------- audit chain (C18)
class TestAuditChain:
    def test_forged_hash_is_overwritten(self, db, world):
        db.q("INSERT INTO audit_log(seq, prev_hash, hash, actor, action, target) "
             "VALUES (999,'forged','forged','x','y','z')")
        assert db.one("SELECT count(*) FROM audit_log WHERE hash='forged' OR seq=999") == "0"
        assert db.one("SELECT audit_verify() IS NULL") == "t"

    def test_update_delete_truncate_forbidden(self, db, world):
        db.rejects("UPDATE audit_log SET actor='evil'", "append-only")
        db.rejects("DELETE FROM audit_log", "append-only")
        db.rejects("TRUNCATE audit_log", "append-only")

    def test_tampering_is_detected(self, db, world):
        # Superuser bypasses the trigger; verification must still catch it.
        seq = db.one("SELECT max(seq) FROM audit_log")
        db.q("ALTER TABLE audit_log DISABLE TRIGGER trg_audit_append_only; "
             f"UPDATE audit_log SET actor='evil' WHERE seq={seq}; "
             "ALTER TABLE audit_log ENABLE TRIGGER trg_audit_append_only")
        assert db.one("SELECT audit_verify()") == seq

    def test_concurrent_writers_do_not_fork_chain(self, db, world):
        def writer(i):
            sql = "".join(f"SELECT audit_append('w{i}','load','t{j}','{{}}'::jsonb);" for j in range(100))
            return subprocess.run(["psql", "-h", HOST, "-p", PORT, "-U", USER, "-d", db.name,
                                   "-v", "ON_ERROR_STOP=1", "-X", "-q", "-c", sql],
                                  capture_output=True, text=True).returncode
        with cf.ThreadPoolExecutor(4) as ex:
            assert list(ex.map(writer, range(4))) == [0, 0, 0, 0]
        assert db.one("SELECT max(seq) = count(*) FROM audit_log") == "t"
        assert db.one("SELECT audit_verify() IS NULL") == "t"
