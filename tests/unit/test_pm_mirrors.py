"""Mirrors, the roster and the HTTP surface (Phase 5). Mission Control is faked at its REST edge
here; the real application is exercised in tests/e2e/test_phase5_stack.py."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from pm_kit import make_plan, pgdb, project_with_plan  # noqa: F401
from discovery_kit import Secrets
from revenueos_pm import app as appmod, mirrors, roster

ROOT = Path(__file__).resolve().parents[2]


class FakeMC(BaseHTTPRequestHandler):
    tasks: dict = {}

    def log_message(self, *a):
        pass

    def _send(self, code, body):
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _body(self):
        n = int(self.headers.get("content-length") or 0)
        return json.loads(self.rfile.read(n)) if n else {}

    def do_POST(self):
        if self.headers.get("x-api-key") != "k":
            return self._send(401, {"error": "no"})
        b = self._body()
        i = len(self.tasks) + 1
        self.tasks[str(i)] = {**b, "id": i}
        self._send(201, {"task": self.tasks[str(i)]})

    def do_PUT(self):
        i = self.path.rsplit("/", 1)[1]
        self.tasks[i].update(self._body())
        self._send(200, {"task": self.tasks[i]})

    def do_GET(self):
        i = self.path.rsplit("/", 1)[1]
        self._send(200, {"task": self.tasks[i]}) if i in self.tasks else self._send(404, {})


@pytest.fixture
def mc_url():
    FakeMC.tasks = {}
    srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeMC)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_sync_writes_every_mirror_records_where_and_repairs_on_change(pgdb, world, mc_url, tmp_path):
    pid, ids = project_with_plan(pgdb, world, slices=4, tasks_per_slice=1)
    t = ids["s0t0"]
    mc, tr = mirrors.MissionControl(mc_url, key="k"), mirrors.FileTracker(tmp_path / "tr")
    out = mirrors.sync(pgdb, t, mc=mc, tracker=tr)
    assert out["mission-control"] == "1" and out["llm-tracker"] == f"{t}.json"
    assert FakeMC.tasks["1"]["metadata"]["revenueos_task_id"] == t and FakeMC.tasks["1"]["status"] == "inbox"
    pgdb.rows("UPDATE tasks SET objective = 'changed' WHERE id = $t::uuid RETURNING id", t=t)
    mirrors.sync(pgdb, t, mc=mc, tracker=tr)
    assert len(FakeMC.tasks) == 1 and FakeMC.tasks["1"]["description"] == "changed"
    assert mc.get("1")["id"] == 1 and tr.get(t)["objective"] == "changed"
    assert pgdb.scalar("SELECT count(*) AS n FROM task_mirrors WHERE task_id = $t::uuid", t=t) == 2


def test_a_mirror_that_is_down_never_blocks_the_task(pgdb, world, tmp_path):
    pid, ids = project_with_plan(pgdb, world, slices=4, tasks_per_slice=1)
    out = mirrors.sync(pgdb, ids["s0t0"], mc=mirrors.MissionControl("http://127.0.0.1:9", key="k"), piyaz=mirrors.Piyaz("http://127.0.0.1:9", token="t"),
                       tracker=mirrors.FileTracker(tmp_path))
    assert out["mission-control"].startswith("error:") and out["piyaz"].startswith("error:") and out["llm-tracker"].endswith(".json")
    with pytest.raises(mirrors.MirrorError, match="not provisioned"):
        mirrors.MissionControl("http://x", key=lambda: None).key()
    with pytest.raises(mirrors.MirrorError, match="not provisioned"):
        mirrors.Piyaz("http://x").call("t", {})


def test_file_tracker_is_atomic_and_rejects_bad_ids(tmp_path):
    tr = mirrors.FileTracker(tmp_path)
    tr.put({"id": "abc-1", "state": "DRAFT"})
    assert tr.patch("abc-1", state="PLANNED")["state"] == "PLANNED" and [t["id"] for t in tr.list()] == ["abc-1"]
    assert tr.get("nope") is None and not list(tmp_path.glob("*.tmp"))
    with pytest.raises(mirrors.MirrorError):
        tr.get("../etc/passwd")
    with pytest.raises(mirrors.MirrorError):
        tr.patch("missing", x=1)


def test_status_mapping_covers_every_state():
    states = {"DRAFT", "RESEARCHED", "PLANNED", "AWAITING_APPROVAL", "EXECUTING", "EVIDENCE_SUBMITTED", "VERIFYING", "QC_PASSED",
              "FAILED_QC", "COMPLETED", "BLOCKED", "BUDGET_HALTED", "AWAITING_HUMAN_APPROVAL", "CANCELLED"}
    assert states == set(mirrors.MC_STATUS)


def test_roster_matches_the_generator_and_every_agent_has_a_full_companion():
    import subprocess
    import sys
    assert subprocess.run([sys.executable, str(ROOT / "scripts/gen_roster.py"), "--check"]).returncode == 0
    agents = roster.load(ROOT)
    assert len(agents) >= 20 and {a["division"] for a in agents} >= {"engineering", "design", "research"}
    for a in agents:
        for section in ("## Core mission", "## Technical deliverables", "## Success metrics", "## Allowed MCP tools"):
            assert section in a["markdown"], (a["id"], section)


@pytest.fixture
def client(pgdb, tmp_path, mc_url, monkeypatch):
    appmod._state.clear()
    appmod._state.update(db=pgdb, secrets=Secrets({}), mc=mirrors.MissionControl(mc_url, key="k"), tracker=mirrors.FileTracker(tmp_path))
    monkeypatch.setenv("REVENUEOS_CONFIG_DIR", str(ROOT / "config"))
    yield TestClient(appmod.app)
    appmod._state.clear()


def test_http_flow_project_to_completed_slice_and_mirrors(client, world):
    c = client
    pid = c.post("/v1/projects", json={"name": "p", "business_line": "cleaning", "premise_bundle_id": world["premise"]}).json()["id"]
    for kind in ("spec", "plan", "rules"):
        v = c.post(f"/v1/projects/{pid}/artifacts", json={"kind": kind, "content": f"{kind} body"}).json()["version"]
        assert c.post(f"/v1/projects/{pid}/artifacts/{kind}/{v}/approve", json={"approved_by": "agent:planner"}).status_code == 409
        assert c.post(f"/v1/projects/{pid}/artifacts/{kind}/{v}/approve", json={"approved_by": "human:christine"}).status_code == 200
    bad = c.post(f"/v1/projects/{pid}/plan", json={"plan": {"milestones": []}})
    assert bad.status_code == 422
    ids = c.post(f"/v1/projects/{pid}/plan", json={"plan": make_plan(4, 1)}).json()
    assert ids["artifacts_approved"] and len(c.get(f"/v1/projects/{pid}/tree").json()["tree"]) == 4
    t = ids["tasks"]["s0t0"]
    sid = c.get(f"/v1/projects/{pid}/tree").json()["tree"][0]["slice_id"]
    run = c.post(f"/v1/slices/{sid}/run", json={"executor_agent_id": world["exec"], "verifier_agent_id": world["ver"],
                                               "premise_bundle_id": world["premise"]}).json()
    assert run["status"] == "done" and run["completed"] == [t]
    synced = c.post(f"/v1/tasks/{t}/mirror/sync", json={}).json()
    assert synced.get("mission-control") == "1", synced
    assert FakeMC.tasks["1"]["status"] == "done"
    assert c.post(f"/v1/tasks/{t}/archive", json={}).json() == {"archived": True}
    assert c.post(f"/v1/tasks/{t}/bogus", json={}).status_code == 400
    assert c.post(f"/v1/tasks/{t}/execute", json={}).status_code == 409           # terminal state: the database says no
    assert c.get(f"/v1/tasks/{t}/mirror/visibility").status_code in (200, 502)
    assert len(c.get("/v1/roster").json()["agents"]) >= 20
    assert c.get("/v1/info").json()["component"] == "C06"
