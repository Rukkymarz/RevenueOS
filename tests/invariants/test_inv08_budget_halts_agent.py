"""INV-08: every agent has a monthly spend budget; exceeding it halts the agent."""
import pytest


class TestINV08Budgets:
    def test_spend_beyond_limit_is_rejected_by_the_database(self, db, world):
        db.q(f"INSERT INTO budgets(agent_id, period, \"limit\", used) VALUES ('{world['exec']}','2026-11',10,9)")
        db.rejects(f"UPDATE budgets SET used = used + 2 WHERE agent_id='{world['exec']}'", "budgets_check")
        db.rejects(f"UPDATE budgets SET reserved = 5 WHERE agent_id='{world['exec']}'", "budgets_check")

    def test_one_budget_row_per_agent_and_period(self, db, world):
        db.q(f"INSERT INTO budgets(agent_id, period, \"limit\") VALUES ('{world['exec']}','2026-11',10)")
        db.rejects(f"INSERT INTO budgets(agent_id, period, \"limit\") VALUES ('{world['exec']}','2026-11',999)",
                   "budgets_agent_id_period_key")

    def test_task_can_be_halted_and_resumes_only_where_it_stopped(self, db, world):
        t = world["task"]
        db.q(f"UPDATE tasks SET state='BUDGET_HALTED' WHERE id='{t}'")
        db.rejects(f"UPDATE tasks SET state='COMPLETED' WHERE id='{t}'", "illegal transition")

    @pytest.mark.xfail(strict=True, raises=ImportError, reason="control lands in Phase 13 (model router reservation)")
    def test_router_halts_agent_when_reservation_exceeds_budget(self, db, world):
        from revenueos_orchestrator.router import BudgetExceeded, reserve
        with pytest.raises(BudgetExceeded):
            reserve(agent_id=world["exec"], estimated_cost=1_000_000)
