"""HTTP surface of the discovery service (C04): Forage search/install/learn, the governance
operations (approve, activate, probe, metrics) and the one governed call path that the NAVA
gateway's `mcp.call` syscall uses. Agents never reach this service directly: runtime-os does,
after its own 12 steps. Human operations (approve, release) name their approver."""
import json
import os
import threading
import time
from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from revenueos_common.db import Database, DatabaseError
from revenueos_common.registry import components_for, config_loaded
from revenueos_common.secrets import KeychainStore, SecretResolver
from revenueos_common.service import create_app

from . import COMPONENT, SERVICE, forage, registry, sources
from .agent_discover import AgentDiscover, AgentDiscoverError
from .monitor import TraceMonitor
from .sandbox_exec import ROOT

_state: dict = {}


def db() -> Database:
    return _state.setdefault("db", Database(actor="discovery"))


def ad() -> AgentDiscover:
    return _state.setdefault("ad", AgentDiscover())


def secrets() -> SecretResolver:
    return _state.setdefault("secrets", SecretResolver(KeychainStore(
        os.environ.get("REVENUEOS_KEYCHAIN_DIR", "/run/revenueos/keychain"))))


def _fail(e: Exception) -> JSONResponse:
    if isinstance(e, registry.ActivationRefused):
        return JSONResponse({"status": "refused", "reason": str(e)}, status_code=403)
    if isinstance(e, registry.NotInstalled):
        return JSONResponse({"status": "not_installed", "reason": f"server {e.args[0]!r} is not installed"}, status_code=404)
    if isinstance(e, PermissionError):
        return JSONResponse({"status": "refused", "reason": str(e)}, status_code=403)
    if isinstance(e, DatabaseError):
        return JSONResponse({"status": "refused", "reason": e.message()[:400]}, status_code=409)
    if isinstance(e, (AgentDiscoverError, KeyError, ValueError)):
        return JSONResponse({"status": "failed", "reason": f"{type(e).__name__}: {str(e)[:400]}"}, status_code=400)
    return JSONResponse({"status": "failed", "reason": f"{type(e).__name__}: {str(e)[:400]}"}, status_code=502)


def _route(fn):
    async def handler(request: Request) -> JSONResponse:
        body = await request.json() if request.method == "POST" and await request.body() else {}
        import anyio
        try:
            return JSONResponse(await anyio.to_thread.run_sync(lambda: fn(request, body)))
        except Exception as e:  # noqa: BLE001 - every failure becomes a typed JSON answer
            return _fail(e)
    return handler


def r_search(_, b):
    return forage.search(db(), ad(), b["query"], int(b.get("limit", 10)), mcptoon_home=str(Path(ROOT) / ".mcptoon"))


def r_install(_, b):
    return forage.install(db(), ad(), secrets(), b["spec"], agent_id=b.get("agent_id"), task_id=b.get("task_id"))


def r_learn(_, b):
    return forage.learn(db(), ad(), b["server"])


def r_call(_, b):
    out = registry.call(db(), ad(), server=b["server"], tool=b["tool"], arguments=b.get("arguments") or {},
                        task_id=b["task_id"], agent_id=b.get("agent_id"), timeout_s=float(b.get("timeout_s", 60)))
    return {"status": "ok", "result": out}


def r_activate(req, b):
    return registry.activate(db(), ad(), server=req.path_params["name"], task_id=b["task_id"], agent_id=b.get("agent_id"))


def r_deactivate(req, b):
    return {"server": req.path_params["name"], "deactivated": registry.deactivate(db(), req.path_params["name"], b.get("task_id"))}


def r_approve(req, b):
    return registry.approve(db(), req.path_params["name"], b.get("approved_by", ""), b.get("status", "approved"))


def r_release(req, b):
    return registry.release(db(), req.path_params["name"], b.get("approved_by", ""))


def r_probe(req, _):
    return registry.probe(db(), ad(), req.path_params["name"])


def r_metrics(req, _):
    return {"server": req.path_params["name"], "metrics": registry.metrics(ad(), req.path_params["name"])}


def r_events(req, _):
    return {"events": db().rows("SELECT kind, detail, task_id, created_at FROM tool_events WHERE mcp_server_name = $s "
                                "ORDER BY created_at, id", s=req.path_params["name"])}


def r_servers(_, __):
    return {"servers": registry.listing(db())}


def r_ingest(_, b):
    wanted = b.get("sources")
    return {"ingested": {s["name"]: sources.ingest(db(), s) for s in sources.CURATED if not wanted or s["name"] in wanted}}


def r_manifest(_, __):
    return sources.mcptoon_manifest(str(Path(ROOT) / ".mcptoon"), ad().base)


def r_details(req, _):
    return sources.mcpfinder_details(ad(), req.query_params["name"])


async def info(_: Request) -> JSONResponse:
    return JSONResponse({"service": SERVICE, "component": COMPONENT, "hosts": components_for(COMPONENT)})


def daemon_ok() -> bool:
    return "ad" not in _state or os.environ.get("DISCOVERY_NO_DAEMON") == "1" or ad().healthy()


app = create_app(SERVICE, checks={"component_map": config_loaded, "agent_discover": daemon_ok}, routes=[
    Route("/v1/info", info),
    Route("/v1/forage/search", _route(r_search), methods=["POST"]),
    Route("/v1/forage/install", _route(r_install), methods=["POST"]),
    Route("/v1/forage/learn", _route(r_learn), methods=["POST"]),
    Route("/v1/call", _route(r_call), methods=["POST"]),
    Route("/v1/servers", _route(r_servers)),
    Route("/v1/servers/{name}/activate", _route(r_activate), methods=["POST"]),
    Route("/v1/servers/{name}/deactivate", _route(r_deactivate), methods=["POST"]),
    Route("/v1/servers/{name}/approve", _route(r_approve), methods=["POST"]),
    Route("/v1/servers/{name}/release", _route(r_release), methods=["POST"]),
    Route("/v1/servers/{name}/probe", _route(r_probe), methods=["POST"]),
    Route("/v1/servers/{name}/metrics", _route(r_metrics)),
    Route("/v1/servers/{name}/events", _route(r_events)),
    Route("/v1/sources/ingest", _route(r_ingest), methods=["POST"]),
    Route("/v1/mcptoon/manifest", _route(r_manifest)),
    Route("/v1/mcpfinder/details", _route(r_details)),
])


# -- process lifecycle (called from __main__) ---------------------------------------------------
def write_sandbox_env() -> None:
    """What the sandbox wrapper needs to open an identity-pinned egress session. agent-discover
    launches the wrapper with a minimal environment, so it reads this file instead. Names and
    paths only: no secret value is written."""
    Path(ROOT).mkdir(parents=True, exist_ok=True)
    env = {k: os.environ[k] for k in ("PGHOST", "PGPORT", "PGUSER", "PGDATABASE", "PGPASSFILE",
                                      "REVENUEOS_KEYCHAIN_DIR", "REVENUEOS_CONFIG_DIR") if k in os.environ}
    env.setdefault("REVENUEOS_KEYCHAIN_DIR", "/run/revenueos/keychain")
    (Path(ROOT) / "sandbox-env.json").write_text(json.dumps(
        {"env": env, "egress_proxy": os.environ.get("EGRESS_PROXY", "envoy:10000")}))


PINNED = [   # named, pinned components registered at start (docs/PINS.md)
    {"source": "pinned", "name": "mcpfinder", "transport": "stdio", "command": "node",
     "args": ["/opt/mcpfinder/packages/mcp-server/dist/cli.js"], "version": "2.0.2",
     "checksum": "sha256:git-4c9e2f421a4bfda47e01052ce21931d9b6026b27", "license": "AGPL-3.0",
     "repo": "mcpfinder/mcpfinder", "description": "MCPfinder: multi-registry search, trust signals, install-ready JSON",
     "egress_hosts": ["mcpfinder.dev", "registry.modelcontextprotocol.io", "glama.ai", "registry.npmjs.org", "api.github.com"],
     "last_push": "2026-11-13", "approved_by": "bootstrap:docs/PINS.md"},
    # Addendum F: api-anything is registered experimental and may be approved only after 14 days.
    {"source": "pinned", "name": "api-anything", "transport": "stdio", "command": "npx",
     "args": ["-y", "api-anything@0.4.0"], "version": "0.4.0",
     "checksum": "sha256:git-d40abd44f171c5cc444f1ac6b947afefa8605b78", "license": "MIT",
     "repo": "goodnight000/api-anything", "description": "api-anything: call websites as APIs (fallback extractor, Phase 6)",
     "last_push": "2026-11-13", "observe_days": 14, "enable": False},
]


def bootstrap() -> None:
    for spec in PINNED:
        try:
            if db().scalar("SELECT 1 AS x FROM tool_installations WHERE mcp_server_name = $n AND version = $v",
                           n=spec["name"], v=spec["version"]) and ad().find(spec["name"]):
                continue
            forage.install(db(), ad(), secrets(), dict(spec))
        except Exception as e:  # noqa: BLE001 - a pinned server failing to register must not stop discovery
            print(f"discovery: bootstrap of {spec['name']} failed: {type(e).__name__}: {e}", flush=True)


def background(interval: float = 2.0, probe_every: float = 60.0) -> None:  # pragma: no cover - long-running
    monitor, last_probe = TraceMonitor(db(), ad()), 0.0
    while True:
        try:
            monitor.scan()
            if time.time() - last_probe > probe_every:
                last_probe = time.time()
                for s in db().rows("SELECT DISTINCT mcp_server_name AS name FROM tool_installations WHERE active"):
                    registry.probe(db(), ad(), s["name"])
        except Exception as e:  # noqa: BLE001
            print(f"discovery: background pass failed: {type(e).__name__}: {e}", flush=True)
        time.sleep(interval)


def start() -> None:  # pragma: no cover - process entrypoint
    write_sandbox_env()
    ad().start_daemon(os.environ.get("AGENT_DISCOVER_DATA_DIR", "/var/lib/revenueos/agent-discover"),
                      os.environ.get("DISCOVERY_REGISTRY_URL"))
    bootstrap()
    threading.Thread(target=background, daemon=True, name="discovery-background").start()
