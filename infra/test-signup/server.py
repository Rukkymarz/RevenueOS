"""Self-hosted test signup service (Phase 2 acceptance, spec 2.6). Stands in for a real
third-party product: signing up mails a one-time code and a magic link to the address given,
over SMTP to the agent's own mail server; verifying either completes the signup.

POST /signup {"email"}            -> 202, sends the email
POST /verify {"email", "code"}    -> 200 {"verified": true} | 400
GET  /magic?token=...             -> 200 {"verified": true} | 400
GET  /status?email=...            -> {"verified": bool}
"""
import json
import os
import secrets
import smtplib
import threading
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

SMTP_HOST = os.environ.get("SMTP_HOST", "stalwart")
PUBLIC = os.environ.get("PUBLIC_URL", "http://signup-test:8090")
lock = threading.Lock()
pending: dict[str, dict] = {}
verified: set[str] = set()


class Handler(BaseHTTPRequestHandler):
    def _json(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _body(self):
        return json.loads(self.rfile.read(int(self.headers.get("content-length") or 0)) or b"{}")

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/signup":
            email = str(self._body().get("email", ""))
            if "@" not in email:
                return self._json(400, {"error": "email required"})
            code, token = f"{secrets.randbelow(10**6):06d}", secrets.token_urlsafe(16)
            with lock:
                pending[email] = {"code": code, "token": token}
            msg = EmailMessage()
            msg["From"], msg["To"], msg["Subject"] = "Signup Test <noreply@signup.test>", email, "Your verification code"
            msg.set_content(f"Your verification code is {code}.\n\nOr open this link: {PUBLIC}/magic?token={token}\n")
            with smtplib.SMTP(SMTP_HOST, 25, timeout=20) as s:
                s.send_message(msg)
            return self._json(202, {"status": "code sent"})
        if path == "/verify":
            b = self._body()
            email, code = str(b.get("email", "")), str(b.get("code", ""))
            with lock:
                ok = email in pending and secrets.compare_digest(pending[email]["code"], code)
                if ok:
                    verified.add(email)
                    pending.pop(email)
            return self._json(200 if ok else 400, {"verified": ok})
        self._json(404, {"error": "not found"})

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path == "/health":
            return self._json(200, {"status": "ok"})
        if u.path == "/magic":
            token = (q.get("token") or [""])[0]
            with lock:
                email = next((e for e, p in pending.items() if secrets.compare_digest(p["token"], token)), None)
                if email:
                    verified.add(email)
                    pending.pop(email)
            return self._json(200 if email else 400, {"verified": bool(email)})
        if u.path == "/status":
            return self._json(200, {"verified": (q.get("email") or [""])[0] in verified})
        self._json(404, {"error": "not found"})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8090), Handler).serve_forever()
