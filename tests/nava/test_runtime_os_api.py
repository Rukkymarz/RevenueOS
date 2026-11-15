"""HTTP surface of runtime-os: token authentication, isolation between agents, and the syscall
route returning the gateway's verdicts. Skips locally when httpx (TestClient's engine) is absent;
CI always runs it."""
import os

import pytest

pytest.importorskip("httpx")
from starlette.testclient import TestClient  # noqa: E402


@pytest.fixture
def api(nava, pgdb, monkeypatch):
    import revenueos_runtime_os.app as app_mod
    monkeypatch.setattr(app_mod, "db", pgdb)
    monkeypatch.setitem(app_mod._state, "k", nava.k)
    token = nava.k.issue_token(nava.agent)
    other_token = nava.k.issue_token(nava.other)
    client = TestClient(app_mod.app)
    return client, {"authorization": f"Bearer {token}"}, {"authorization": f"Bearer {other_token}"}, nava


def test_unauthenticated_is_401(api):
    client, *_ = api
    assert client.post("/v1/syscalls", json={}).status_code == 401
    assert client.get("/v1/tools").status_code == 401
    assert client.post("/v1/syscalls", json={}, headers={"authorization": "Bearer nava_wrong"}).status_code == 401


def test_syscall_route_full_loop(api):
    client, hdr, _, nava = api
    r = client.post("/v1/syscalls", json={"task_id": nava.task, "tool": "test.echo", "args": {"text": "hi"}},
                    headers=hdr)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "committed" and body["receipt_id"]
    # the caller reads back its own call with all 12 steps
    g = client.get(f"/v1/syscalls/{body['id']}", headers=hdr).json()
    assert [s["step"] for s in g["steps"]] == list(range(1, 13))


def test_denied_tool_is_403_and_bad_body_400(api):
    client, hdr, _, nava = api
    r = client.post("/v1/syscalls", json={"task_id": nava.task, "tool": "sandbox.run",
                                          "args": {"workspace": "w", "argv": ["rm", "-rf", "/"]}}, headers=hdr)
    assert r.status_code == 403 and r.json()["risk_class"] == "critical"
    assert client.post("/v1/syscalls", json={"task_id": "nope", "tool": "t"}, headers=hdr).status_code == 400


def test_approval_flow_is_202(api):
    client, hdr, _, nava = api
    ws = nava.ws.path(nava.agent, "api")
    ws.mkdir(parents=True)
    (ws / "f").write_text("x")
    r = client.post("/v1/syscalls", json={"task_id": nava.task, "tool": "fs.delete", "mode": "ask",
                                          "args": {"workspace": "api", "path": "f"}}, headers=hdr)
    assert r.status_code == 202 and r.json()["approval_id"]


def test_inbox_and_syscall_isolation(api):
    client, hdr, hdr2, nava = api
    seq = client.post("/v1/bus/send", json={"to": nava.other, "channel": "jobs", "body": {"n": 1}},
                      headers=hdr).json()["seq"]
    assert seq >= 1
    mine = client.get("/v1/bus/inbox", headers=hdr).json()["messages"]
    theirs = client.get("/v1/bus/inbox", headers=hdr2).json()["messages"]
    assert mine == [] and [m["body"]["n"] for m in theirs] == [1]
    # another agent cannot read my syscall
    sid = client.post("/v1/syscalls", json={"task_id": nava.task, "tool": "test.echo", "args": {}},
                      headers=hdr).json()["id"]
    assert client.get(f"/v1/syscalls/{sid}", headers=hdr2).status_code == 404



def test_memory_subagent_and_plan_routes(api):
    client, hdr, hdr2, nava = api
    assert client.post("/v1/memory", json={"tier": "eternal", "key": "k", "value": {}}, headers=hdr).status_code == 400
    mid = client.post("/v1/memory", json={"tier": "episodic", "key": "k", "value": {"v": 1}}, headers=hdr).json()["id"]
    items = client.get("/v1/memory?tier=episodic&key=k", headers=hdr).json()["items"]
    assert [i["id"] for i in items] == [mid]
    assert client.get("/v1/memory?tier=episodic", headers=hdr2).json()["items"] == []      # not my memory
    assert client.get("/v1/bus/inbox?after=x", headers=hdr).status_code == 400
    assert client.post("/v1/bus/send", json={"to": "nope", "body": {}}, headers=hdr).status_code == 400
    assert {t["name"] for t in client.get("/v1/tools", headers=hdr).json()["tools"]} >= {"fs.read", "sandbox.run"}
    assert client.get("/v1/syscalls/not-a-uuid", headers=hdr).status_code == 400

    assert client.post("/v1/subagents", json={}, headers=hdr).status_code == 400
    child = client.post("/v1/subagents", json={"objective": "help", "ttl_s": 60, "denies": ["sandbox.*"]},
                        headers=hdr).json()
    chdr = {"authorization": f"Bearer {child['token']}"}
    assert client.post("/v1/subagents", json={"objective": "nested"}, headers=chdr).status_code == 403

    assert client.post("/v1/plans", json={"task_id": nava.task, "steps": []}, headers=hdr).status_code == 400
    pid = client.post("/v1/plans", json={"task_id": nava.task, "objective": "o", "steps": [
        {"tool": "fs.write", "args": {"workspace": "pl", "path": "a", "content": "1"}},
        {"tool": "test.echo", "args": {"text": "x"}}]}, headers=hdr).json()["id"]
    assert client.get(f"/v1/plans/{pid}", headers=hdr2).status_code == 404                  # not my plan
    assert client.post(f"/v1/plans/{pid}/pause", headers=hdr, json={}).json()["status"] == "paused"
    assert client.post(f"/v1/plans/{pid}/run", headers=hdr, json={}).json()["status"] == "paused"
    done = client.post(f"/v1/plans/{pid}/resume", headers=hdr, json={}).json()
    assert done["status"] == "completed"
    assert client.post(f"/v1/plans/{pid}/retry", headers=hdr, json={}).json()["status"] == "completed"
    assert client.post(f"/v1/plans/{pid}/explode", headers=hdr, json={}).status_code == 404
    assert client.get(f"/v1/plans/{pid}", headers=hdr).json()["steps"][0]["status"] == "done"
