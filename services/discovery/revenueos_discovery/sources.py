"""Where Forage looks (spec 4.1, 4.3, 4.4): the Official MCP Registry, Smithery and npm searched
in parallel; the mcptoon CLI and the MCPfinder server as adapters; and the curated lists ingested
into `discovery_entries`. Every endpoint is an environment variable so the acceptance stack can
point them at a local fixture; production uses the real ones."""
import json
import os
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

REGISTRY = os.environ.get("DISCOVERY_REGISTRY_URL", "https://registry.modelcontextprotocol.io").rstrip("/")
SMITHERY = os.environ.get("DISCOVERY_SMITHERY_URL", "https://registry.smithery.ai").rstrip("/")
NPM = os.environ.get("DISCOVERY_NPM_URL", "https://registry.npmjs.org").rstrip("/")
GITHUB_API = os.environ.get("DISCOVERY_GITHUB_API", "https://api.github.com").rstrip("/")
RAW = os.environ.get("DISCOVERY_RAW_BASE", "https://raw.githubusercontent.com").rstrip("/")

# 4.4 curated sources, pinned (docs/PINS.md "Discovery data sources").
CURATED = [
    {"name": "official-mcp-registry", "kind": "registry", "url": REGISTRY, "commit_sha": None},
    {"name": "awesome-mcp-servers-2026", "kind": "awesome-list", "repo": "punkpeye/awesome-mcp-servers",
     "commit_sha": "f431a5cd95cebf038e587715635b9d1a0a4d0c02"},
    {"name": "awesome-mcp", "kind": "awesome-list", "repo": "wong2/awesome-mcp-servers",
     "commit_sha": "39eb1d76d76e562657f3c657266a504cea159e23"},
    {"name": "best-of-mcp-servers", "kind": "awesome-list", "repo": "tolkonepiu/best-of-mcp-servers",
     "commit_sha": "d808a9a423a9bdb7ac338d1999e75acb6f2b843c"},
]


def _get(url: str, timeout: int = 15):
    req = urllib.request.Request(url, headers={"accept": "application/json", "user-agent": "revenueos-forage/1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _json(url: str, timeout: int = 15):
    return json.loads(_get(url, timeout))


def _repo(url: str | None) -> str | None:
    m = re.search(r"github\.com[/:]([\w.-]+/[\w.-]+?)(?:\.git|/|$)", url or "")
    return m.group(1) if m else None


# -- the three parallel searches (4.1) ---------------------------------------------------------
def search_registry(q: str, limit: int) -> list[dict]:
    data = _json(f"{REGISTRY}/v0/servers?" + urllib.parse.urlencode({"search": q, "limit": limit}))
    out = []
    for item in data.get("servers", []):
        s = item.get("server", item)
        pk = (s.get("packages") or [{}])[0]
        rm = (s.get("remotes") or [{}])[0]
        out.append({"source": "registry", "name": s.get("name"), "description": s.get("description", ""),
                    "version": s.get("version"), "repo": _repo((s.get("repository") or {}).get("url")),
                    "package": pk.get("identifier"), "package_type": pk.get("registryType"),
                    "url": rm.get("url")})
    return out


def search_smithery(q: str, limit: int) -> list[dict]:
    data = _json(f"{SMITHERY}/servers?" + urllib.parse.urlencode({"q": q, "pageSize": limit}))
    return [{"source": "smithery", "name": s.get("qualifiedName") or s.get("name"),
             "description": s.get("description", ""), "repo": _repo(s.get("homepage")),
             "uses": s.get("useCount")} for s in data.get("servers", [])]


def search_npm(q: str, limit: int) -> list[dict]:
    data = _json(f"{NPM}/-/v1/search?" + urllib.parse.urlencode({"text": f"{q} mcp", "size": limit}))
    out = []
    for o in data.get("objects", []):
        p = o.get("package", {})
        out.append({"source": "npm", "name": p.get("name"), "description": p.get("description", ""),
                    "version": p.get("version"), "package": p.get("name"), "package_type": "npm",
                    "repo": _repo((p.get("links") or {}).get("repository"))})
    return out


PROVIDERS = {"registry": search_registry, "smithery": search_smithery, "npm": search_npm}


def parallel_search(q: str, limit: int = 10) -> tuple[list[dict], dict]:
    results, errors = [], {}
    with ThreadPoolExecutor(max_workers=len(PROVIDERS)) as pool:
        futures = {name: pool.submit(fn, q, limit) for name, fn in PROVIDERS.items()}
        for name, f in futures.items():
            try:
                results += [c for c in f.result(timeout=30) if c.get("name")]
            except Exception as e:  # noqa: BLE001 - one dead registry must not hide the others
                errors[name] = f"{type(e).__name__}: {str(e)[:160]}"
    return results, errors


# -- adapters (4.3) ----------------------------------------------------------------------------
def mcptoon(args: list[str], home: str, timeout: int = 45) -> subprocess.CompletedProcess:
    env = {"PATH": os.environ.get("PATH", ""), "HOME": home, "MCPTOON_HOME": home, "NO_COLOR": "1"}
    return subprocess.run(["mcptoon", *args], env=env, capture_output=True, text=True, timeout=timeout)


def search_mcptoon(q: str, limit: int, home: str) -> list[dict]:
    """mcptoon's own registry search (`mcptoon install --search`), which lists and installs nothing."""
    p = mcptoon(["install", "--search", q, "--format", "json"], home)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout).strip()[:200] or f"mcptoon exited {p.returncode}")
    text = p.stdout.strip()
    try:
        data = json.loads(text[text.index("["):text.rindex("]") + 1]) if "[" in text else []
    except ValueError:
        data = []
    if not data:   # plain-text listing: one server per line, name first
        data = [{"name": ln.split()[0].strip("-*•"), "description": ln} for ln in text.splitlines()
                if ln.strip() and not ln.startswith(("🎉", " ", "note:", "No "))]
    return [{"source": "mcptoon", "name": d.get("name"), "description": d.get("description", ""),
             "url": d.get("url"), "command": d.get("command"), "args": d.get("args"),
             "via": d.get("source")} for d in data[:limit] if isinstance(d, dict) and d.get("name")]


def mcptoon_manifest(home: str, daemon_url: str) -> dict:
    """The compact discovery manifest (spec 4.3): mcptoon pointed at the one governed endpoint."""
    mcptoon(["install", "revenueos", "--url", daemon_url.rstrip("/") + "/mcp"], home)
    p = mcptoon(["manifest", "--format", "json"], home, timeout=90)
    try:
        return {"manifest": json.loads(p.stdout[p.stdout.index("{"):p.stdout.rindex("}") + 1])}
    except ValueError:
        return {"manifest_text": p.stdout.strip()[:20000], "stderr": p.stderr.strip()[:500]}


def search_mcpfinder(ad, q: str, limit: int) -> list[dict]:
    out = ad.call_tool("mcpfinder", "search_mcp_servers", {"query": q, "limit": limit})
    items = out.get("servers") or out.get("results") or [] if isinstance(out, dict) else out or []
    return [{"source": "mcpfinder", "name": s.get("name") or s.get("id"), "description": s.get("description", ""),
             "repo": _repo(s.get("repository") or s.get("repositoryUrl") or s.get("url")),
             "trust": {k: s[k] for k in ("stars", "trustScore", "verified", "lastUpdated", "license") if k in s}}
            for s in items if isinstance(s, dict)]


def mcpfinder_details(ad, name: str) -> dict:
    """Trust signals and install-ready JSON for one server, straight from MCPfinder's own tools."""
    return {"details": ad.call_tool("mcpfinder", "get_server_details", {"name": name}),
            "install": ad.call_tool("mcpfinder", "get_install_config", {"name": name, "client": "claude-code"})}


# -- enrichment: the signals the policy engine needs -------------------------------------------
def enrich(c: dict) -> dict:
    c = dict(c)
    if c.get("repo") and not (c.get("license") and c.get("last_push")):
        try:
            r = _json(f"{GITHUB_API}/repos/{c['repo']}")
            c.setdefault("license", (r.get("license") or {}).get("spdx_id"))
            c.setdefault("last_push", (r.get("pushed_at") or "")[:10] or None)
            c["archived"] = bool(r.get("archived"))
            c["stars"] = r.get("stargazers_count")
        except (OSError, ValueError, urllib.error.URLError):
            pass
    if c.get("package_type") == "npm" and c.get("package") and c.get("version") and not c.get("checksum"):
        try:
            v = _json(f"{NPM}/{urllib.parse.quote(c['package'], safe='@')}/{c['version']}")
            c["checksum"] = (v.get("dist") or {}).get("integrity")
            c.setdefault("license", v.get("license") if isinstance(v.get("license"), str) else None)
        except (OSError, ValueError, urllib.error.URLError):
            pass
    return c


# -- curated ingestion (4.4) -------------------------------------------------------------------
_ENTRY = re.compile(r"\[(?P<name>[^\]]+)\]\((?P<url>https://github\.com/[\w.-]+/[\w.-]+)[^)]*\)(?P<rest>.*)")
_STARS = re.compile(r"⭐\s*([\d.,]+)\s*([KkMm]?)")


def parse_list(markdown: str) -> list[dict]:
    out, seen = [], set()
    for line in markdown.splitlines():
        if not line.lstrip().startswith(("-", "*", "<details", "|")):
            continue
        m = _ENTRY.search(line)
        if not m:
            continue
        repo = _repo(m.group("url"))
        if not repo or repo.lower() in seen:
            continue
        seen.add(repo.lower())
        rest = re.sub(r"\[!\[[^\]]*\]\([^)]*\)\]\([^)]*\)|<[^>]+>", "", m.group("rest"))
        stars = None
        s = _STARS.search(rest)
        if s:
            n = float(s.group(1).replace(",", ""))
            stars = int(n * {"k": 1e3, "m": 1e6}.get(s.group(2).lower(), 1))
        desc = rest.split(" - ", 1)[1].strip() if " - " in rest else rest.strip(" -*")
        out.append({"name": re.sub(r"[*_`]", "", m.group("name")).strip(), "repo": repo,
                    "description": desc[:500], "stars": stars})
    return out


def ingest(db, source: dict) -> int:
    """Ingest one curated source into discovery_entries. A list is replaced as a whole."""
    url = source.get("url") or f"https://github.com/{source['repo']}"
    db.rows("INSERT INTO discovery_sources(name, kind, url, commit_sha) VALUES ($n, $k, $u, $s) "
            "ON CONFLICT (name) DO UPDATE SET url = EXCLUDED.url, commit_sha = EXCLUDED.commit_sha RETURNING name",
            n=source["name"], k=source["kind"], u=url, s=source.get("commit_sha"))
    if source["kind"] == "registry":
        data = _json(f"{REGISTRY}/v0/servers?limit=100", timeout=30)
        entries = [{"name": (i.get("server", i)).get("name"), "repo": _repo(((i.get("server", i)).get("repository") or {}).get("url")),
                    "description": (i.get("server", i)).get("description", ""), "stars": None}
                   for i in data.get("servers", [])]
    else:
        entries = parse_list(_get(f"{RAW}/{source['repo']}/{source['commit_sha']}/README.md", timeout=60).decode("utf-8", "replace"))
    entries = [e for e in entries if e.get("name")]
    db.rows("DELETE FROM discovery_entries WHERE source = $n RETURNING 1 AS x", n=source["name"])
    for i in range(0, len(entries), 100):
        db.rows("INSERT INTO discovery_entries(source, name, repo, description, stars) "
                "SELECT $n, e->>'name', e->>'repo', coalesce(e->>'description', ''), (e->>'stars')::integer "
                "FROM jsonb_array_elements($j::jsonb) e ON CONFLICT DO NOTHING RETURNING 1 AS x",
                n=source["name"], j=json.dumps(entries[i:i + 100]))
    db.rows("UPDATE discovery_sources SET entries = $c::integer, ingested_at = now() WHERE name = $n RETURNING name",
            c=len(entries), n=source["name"])
    return len(entries)


def search_curated(db, q: str, limit: int) -> list[dict]:
    rows = db.rows("SELECT source, name, repo, description, stars FROM discovery_entries "
                   "WHERE name ILIKE $q OR description ILIKE $q ORDER BY stars DESC NULLS LAST LIMIT $l::integer",
                   q=f"%{q}%", l=limit)
    return [{"source": "curated", "list": r["source"], "name": r["name"], "repo": r["repo"],
             "description": r["description"], "stars": r["stars"]} for r in rows]
