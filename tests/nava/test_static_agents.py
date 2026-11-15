"""The seven static agents (spec 3.3): provisioned with capability fences, compiling
deterministic plans, running them through the gateway with receipts. The database — not agent
code — holds the fence (N04)."""
import pytest

from revenueos_runtime_os.agents import STATIC_AGENTS, provision_static_agents, run_objective

SEVEN = {"CodingAgent", "TerminalAgent", "ReviewerAgent", "VerifierAgent", "WebScraperAgent",
         "BrowserAgent", "ComputerAgent"}


@pytest.fixture
def agents(nava):
    ids = provision_static_agents(nava.k)
    # idempotent: a second provisioning changes nothing
    assert provision_static_agents(nava.k) == ids
    return ids


def test_all_seven_exist_with_fences(nava, agents):
    assert set(agents) == SEVEN
    row = nava.db.one("SELECT count(*) FROM agents WHERE framework='nava-static'")
    assert row == "7"
    # every agent is fenced: it has denies for every family outside its allow set
    for name, spec in STATIC_AGENTS.items():
        n = nava.db.one(f"SELECT count(*) FROM nava_denies WHERE agent_id='{agents[name]}'")
        assert int(n) == len(spec.denies), name


def test_coding_agent_writes_and_proves_with_tests(nava, agents):
    p = run_objective(nava.k, "CodingAgent", agents["CodingAgent"], nava.task, "ship greet()", {
        "workspace": "code",
        "files": {"greet.py": "def greet():\n    return 'hi'\n",
                  "test_greet.py": "from greet import greet\nassert greet() == 'hi'\n"},
        "check": ["python3", "test_greet.py"],
    })
    assert p["status"] == "completed", p
    assert all(s["status"] == "done" for s in p["steps"])


def test_terminal_agent_runs_commands_but_nothing_else(nava, agents):
    aid = agents["TerminalAgent"]
    p = run_objective(nava.k, "TerminalAgent", aid, nava.task, "touch marker", {
        "workspace": "term", "commands": [["sh", "-c", "echo made > marker.txt"]]})
    assert p["status"] == "completed"
    # fenced: the same agent cannot call fs.write directly
    r = nava.gw.syscall(caller_agent=aid, agent_id=aid, task_id=nava.task, tool="fs.write",
                        args={"workspace": "term", "path": "x", "content": "y"})
    assert r.status == "denied" and r.step == "authorize"
    # and the OpenMuse terminal cap holds: a plan asking for 300 s is compiled down to 30
    steps = STATIC_AGENTS["TerminalAgent"].compile({"workspace": "t", "commands": [["true"]], "timeout_s": 300})
    assert steps[0]["args"]["timeout_s"] == 30


def test_reviewer_agent_is_read_only(nava, agents):
    aid = agents["ReviewerAgent"]
    ws = nava.ws.path(aid, "rev")
    ws.mkdir(parents=True)
    (ws / "draft.md").write_text("content under review")
    p = run_objective(nava.k, "ReviewerAgent", aid, nava.task, "read the draft", {
        "workspace": "rev", "paths": ["draft.md"]})
    assert p["status"] == "completed"
    assert p["steps"][0]["output"]["status"] == "committed"
    for tool, args in (("fs.write", {"workspace": "rev", "path": "draft.md", "content": "overwrite"}),
                       ("fs.delete", {"workspace": "rev", "path": "draft.md"}),
                       ("sandbox.run", {"workspace": "rev", "argv": ["true"]})):
        r = nava.gw.syscall(caller_agent=aid, agent_id=aid, task_id=nava.task, tool=tool, args=args)
        assert r.status == "denied" and r.step == "authorize", tool


def test_verifier_agent_checks_postconditions(nava, agents):
    aid = agents["VerifierAgent"]
    ws = nava.ws.path(aid, "ver")
    ws.mkdir(parents=True)
    (ws / "artifact.txt").write_text("built-ok")
    p = run_objective(nava.k, "VerifierAgent", aid, nava.task, "verify the artifact", {
        "workspace": "ver",
        "checks": [{"argv": ["cat", "artifact.txt"],
                    "expect": [{"exit_code": 0}, {"stdout_contains": "built-ok"},
                               {"file_exists": "artifact.txt"}]}]})
    assert p["status"] == "completed"
    # a check whose postcondition fails rolls the step back and fails the plan honestly
    p2 = run_objective(nava.k, "VerifierAgent", aid, nava.task, "verify a lie", {
        "workspace": "ver",
        "checks": [{"argv": ["cat", "artifact.txt"], "expect": [{"stdout_contains": "no-such-text"}],
                    }]}, )
    assert p2["status"] == "failed"
    sid = p2["steps"][0]["syscall_id"]
    assert nava.db.one(f"SELECT status FROM syscalls WHERE id='{sid}'") in ("rolled_back", "failed")


def test_desktop_agents_compile_real_plans_and_stay_fenced(nava, agents):
    # plan compilation is deterministic and non-empty (execution needs runtime-omni: e2e covers it)
    assert STATIC_AGENTS["WebScraperAgent"].compile({"urls": ["http://u/1", "http://u/2"]}) == [
        {"tool": "omni.web.fetch_url", "args": {"url": "http://u/1"}},
        {"tool": "omni.web.fetch_url", "args": {"url": "http://u/2"}}]
    assert STATIC_AGENTS["BrowserAgent"].compile({"urls": ["http://u"]})[0]["tool"] == "omni.browser.open_url"
    comp = STATIC_AGENTS["ComputerAgent"].compile({"type_texts": ["hello"], "notify": "done"})
    assert [s["tool"] for s in comp] == ["omni.screen.screenshot", "omni.gui.type_text",
                                         "omni.notify.send_notification"]
    # ComputerAgent has no filesystem or shell at all
    aid = agents["ComputerAgent"]
    for tool, args in (("sandbox.run", {"workspace": "w", "argv": ["true"]}),
                       ("fs.read", {"workspace": "w", "path": "x"})):
        r = nava.gw.syscall(caller_agent=aid, agent_id=aid, task_id=nava.task, tool=tool, args=args)
        assert r.status == "denied" and r.step == "authorize", tool


def test_agents_are_bound_to_gateway_receipts(nava, agents):
    before = int(nava.db.one("SELECT count(*) FROM tool_calls WHERE mcp_server='runtime-os'"))
    run_objective(nava.k, "TerminalAgent", agents["TerminalAgent"], nava.task, "echo", {
        "workspace": "term2", "commands": [["echo", "receipted"]]})
    after = int(nava.db.one("SELECT count(*) FROM tool_calls WHERE mcp_server='runtime-os'"))
    assert after == before + 1
