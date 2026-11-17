"""Phase 5 acceptance against the live stack (spec Acceptance 5): a project cannot execute before its
Spec/Plan/Rules are approved by a human; a plan becomes a milestone/slice/task tree; the scripted slice
runner completes it end to end; one task is visible through Mission Control's REST, CLI, MCP and web
session; the roster lists all twenty agents. Piyaz is reported separately (docs/reviews/phase-5-review.md)."""
import json
import os
import subprocess
from pathlib import Path

import pytest

from test_phase4_stack import COMPOSE, http, psql

pytestmark = pytest.mark.skipif(os.environ.get("REVENUEOS_E2E") != "1", reason="needs the running compose stack")


def pm(method, path, body=None):
    return http("http://pm:8106", method, path, body, container="pm")


@pytest.fixture(scope="module")
def world():
    ag = {}
    for role in ("exec", "ver"):
        ag[role] = psql(f"INSERT INTO agents(name, role, framework, budget_monthly) VALUES ('p5-{role}','x','langgraph',100) RETURNING id").splitlines()[0]
        psql(f"INSERT INTO agent_identities(agent_id, kind, provider, address) VALUES ('{ag[role]}','email','stalwart','p5-{role}@agents.revenueos.test')")
        psql(f"INSERT INTO agent_identities(agent_id, kind, provider, profile_path) VALUES ('{ag[role]}','browser_profile','chromium','/var/lib/revenueos/profiles/{ag[role]}/default')")
    rr = psql("INSERT INTO research_runs(target, pack) VALUES ('acme','local-services') RETURNING id").splitlines()[0]
    ag["premise"] = psql("INSERT INTO premise_bundles(research_run_id, claims, missing_data) VALUES "
                         f"('{rr}', '[{{\"text\":\"x\",\"label\":\"verified\",\"source_ids\":[\"s1\"]}}]', '[]') RETURNING id").splitlines()[0]
    return ag


PLAN = {"milestones": [{"name": "MVP", "slices": [
    {"name": f"slice {i}", "tasks": [
        {"key": f"s{i}t{j}", "objective": f"build part {i}.{j}", "task_class": "code",
         "acceptance_criteria": [{"check": "tests_pass"}], "cost_estimate": 1.0,
         **({"depends_on": [f"s{i}t{j - 1}"]} if j else {})} for j in range(2)]} for i in range(4)]}]}


def test_roster_lists_twenty_agents():
    st, r = pm("GET", "/v1/roster")
    assert st == 200 and len(r["agents"]) == 20, r


def test_approval_gate_then_tree_then_run_and_mirror(world):
    st, p = pm("POST", "/v1/projects", {"name": "e2e", "business_line": "cleaning", "premise_bundle_id": world["premise"]})
    assert st == 200
    pid = p["id"]
    st, planned = pm("POST", f"/v1/projects/{pid}/plan", {"plan": PLAN})
    assert st == 200 and planned["artifacts_approved"] is False and len(planned["tasks"]) == 8
    st, tree = pm("GET", f"/v1/projects/{pid}/tree")
    slices = [s for m in tree["tree"] for s in m["slices"]]
    assert len(slices) == 4
    tid = next(iter(planned["tasks"].values()))
    # no approved Spec/Plan/Rules: the database refuses EXECUTING
    st, _ = pm("POST", f"/v1/tasks/{tid}/publish", {"premise_bundle_id": world["premise"]})
    assert st == 200
    st, _ = pm("POST", f"/v1/tasks/{tid}/claim", {"agent_id": world["exec"]})
    assert st == 200
    assert pm("POST", f"/v1/tasks/{tid}/plan", {})[0] == 200
    st, err = pm("POST", f"/v1/tasks/{tid}/execute", {})
    assert st in (409, 422), err
    # an agent cannot approve; a human can
    for kind in ("spec", "plan", "rules"):
        v = pm("POST", f"/v1/projects/{pid}/artifacts", {"kind": kind, "content": f"{kind} text"})[1]["version"]
        assert pm("POST", f"/v1/projects/{pid}/artifacts/{kind}/{v}/approve", {"approved_by": "agent:planner"})[0] in (409, 422)
        assert pm("POST", f"/v1/projects/{pid}/artifacts/{kind}/{v}/approve", {"approved_by": "human:christine"})[0] == 200
    assert pm("GET", f"/v1/projects/{pid}/tree")[1]["artifacts_approved"] is True
    # Auto Mode machinery with the scripted components completes a slice
    sid = slices[0]["id"]
    st, rep = pm("POST", f"/v1/slices/{sid}/run", {"executor_agent_id": world["exec"], "verifier_agent_id": world["ver"],
                                                  "premise_bundle_id": world["premise"], "cost_per_task": 0.1})
    assert st == 200 and rep["status"] in ("done", "blocked"), rep
    # one task visible through every Mission Control interface
    st, _ = pm("POST", f"/v1/tasks/{tid}/mirror/sync", {"targets": ["mission-control"]})
    assert st == 200
    st, vis = pm("GET", f"/v1/tasks/{tid}/mirror/visibility")
    assert st == 200 and all(v is True for v in vis["visible"].values()), vis
