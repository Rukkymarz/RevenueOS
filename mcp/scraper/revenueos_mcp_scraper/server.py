"""scraper MCP (C14, spec 6.2): robots-aware fetch + extraction, with an ordered fallback chain.

Direct fetch comes first. When it is blocked or returns nothing readable, the chain tries
Agent-Reach, EasySpider and api-anything, each reached through an HTTP adapter the operator
configures (SCRAPER_FALLBACK_<NAME>_URL). An adapter that is not configured is reported as
`not_configured`, never as success. Private and link-local addresses are refused (SSRF guard).
"""
import ipaddress
import json
import os
import socket
import urllib.error
import urllib.request
import urllib.robotparser
from urllib.parse import urlparse

from pydantic import BaseModel, Field
from revenueos_mcp_common import create_server

from . import extract

UA = "RevenueOS-Scraper/0.1 (+https://github.com/Rukkymarz/RevenueOS)"
MAX_BYTES = 2_000_000
FALLBACKS = ("agent-reach", "easyspider", "api-anything")
server = create_server("scraper", token_ref=os.environ.get("SCRAPER_TOKEN_REF", "keychain://mcp-scraper-token"))


class FetchArgs(BaseModel):
    url: str = Field(min_length=8, max_length=2000, pattern=r"^https?://")
    use_fallbacks: bool = True
    respect_robots: bool = True


class ExtractArgs(BaseModel):
    html: str = Field(max_length=2_000_000)
    selector: str = Field(max_length=100)


def _allowed_hosts() -> set[str]:
    return {h.strip() for h in os.environ.get("SCRAPER_ALLOW_HOSTS", "").split(",") if h.strip()}


def guard(url: str) -> None:
    """Refuse non-public destinations unless the host is explicitly allowed."""
    host = urlparse(url).hostname or ""
    if host in _allowed_hosts():
        return
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise ValueError(f"cannot resolve {host}") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise PermissionError(f"{host} resolves to a non-public address; refused")


def _get(url: str) -> tuple[int, str, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,*/*;q=0.5"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.headers.get("content-type", ""), r.read(MAX_BYTES).decode(r.headers.get_content_charset() or "utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("content-type", "") if e.headers else "", ""


def robots_ok(url: str) -> bool:
    u = urlparse(url)
    rp = urllib.robotparser.RobotFileParser()
    try:
        status, _, body = _get(f"{u.scheme}://{u.netloc}/robots.txt")
    except Exception:
        return True   # no readable robots.txt: allowed by convention
    if status >= 400:
        return True
    rp.parse(body.splitlines())
    return rp.can_fetch(UA, url)


def _fallback(name: str, url: str) -> dict:
    endpoint = os.environ.get(f"SCRAPER_FALLBACK_{name.upper().replace('-', '_')}_URL")
    if not endpoint:
        return {"name": name, "status": "not_configured"}
    req = urllib.request.Request(endpoint, data=json.dumps({"url": url}).encode(), method="POST",
                                 headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = json.loads(r.read(MAX_BYTES))
    except Exception as e:  # noqa: BLE001 - a broken fallback is reported, then the next one is tried
        return {"name": name, "status": f"error:{type(e).__name__}"}
    html = body.get("html") or body.get("text") or ""
    return {"name": name, "status": "ok" if html.strip() else "empty", "html": html}


@server.tool("scrape_fetch", risk_class="low", args_model=FetchArgs)
def scrape_fetch(args: dict) -> dict:
    a = FetchArgs.model_validate(args)
    guard(a.url)
    if a.respect_robots and not robots_ok(a.url):
        return {"status": "robots_disallowed", "url": a.url, "tried": []}
    tried, html, via = [], "", None
    try:
        code, ctype, body = _get(a.url)
        tried.append({"name": "direct", "status": code})
        if code == 200 and body.strip() and "html" in ctype.lower():
            html, via = body, "direct"
    except Exception as e:  # noqa: BLE001
        tried.append({"name": "direct", "status": f"error:{type(e).__name__}"})
    if not html and a.use_fallbacks:
        for name in FALLBACKS:
            r = _fallback(name, a.url)
            tried.append({k: v for k, v in r.items() if k != "html"})
            if r["status"] == "ok":
                html, via = r["html"], name
                break
    if not html:
        return {"status": "failed", "url": a.url, "tried": tried}
    return {"status": "ok", "url": a.url, "via": via, "tried": tried, **extract.page(html, a.url)}


@server.tool("scrape_extract", risk_class="low", args_model=ExtractArgs)
def scrape_extract(args: dict) -> dict:
    a = ExtractArgs.model_validate(args)
    return {"matches": extract.select(a.html, a.selector)[:200]}


@server.tool("scrape_fallbacks", risk_class="low")
def scrape_fallbacks(args: dict) -> dict:
    return {"chain": [{"name": n, "configured": bool(os.environ.get(f"SCRAPER_FALLBACK_{n.upper().replace('-', '_')}_URL"))}
                      for n in FALLBACKS]}


app = server.http_app()


def main() -> None:  # pragma: no cover - process entrypoint
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8204)))


if __name__ == "__main__":  # pragma: no cover
    main()
