"""HTTP surface of the pm service (C06): projects, Spec/Plan/Rules approval, the task tree,
FIST lifecycle verbs, slice runs, mirrors and the roster. Postgres decides; this only asks."""
import os
from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from revenueos_common.db import Database, DatabaseError
from revenueos_common.registry import components_for, config_loaded
from revenueos_common.secrets import KeychainStore, SecretResolver
from revenueos_common.service import create_app

from . import COMPONENT, SERVICE, lifecycle, mirrors, plan, roster
from .runner import SliceRunner
from .scripted import NoopPlanner, RecomputeChecker, ScriptedExecutor

_state: dict = {}


def db() -> Database:
    if "db" not in _state:
        _state["db"] = Database(actor="pm")
    return _state["db"]


def secrets() -> SecretResolver:
    if "secrets" not in _state:
        _state["secrets"] = SecretResolver(KeychainStore(os.environ.get("REVENUEOS_KEYCHAIN_DIR", "/run/revenueos/keychain")))
    return _state["secrets"]


def mission_control() -> mirrors.MissionControl:
    if "mc" not in _state:
        s = secrets()
        _state["mc"] = mirrors.MissionControl(key=lambda: s.get("keychain://mission-control-api-key"),
                                              user=lambda: s.get("keychain://mission-control-user"),
                                              password=lambda: s.get("keychain://mission-control-password"))
    return _state["mc"]


def tracker() -> mirrors.FileTracker:
    return _state.setdefault("tracker", mirrors.FileTracker(os.environ.get("PM_TRACKER_DIR", "/var/lib/revenueos/tracker")))


def _fail(e: Exception) -> JSONResponse:
    if isinstance(e, DatabaseError):
        return JSONResponse({"status": "refused", "reason": e.message[:400]}, status_code=409)
    if isinstance(e, (plan.PlanError, lifecycle.LifecycleError)):
        return JSONResponse({"status": "invalid", "reason": str(e)}, status_code=422)
    if isinstance(e, (KeyError, ValueError)):
        return JSONResponse({"status": "invalid", "reason": f"{type(e).__name__}: {str(e)[:300]}"}, status_code=400)
    return JSONResponse({"status": "failed", "reason": f"{type(e).__name__}: {str(e)[:300]}"}, status_code=502)


def _route(fn):
    async def handler(request: Request) -> JSONResponse:
        import anyio
        body = await request.json() if request.method == "POST" and await request.body() else {}
        try:
            return JSONResponse(await anyio.to_thread.run_sync(lambda: fn(request, body)))
        except Exception as e:  # noqa: BLE001 - every failure is a typed JSON answer
            return _fail(e)
    return handler


def r_project(_, b):
    return {"id": plan.create_project(db(), b["name"], b["business_line"], b.get("premise_bundle_id"))}


def r_artifact(req, b):
    return {"version": plan.submit_artifact(db(), req.path_params["pid"], b["kind"], b["content"], b.get("author", "agent:planner"))}


def r_approve_artifact(req, b):
    p = req.path_params
    return plan.approve_artifact(db(), p["pid"], p["kind"], int(p["version"]), b.get("approved_by", ""))


def r_plan(req, b):
    ids = plan.create_tree(db(), req.path_params["pid"], b["plan"], b.get("actor", "agent:planner"))
    return {"tasks": ids, "artifacts_approved": plan.artifacts_approved(db(), req.path_params["pid"])}


def r_tree(req, _):
    return {"tree": plan.tree(db(), req.path_params["pid"]), "artifacts_approved": plan.artifacts_approved(db(), req.path_params["pid"])}


def r_verb(req, b):
    p, actor = req.path_params, b.get("actor", "agent:fist")
    t, verb = p["tid"], p["verb"]
    if verb not in lifecycle.VERBS:
        raise ValueError(f"verb must be one of {lifecycle.VERBS}")
    d = db()
    if verb == "publish":
        return {"state": lifecycle.publish(d, t, b["premise_bundle_id"], actor)}
    if verb == "claim":
        return {"claimed": lifecycle.claim(d, t, b["agent_id"], actor)}
    if verb == "plan":
        return {"state": lifecycle.plan(d, t, actor)}
    if verb == "execute":
        return {"state": lifecycle.execute(d, t, actor)}
    if verb == "submit":
        return {"state": lifecycle.submit(d, t, b["evidence"], actor)}
    if verb in ("verify", "reject"):
        return {"state": lifecycle.verify(d, t, b["verifier_agent_id"], b["results"], actor)}
    if verb == "retry":
        return {"state": lifecycle.retry(d, t, actor)}
    if verb == "pause":
        return {"state": lifecycle.pause(d, t, actor)}
    if verb == "resume":
        return {"state": lifecycle.resume(d, t, actor)}
    if verb == "archive":
        lifecycle.archive(d, t, actor)
        return {"archived": True}
    lifecycle.delete(d, t, actor)
    return {"deleted": True}


def r_run_slice(req, b):
    """Auto Mode machinery with the scripted components (ADR-0005)."""
    ex = ScriptedExecutor(float(b.get("cost_per_task", 0.01)), set(b.get("fail_first") or ()))
    runner = SliceRunner(db(), planner=NoopPlanner(), executor=ex, checkers=[RecomputeChecker("gitreins"), RecomputeChecker("omega")],
                         executor_agent=b["executor_agent_id"], verifier_agent=b["verifier_agent_id"],
                         premise_bundle_id=b["premise_bundle_id"], max_retries=int(b.get("max_retries", 1)))
    rep = runner.run(req.path_params["sid"])
    return {"slice_id": rep.slice_id, "status": rep.status, "completed": rep.completed, "steps": rep.steps, "reason": rep.reason}


def r_sync(req, b):
    targets = set(b.get("targets") or ["mission-control", "llm-tracker"])
    return mirrors.sync(db(), req.path_params["tid"], mc=mission_control() if "mission-control" in targets else None,
                        tracker=tracker() if "llm-tracker" in targets else None)


def r_visibility(req, _):
    tid = req.path_params["tid"]
    ext = db().scalar("SELECT external_id AS e FROM task_mirrors WHERE task_id = $t::uuid AND system = 'mission-control'", t=tid)
    if not ext:
        raise plan.PlanError("task is not mirrored in Mission Control")
    return {"external_id": ext, "visible": mission_control().visible_everywhere(ext, tid)}


def r_roster(_, __):
    return {"agents": roster.load()}


async def info(_: Request) -> JSONResponse:
    return JSONResponse({"service": SERVICE, "component": COMPONENT, "hosts": components_for(COMPONENT)})


app = create_app(SERVICE, checks={"component_map": config_loaded}, routes=[
    Route("/v1/info", info),
    Route("/v1/roster", _route(r_roster)),
    Route("/v1/projects", _route(r_project), methods=["POST"]),
    Route("/v1/projects/{pid}/artifacts", _route(r_artifact), methods=["POST"]),
    Route("/v1/projects/{pid}/artifacts/{kind}/{version}/approve", _route(r_approve_artifact), methods=["POST"]),
    Route("/v1/projects/{pid}/plan", _route(r_plan), methods=["POST"]),
    Route("/v1/projects/{pid}/tree", _route(r_tree)),
    Route("/v1/tasks/{tid}/{verb}", _route(r_verb), methods=["POST"]),
    Route("/v1/slices/{sid}/run", _route(r_run_slice), methods=["POST"]),
    Route("/v1/tasks/{tid}/mirror/sync", _route(r_sync), methods=["POST"]),
    Route("/v1/tasks/{tid}/mirror/visibility", _route(r_visibility)),
])
