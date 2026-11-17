"""Test-only stand-in for the public discovery endpoints (compose profile `test`), so Phase 4
acceptance runs without the internet and proves the real code paths: the Official MCP Registry
(v0 search for Forage, v0.1 mirror and version lookup for agent-discover), Smithery, npm, the
GitHub repository API (license and activity signals for the policy engine) and one curated list."""
import json
import re
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

NOW = datetime.now(timezone.utc)
RECENT = (NOW - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
STALE = (NOW - timedelta(days=900)).strftime("%Y-%m-%dT%H:%M:%SZ")
META = {"io.modelcontextprotocol.registry/official": {"status": "active", "isLatest": True,
                                                      "publishedAt": RECENT, "updatedAt": RECENT}}
SERVERS = [
    {"name": "io.revenueos.fixture/echo", "title": "Fixture Echo", "version": "1.0.0",
     "description": "Echo and add tools: fills the pdf-to-echo capability gap in the acceptance test",
     "repository": {"url": "https://github.com/revenueos-fixture/echo", "source": "github"},
     "remotes": [{"type": "streamable-http", "url": "http://mcp-fixture-echo:8090/mcp"}]},
    {"name": "io.revenueos.fixture/abandoned", "title": "Abandoned", "version": "0.1.0",
     "description": "Echo server whose repository is stale and unlicensed: the policy engine must refuse it",
     "repository": {"url": "https://github.com/revenueos-fixture/abandoned", "source": "github"},
     "remotes": [{"type": "streamable-http", "url": "http://mcp-fixture-echo:8090/mcp"}]},
]
REPOS = {
    "revenueos-fixture/echo": {"license": {"spdx_id": "MIT"}, "pushed_at": RECENT, "archived": False, "stargazers_count": 120},
    "revenueos-fixture/abandoned": {"license": None, "pushed_at": STALE, "archived": True, "stargazers_count": 2},
}
LIST = """# Awesome fixture list
- [Fixture Echo](https://github.com/revenueos-fixture/echo) - Echo and add tools ⭐ 120
- [Abandoned](https://github.com/revenueos-fixture/abandoned) - Stale echo server
"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, body, status=200, ctype="application/json"):
        data = body.encode() if isinstance(body, str) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("content-type", ctype)
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        path = unquote(u.path)
        if path == "/health":
            return self._send({"status": "ok"})
        if path == "/site/acme":          # Acceptance 6: a public-looking business page for the scraper
            page = (b"<html><head><title>Acme Offices</title><meta name=description content='Office park'></head><body>"
                    b"<p>Facilities: hello@acme.example, 404-555-1212</p><a href='/site/contact'>Contact</a></body></html>")
            self.send_response(200)
            self.send_header("content-type", "text/html")
            self.send_header("content-length", str(len(page)))
            self.end_headers()
            return self.wfile.write(page)
        if path in ("/v0/servers", "/v0.1/servers"):
            term = (q.get("search") or "").lower()
            hits = [s for s in SERVERS if term in (s["name"] + s["description"]).lower()]
            return self._send({"servers": [{"server": s, "_meta": META} for s in hits], "metadata": {"count": len(hits)}})
        m = re.match(r"^/v0(?:\.1)?/servers/(.+)/versions/([^/]+)$", path)
        if m:
            s = next((s for s in SERVERS if s["name"] == m.group(1)), None)
            return self._send({"server": s, "_meta": META}) if s else self._send({"error": "not found"}, 404)
        if path == "/servers":            # Smithery
            term = (q.get("q") or "").lower()
            return self._send({"servers": [{"qualifiedName": "@revenueos-fixture/echo", "description": "Echo (Smithery listing)",
                                            "homepage": "https://github.com/revenueos-fixture/echo", "useCount": 7}]
                               if term in "echo fixture" else []})
        if path == "/-/v1/search":        # npm
            return self._send({"objects": [{"package": {"name": "@revenueos-fixture/echo-mcp", "version": "1.0.0",
                                                        "description": "Echo MCP (npm listing)",
                                                        "links": {"repository": "https://github.com/revenueos-fixture/echo"}}}]})
        m = re.match(r"^/repos/([^/]+/[^/]+)$", path)
        if m:
            return self._send(REPOS[m.group(1)]) if m.group(1) in REPOS else self._send({"message": "Not Found"}, 404)
        if path.endswith("/README.md"):
            return self._send(LIST, ctype="text/markdown")
        self._send({"error": "not found", "path": path}, 404)

    def log_message(self, *_):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8085), Handler).serve_forever()
