"""Test-only upstream for the egress proof (compose profile `test`). It reports whether
an Authorization header arrived and its SHA-256, never the value itself, so a test can
prove injection happened while the secret stays out of every response."""
import hashlib
import json
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        auth = self.headers.get("authorization")
        body = json.dumps({
            "path": self.path,
            "authorization_present": auth is not None,
            "authorization_sha256": hashlib.sha256(auth.encode()).hexdigest() if auth else None,
            "agent_header_leaked": self.headers.get("x-revenueos-agent") is not None,
        }).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
