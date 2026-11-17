"""Mirrors of the task record (spec 5.1, 5.3, 5.6). Postgres is authoritative; Mission Control, Piyaz
and the filesystem tracker are views kept in step. A mirror that is down never blocks a task: the
failure is returned and the next sync repairs it. Secrets are resolved by reference at call time."""
import json
import os
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

MC_STATUS = {"DRAFT": "inbox", "RESEARCHED": "inbox", "PLANNED": "assigned", "AWAITING_APPROVAL": "assigned",
             "EXECUTING": "in_progress", "EVIDENCE_SUBMITTED": "quality_review", "VERIFYING": "quality_review",
             "QC_PASSED": "quality_review", "FAILED_QC": "in_progress", "COMPLETED": "done", "BLOCKED": "in_progress",
             "BUDGET_HALTED": "in_progress", "AWAITING_HUMAN_APPROVAL": "assigned", "CANCELLED": "done"}


class MirrorError(RuntimeError):
    pass


def _http(method: str, url: str, headers: dict, body=None, timeout: int = 30):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"content-type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raise MirrorError(f"{method} {url}: HTTP {e.code} {e.read()[:200]!r}") from None
    except (OSError, ValueError) as e:
        raise MirrorError(f"{method} {url}: {type(e).__name__}: {e}") from None


class MissionControl:
    """Mission Control's REST, CLI, MCP and web-session interfaces over one task."""

    def __init__(self, base: str | None = None, key=None, *, scripts: str | None = None, user=None, password=None):
        self.base = (base or os.environ.get("MISSION_CONTROL_URL", "http://mission-control:3000")).rstrip("/")
        self._key, self._user, self._password = key, user, password
        self.scripts = scripts or os.environ.get("MC_SCRIPTS", "/opt/mission-control/scripts")

    def key(self) -> str:
        k = self._key() if callable(self._key) else self._key
        if not k:
            raise MirrorError("Mission Control API key is not provisioned")
        return k

    def rest(self, method: str, path: str, body=None):
        return _http(method, self.base + path, {"x-api-key": self.key()}, body)[1]

    def upsert(self, task: dict, external_id: str | None) -> str:
        payload = {"title": task["objective"][:200], "description": task["objective"], "status": MC_STATUS.get(task["state"], "inbox"),
                   "metadata": {"revenueos_task_id": task["id"], "revenueos_state": task["state"], "project_id": task.get("project_id")},
                   "tags": ["revenueos", task["task_class"]]}
        if external_id:
            self.rest("PUT", f"/api/tasks/{external_id}", payload)
            return external_id
        out = self.rest("POST", "/api/tasks", {**payload, "created_by": "revenueos-pm"})
        t = out.get("task") or out
        return str(t["id"])

    def get(self, external_id: str) -> dict:
        out = self.rest("GET", f"/api/tasks/{external_id}")
        return out.get("task") or out

    def _env(self) -> dict:
        return {"PATH": os.environ.get("PATH", ""), "HOME": "/tmp", "MC_URL": self.base, "MC_API_KEY": self.key()}

    @staticmethod
    def _unwrap(out: dict) -> dict:
        """mc-cli --json prints {ok, status, data}; the task sits under data (and often under data.task)."""
        out = out.get("data", out) if isinstance(out, dict) else out
        return out.get("task") or out

    def via_cli(self, external_id: str) -> dict:
        r = subprocess.run(["node", f"{self.scripts}/mc-cli.cjs", "tasks", "get", "--id", str(external_id), "--json"],
                           capture_output=True, text=True, timeout=60, env=self._env())
        if r.returncode != 0:
            raise MirrorError(f"mc-cli exit {r.returncode}: {r.stderr[:200]} {r.stdout[:200]}")
        return self._unwrap(json.loads(r.stdout))

    def via_mcp(self, external_id: str) -> dict:
        """The stdio MCP server, driven as a client does: the server exits when stdin closes, so stdin
        stays open until the tool reply for request 2 has arrived."""
        msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                                                                              "clientInfo": {"name": "revenueos-pm", "version": "1"}}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "mc_get_task", "arguments": {"id": int(external_id)}}}]
        p = subprocess.Popen(["node", f"{self.scripts}/mc-mcp-server.cjs"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, env=self._env())
        try:
            p.stdin.write("\n".join(json.dumps(m) for m in msgs) + "\n")
            p.stdin.flush()
            deadline = time.time() + 60
            while time.time() < deadline:
                line = p.stdout.readline()
                if not line:
                    break
                try:
                    m = json.loads(line)
                except ValueError:
                    continue
                if m.get("id") == 2:
                    if "error" in m or m.get("result", {}).get("isError"):
                        raise MirrorError(f"mcp: {json.dumps(m)[:200]}")
                    return self._unwrap(json.loads(m["result"]["content"][0]["text"]))
            raise MirrorError("mcp: no reply")
        finally:
            p.kill()
            p.wait()

    def via_web_session(self, external_id: str) -> dict:
        """What the dashboard's task panel does: sign in, then read the task with the session cookie."""
        creds = {"username": self._user() if callable(self._user) else self._user,
                 "password": self._password() if callable(self._password) else self._password}
        req = urllib.request.Request(self.base + "/api/auth/login", data=json.dumps(creds).encode(), method="POST",
                                     headers={"content-type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                cookies = [c.split(";")[0] for c in r.headers.get_all("Set-Cookie") or []]
        except (urllib.error.URLError, OSError) as e:
            raise MirrorError(f"web login: {e}") from None
        out = _http("GET", f"{self.base}/api/tasks/{external_id}", {"cookie": "; ".join(cookies)})[1]
        return out.get("task") or out

    def visible_everywhere(self, external_id: str, task_id: str) -> dict:
        res = {}
        for name, fn in (("rest", self.get), ("cli", self.via_cli), ("mcp", self.via_mcp), ("web", self.via_web_session)):
            try:
                t = fn(external_id)
                meta = t.get("metadata") or {}
                if isinstance(meta, str):
                    meta = json.loads(meta or "{}")
                res[name] = meta.get("revenueos_task_id") == task_id
            except Exception as e:  # noqa: BLE001
                res[name] = f"{type(e).__name__}: {str(e)[:160]}"
        return res


class Piyaz:
    """Piyaz is a remote MCP server (Streamable HTTP, OAuth 2.1). The bearer comes from the
    OAuth grant the operator made; this adapter holds a reference, never the token."""

    def __init__(self, base: str | None = None, token=None):
        self.base = (base or os.environ.get("PIYAZ_URL", "http://piyaz:3000")).rstrip("/")
        self._token = token

    def call(self, tool: str, args: dict):
        tok = self._token() if callable(self._token) else self._token
        if not tok:
            raise MirrorError("Piyaz OAuth grant is not provisioned")
        h = {"authorization": f"Bearer {tok}", "accept": "application/json, text/event-stream"}
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": args}}
        status, out = _http("POST", self.base + "/api/mcp", h, body)
        if "error" in out:
            raise MirrorError(f"piyaz {tool}: {out['error']}")
        return out.get("result", out)


class FileTracker:
    """5.6: filesystem-as-database mode for deployments that cannot run SQLite. One JSON file per
    task, written atomically; a patch is a read-modify-write under the same rename."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, task_id: str) -> Path:
        if not task_id.replace("-", "").isalnum():
            raise MirrorError("bad task id")
        return self.root / f"{task_id}.json"

    def put(self, task: dict) -> str:
        p = self._path(task["id"])
        fd, tmp = tempfile.mkstemp(dir=self.root, suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            json.dump(task, f, sort_keys=True, default=str)
        os.replace(tmp, p)
        return p.name

    def get(self, task_id: str) -> dict | None:
        p = self._path(task_id)
        return json.loads(p.read_text()) if p.exists() else None

    def patch(self, task_id: str, **fields) -> dict:
        cur = self.get(task_id)
        if cur is None:
            raise MirrorError(f"unknown task {task_id}")
        cur.update(fields)
        self.put(cur)
        return cur

    def list(self) -> list[dict]:
        return [json.loads(p.read_text()) for p in sorted(self.root.glob("*.json"))]


def task_row(db, task_id: str) -> dict:
    return db.one("SELECT id, project_id, slice_id, objective, task_class, state::text AS state, cost_estimate, cost_actual, "
                  "executor_agent_id, verifier_agent_id FROM tasks WHERE id = $t::uuid", t=task_id)


def sync(db, task_id: str, *, mc: MissionControl | None = None, piyaz: Piyaz | None = None, tracker: FileTracker | None = None) -> dict:
    """Write the task to every configured mirror and record where it landed. Errors are returned."""
    task = task_row(db, task_id)
    out: dict = {}
    for system, target in (("mission-control", mc), ("piyaz", piyaz), ("llm-tracker", tracker)):
        if target is None:
            continue
        try:
            ext = db.scalar("SELECT external_id AS e FROM task_mirrors WHERE task_id = $t::uuid AND system = $s", t=task_id, s=system)
            if system == "mission-control":
                new = target.upsert(task, ext)
            elif system == "piyaz":
                res = target.call("create_task" if not ext else "update_task",
                                  {"title": task["objective"][:200], "state": task["state"], "ref": ext or task_id})
                new = str((res or {}).get("id") or ext or task_id)
            else:
                new = target.put(task)
            db.rows("INSERT INTO task_mirrors(task_id, system, external_id) VALUES ($t::uuid, $s, $e) ON CONFLICT (task_id, system) "
                    "DO UPDATE SET external_id = EXCLUDED.external_id, synced_at = now() RETURNING task_id", t=task_id, s=system, e=new)
            out[system] = new
        except Exception as e:  # noqa: BLE001 - a down or misbehaving mirror never blocks the task
            out[system] = f"error: {type(e).__name__}: {e}"
    return out
