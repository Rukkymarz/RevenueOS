"""Forage: search, install, learn (spec 4.1). The named Forage has no public repository; under
D1 this in-repo gateway on FastMCP (through mcp-common) is its implementation, and agent-discover
is the registry it installs into.

search  - the Official MCP Registry, Smithery and npm in parallel, plus the mcptoon and MCPfinder
          adapters and the ingested curated lists.
install - resolve an install plan, enrich it, run the selection policy, give the server its own
          identity and secret scope, register it in agent-discover behind the sandbox wrapper,
          and enable it: usable in the same session, no restart.
learn   - usage instructions built from the server's own indexed tool definitions, for the
          agent rule file."""
import json
import os
import re
from pathlib import Path

from . import policy, registry, sources
from .sandbox_exec import NAME_RE, ROOT

ALLOW_HTTP = frozenset(h for h in os.environ.get("DISCOVERY_ALLOW_HTTP_HOSTS", "").split(",") if h)
LAUNCHER_HOSTS = {"npx": ["registry.npmjs.org"], "uvx": ["pypi.org", "files.pythonhosted.org"],
                  "uv": ["pypi.org", "files.pythonhosted.org"]}


def local_name(name: str) -> str:
    n = re.sub(r"[^a-z0-9._-]+", "-", name.lower().split("/")[-1]).strip("-.") or "server"
    return n[:63]


def search(db, ad, query: str, limit: int = 10, *, mcptoon_home: str | None = None) -> dict:
    candidates, errors = sources.parallel_search(query, limit)
    for label, fn in (("mcptoon", lambda: sources.search_mcptoon(query, limit, mcptoon_home or "/tmp/mcptoon")),
                      ("mcpfinder", lambda: sources.search_mcpfinder(ad, query, limit)),
                      ("curated", lambda: sources.search_curated(db, query, limit))):
        try:
            candidates += fn()
        except Exception as e:  # noqa: BLE001 - an adapter being down narrows the search, it does not fail it
            errors[label] = f"{type(e).__name__}: {str(e)[:160]}"
    seen, merged = set(), []
    for c in candidates:
        key = (c.get("source"), (c.get("name") or "").lower())
        if key not in seen:
            seen.add(key)
            merged.append(c)
    registry.event(db, "forage", "searched", {"query": query, "results": len(merged), "errors": errors})
    return {"query": query, "candidates": merged, "errors": errors}


def _from_plan(plan: dict, source: str) -> dict:
    env_keys = [r["key"] for r in plan.get("requirements", []) if r.get("kind") in ("env", "secret") and r.get("key")]
    checks = (plan.get("provenance") or {}).get("checks") or []
    status = "fail" if any(c.get("status") == "fail" for c in checks) else "pass"
    return {"source": source, "name": plan.get("registry_name") or plan.get("server"),
            "transport": "stdio" if plan.get("command") else (plan.get("transport") or "streamable-http"),
            "command": plan.get("command"), "args": plan.get("args") or [], "url": plan.get("url"),
            "version": plan.get("version"), "env_keys": env_keys,
            "repo": sources._repo(((plan.get("input") or {}).get("repository")) or ""),
            "package": (plan.get("input") or {}).get("package_name"),
            "package_type": "npm" if plan.get("command") == "npx" else None,
            "provenance": {"status": status, "checks": checks}, "warnings": plan.get("warnings") or [],
            "description": plan.get("description", "")}


def install(db, ad, secrets, spec: dict, *, agent_id: str | None = None, task_id: str | None = None) -> dict:
    """spec: {source, name, version?} for a registry/npm/pypi entry, or a full manual candidate
    {source: manual|pinned, name, transport, command/args | url, version, checksum, license,
    last_push}. Optional: local_name, secrets {ENV_KEY: keychain://ref}, egress_hosts [host],
    observe_days, approved_by (pinned bootstrap only)."""
    source = spec.get("source", "registry")
    name = local_name(spec.get("local_name") or spec["name"])
    if not NAME_RE.match(name):
        return {"status": "denied", "reasons": [f"bad server name {name!r}"]}

    held = db.scalar("SELECT health_status AS h FROM tool_installations WHERE mcp_server_name = $n "
                     "ORDER BY created_at DESC LIMIT 1", n=name)
    if held == "QUARANTINED":     # only a human release clears a quarantine; a reinstall does not
        registry.event(db, name, "policy_denied", {"reasons": ["server is quarantined"]}, task_id=task_id, agent_id=agent_id)
        return {"status": "denied", "server": name, "reasons": ["server is quarantined; a human must release it"]}

    if source in ("registry", "npm", "pypi"):
        plan = ad.plan(source, spec["name"], spec.get("version"), name)
        if plan.get("blocked"):
            registry.event(db, name, "policy_denied", {"reasons": [plan["blocked"]], "stage": "plan"},
                           task_id=task_id, agent_id=agent_id)
            return {"status": "denied", "server": name, "reasons": [plan["blocked"]]}
        cand = _from_plan(plan, source)
    else:
        cand = {k: spec.get(k) for k in ("source", "name", "transport", "command", "args", "url", "version",
                                         "checksum", "license", "last_push", "repo", "description")}
        cand["args"] = cand["args"] or []
    cand["secrets"] = spec.get("secrets") or {}
    for k in ("license", "last_push", "checksum"):
        if spec.get(k) and not cand.get(k):
            cand[k] = spec[k]
    cand = sources.enrich(cand)

    verdict = policy.evaluate(cand, allow_http_hosts=ALLOW_HTTP)
    if not verdict.allowed:
        registry.event(db, name, "policy_denied", {"reasons": verdict.reasons, "score": verdict.score},
                       task_id=task_id, agent_id=agent_id)
        return {"status": "denied", "server": name, "reasons": verdict.reasons, "policy_score": verdict.score}

    # 4.7: the server's own identity. Its secrets and its egress rules hang off this row and no other.
    ident = db.scalar("INSERT INTO agents(name, role, framework, budget_monthly) VALUES ($n, 'mcp-server', 'mcp', 0) "
                      "ON CONFLICT (name) DO UPDATE SET updated_at = now() RETURNING id", n=f"mcp:{name}")
    stdio = cand["transport"] == "stdio"
    hosts = sorted(set(spec.get("egress_hosts") or []) | set(LAUNCHER_HOSTS.get((cand.get("command") or "").rsplit("/", 1)[-1], []))) if stdio else []
    for h in hosts:
        db.rows("INSERT INTO egress_rules(agent_id, host, created_by) VALUES ($a::uuid, $h, 'discovery') "
                "ON CONFLICT DO NOTHING RETURNING id", a=ident, h=h.lower())
    base = Path(ROOT) / name
    base.mkdir(parents=True, exist_ok=True)
    (base / "egress.json").unlink(missing_ok=True)
    if hosts:
        (base / "egress.json").write_text(json.dumps({"agent_id": ident, "hosts": hosts}))

    env_keys = sorted(set(cand.get("env_keys") or []) | set(cand["secrets"]))
    if stdio:
        wrapper_args = [name] + [x for k in env_keys for x in ("--env", k)] + ["--", cand["command"], *cand["args"]]
        ad_spec = {"name": name, "transport": "stdio", "command": "revenueos-mcp-sandbox", "args": wrapper_args,
                   "description": cand.get("description") or "", "source": "manual"}
    else:
        ad_spec = {"name": name, "transport": "sse" if cand["transport"] == "sse" else "streamable-http",
                   "url": cand["url"], "description": cand.get("description") or "", "source": "manual"}
    for k in ("package", "version"):
        if cand.get(k):
            ad_spec["package_name" if k == "package" else "package_version"] = cand[k]

    old = ad.find(name)
    if old is not None:
        ad.delete(old["id"])
    entry = ad.create(ad_spec, enabled=False)
    for key, ref in cand["secrets"].items():       # by reference in our records; the value goes only
        value = secrets.get(ref)                   # into agent-discover's per-server secret store
        if value is None:
            ad.delete(entry["id"])
            return {"status": "denied", "server": name, "reasons": [f"secret {ref} is not provisioned"]}
        ad.put_secret(entry["id"], key, value)

    install_spec = {"transport": cand["transport"], "command": cand.get("command"), "args": cand.get("args"),
                    "url": cand.get("url"), "secrets": cand["secrets"], "egress_hosts": hosts,
                    "repo": cand.get("repo"), "sandboxed": stdio, "requested_name": spec["name"]}
    version = cand.get("version") or "remote"
    observe = int(spec.get("observe_days") or 0)
    db.rows(
        "INSERT INTO tool_installations(mcp_server_name, registry_source, version, checksum, license, resolution_mode, "
        "policy_score, installed_by_agent, agent_id, install_spec, observe_until) "
        "VALUES ($n, $src, $v, $c, $l, 'upstream', $p::jsonb, nullif($by, '')::uuid, $ident::uuid, $spec::jsonb, "
        "CASE WHEN $obs::integer > 0 THEN now() + make_interval(days => $obs::integer) END) "
        "ON CONFLICT (mcp_server_name, version) DO UPDATE SET policy_score = EXCLUDED.policy_score, "
        "install_spec = EXCLUDED.install_spec, checksum = EXCLUDED.checksum RETURNING id",
        n=name, src=source, v=version, c=cand.get("checksum") or "remote:no-artifact", l=cand["license"],
        p=json.dumps(verdict.score), by=agent_id or "", ident=ident, spec=json.dumps(install_spec), obs=observe)
    registry.event(db, name, "installed", {"source": source, "version": version, "transport": cand["transport"],
                                           "sandboxed": stdio, "egress_hosts": hosts},
                   task_id=task_id, agent_id=agent_id)

    out = {"status": "installed", "server": name, "install_status": "experimental", "version": version,
           "policy_score": verdict.score}
    if spec.get("enable", True):
        try:
            registry.set_active(db, ad, name, True)
            out["tools"] = [t.get("name") for t in ad.tools(entry["id"])]
        except Exception as e:  # noqa: BLE001 - installed but could not start: recorded, not hidden
            registry.mark_unhealthy(db, ad, name, "health_failed", {"enable": f"{type(e).__name__}: {str(e)[:300]}"})
            out.update(status="installed_unhealthy", error=str(e)[:300])
    if spec.get("approved_by"):
        registry.approve(db, name, spec["approved_by"])
        out["install_status"] = "approved"
    return out


def learn(db, ad, server: str) -> dict:
    """Usage instructions for the agent rule file, so the next session already knows the tool."""
    inst = registry.installation(db, server)
    entry = ad.find(server)
    if entry is None:
        raise registry.NotInstalled(server)
    lines = [f"## MCP server `{server}` (installed by Forage)", "",
             f"- Governance status: **{inst['status']}**. "
             + ("Usable on experimental tasks only until a human approves it (INV-10)."
                if inst["status"] == "experimental" else "Usable on production tasks."),
             f"- Call a tool with the syscall `mcp.call`: `{{\"server\": \"{server}\", \"tool\": \"<name>\", \"arguments\": {{...}}}}`.",
             "- Tools:"]
    tools = ad.tools(entry["id"])
    for t in tools:
        schema = t.get("input_schema") or t.get("inputSchema") or {}
        req = ", ".join(schema.get("required") or []) or "none"
        props = ", ".join(sorted((schema.get("properties") or {}).keys())) or "none"
        desc = (t.get("description") or "").strip().splitlines()[0][:200] if t.get("description") else ""
        lines.append(f"  - `{t.get('name')}` — {desc} (required: {req}; arguments: {props})")
    text = "\n".join(lines) + "\n"
    registry.event(db, server, "learned", {"tools": len(tools)})
    return {"server": server, "marker": f"<!-- forage:{server} -->", "instructions": text}
