"""Proves every component is wired in, every hop has a contract, and the
default stack is open source. Reads config/components.yaml and
packages/contracts/schemas/connections.json; no network."""
from collections import defaultdict, deque
from pathlib import Path
import json

import jsonschema
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CFG = yaml.safe_load((ROOT / "config" / "components.yaml").read_text())
SCHEMA = json.loads((ROOT / "packages" / "contracts" / "schemas" / "connections.json").read_text())
NODES = {c["id"]: c for c in CFG["components"]}
BUSES = CFG["buses"]
FLOWS = CFG["flows"]
DEFS = SCHEMA["$defs"]
AI_KINDS = {"agent", "framework"}


def validator(name):
    return jsonschema.Draft202012Validator({"$ref": f"#/$defs/{name}", "$defs": DEFS},
                                           format_checker=jsonschema.FormatChecker())


def test_ids_unique():
    ids = [c["id"] for c in CFG["components"]]
    assert len(ids) == len(set(ids))


def test_every_spec_component_is_present():
    present = {c["component"] for c in CFG["components"]}
    assert present == {f"C{i:02d}" for i in range(1, 19)}


@pytest.mark.parametrize("node", CFG["components"], ids=lambda n: n["id"])
def test_node_attaches_to_known_buses(node):
    assert node["buses"], f"{node['id']} is not connected to anything"
    unknown = set(node["buses"]) - set(BUSES)
    assert not unknown, f"{node['id']} uses unknown buses {unknown}"


@pytest.mark.parametrize("node", [n for n in CFG["components"] if n["kind"] in AI_KINDS], ids=lambda n: n["id"])
def test_ai_component_can_talk_to_other_agents_and_tools(node):
    # An AI component must reach other agents (A2A) or tools (MCP) and be
    # dispatchable: it attaches to the A2A bus or task API, or is the target of a flow.
    assert {"a2a-bus", "mcp-gateway"} & set(node["buses"]), f"{node['id']} cannot call agents or tools"
    dispatchable = {"a2a-bus", "task-api"} & set(node["buses"]) or any(f["to"] == node["id"] for f in FLOWS)
    assert dispatchable, f"{node['id']} cannot be dispatched by the orchestrator"


@pytest.mark.parametrize("node", [n for n in CFG["components"] if n["kind"] == "tool"], ids=lambda n: n["id"])
def test_tools_are_behind_the_governed_gateway(node):
    assert "mcp-gateway" in node["buses"], f"tool {node['id']} bypasses C04 governance"


def test_whole_system_is_one_connected_graph():
    adj = defaultdict(set)
    for n in CFG["components"]:
        for b in n["buses"]:
            adj[n["id"]].add("bus:" + b)
            adj["bus:" + b].add(n["id"])
    for f in FLOWS:
        adj[f["from"]].add(f["to"])
        adj[f["to"]].add(f["from"])
    seen, q = {"langgraph"}, deque(["langgraph"])
    while q:
        for m in adj[q.popleft()] - seen:
            seen.add(m)
            q.append(m)
    orphans = set(NODES) - seen
    assert not orphans, f"unreachable from the orchestrator: {sorted(orphans)}"


# ------------------------------------------------------------- open source
@pytest.mark.parametrize("node", CFG["components"], ids=lambda n: n["id"])
def test_open_source_rule(node):
    assert node["oss"] in (True, False, "verify")
    if node["oss"] is False:
        assert node["role"] == "fallback", f"{node['id']} is closed-source but not a fallback"
        target = NODES.get(node.get("fallback_for"))
        assert target, f"{node['id']} must name the open-source node it backs up"
        assert target["oss"] is True, f"{node['id']} backs up {target['id']}, which is not confirmed open source"
    if node["role"] == "primary":
        assert node["oss"] in (True, "verify"), f"primary {node['id']} must be open source"


def test_model_router_defaults_to_open_weights():
    r = NODES["model-router"]
    assert r["defaults"]["weights"] == "open"
    assert set(r["defaults"]["inference"]) <= {k for k, v in NODES.items() if v["oss"] is True}


def test_licenses_never_guessed():
    for n in CFG["components"]:
        if n["oss"] == "verify":
            assert n["license"] == "verify-at-pin", f"{n['id']}: unverified project carries a guessed license"


# ------------------------------------------------------------- flows and contracts
def test_every_contract_is_defined_and_valid_schema():
    used = {b["contract"] for b in BUSES.values()} | {f["contract"] for f in FLOWS}
    missing = used - set(DEFS)
    assert not missing, f"undefined contracts: {missing}"
    for name in used:
        jsonschema.Draft202012Validator.check_schema({"$ref": f"#/$defs/{name}", "$defs": DEFS})


@pytest.mark.parametrize("flow", FLOWS, ids=lambda f: f"{f['step']}:{f['from']}->{f['to']}")
def test_flow_hop_is_physically_possible(flow):
    a, b = NODES.get(flow["from"]), NODES.get(flow["to"])
    assert a and b, f"flow references unknown component in {flow}"
    assert flow["bus"] in a["buses"], f"{a['id']} is not on {flow['bus']}"
    assert flow["bus"] in b["buses"], f"{b['id']} is not on {flow['bus']}"


def test_workflow_covers_all_twelve_steps_and_is_unbroken():
    assert {f["step"] for f in FLOWS} == set(range(1, 13))
    adj = defaultdict(set)
    for f in FLOWS:
        adj[f["from"]].add(f["to"])
    seen, q = {"leads-agent"}, deque(["leads-agent"])
    while q:
        for m in adj[q.popleft()] - seen:
            seen.add(m)
            q.append(m)
    for must in ("openbusiness", "agentic-pm", "command-center", "open-pages", "outreach",
                 "postiz", "verifier-agent", "postgres", "myelinate", "tares"):
        assert must in seen, f"workflow never reaches {must}"


# ------------------------------------------------------------- contract behavior
def _ok(name, payload):
    validator(name).validate(payload)


def _bad(name, payload):
    with pytest.raises(jsonschema.ValidationError):
        validator(name).validate(payload)


U = "8f14e45f-ceea-4e7a-9f4c-1b2d3e4f5a6b"
HX = "c" * 64


def test_tool_call_contract_requires_approval_for_high_risk():
    base = {"task_id": U, "agent": "agent:leads", "server": "outreach", "tool": "send",
            "args": {}, "args_hash": HX, "risk_class": "low", "trace_id": "0123456789abcdef"}
    _ok("mcp.tool_call", base)
    _bad("mcp.tool_call", dict(base, risk_class="high"))
    _ok("mcp.tool_call", dict(base, risk_class="high", approval_id=U))
    _bad("mcp.tool_call", dict(base, args_hash="nope"))
    _bad("mcp.tool_call", dict(base, api_key="sk-live-123"))   # no smuggled fields


def test_verification_contract_forbids_llm_confirmation():
    v = {"task_id": U, "verifier": "agent:qc", "method": "gitreins", "method_class": "llm",
         "verdict": "VETO", "tier": "L2"}
    _ok("verification", v)
    _bad("verification", dict(v, verdict="PASS"))
    _ok("verification", dict(v, method_class="deterministic", verdict="PASS"))


def test_premise_contract_requires_labels_and_sources():
    good = {"research_run_id": U, "missing_data": [],
            "claims": [{"text": "a", "label": "verified", "source_ids": ["s1"]},
                       {"text": "b", "label": "inferred"}]}
    _ok("premise.bundle", good)
    _bad("premise.bundle", dict(good, claims=[{"text": "a"}]))
    _bad("premise.bundle", dict(good, claims=[{"text": "a", "label": "verified"}]))
    _bad("premise.bundle", dict(good, claims=[{"text": "a", "label": "verified", "source_ids": []}]))
