"""Self-hosted test signup service (Phase 2 acceptance, spec 2.6). Stands in for a real
third-party product: signing up mails a one-time code and a magic link to the address given,
over SMTP to the agent's own mail server; verifying either completes the signup.

POST /signup {"email"}            -> 202, sends the email            (JSON API)
POST /verify {"email", "code"}    -> 200 {"verified": true} | 400     (JSON API)
GET  /magic?token=...             -> 200 {"verified": true} | 400
GET  /status?email=...            -> {"verified": bool}

Browser surface (Phase 3 acceptance: a real browser signs up and downloads the form):
GET  /                            -> HTML signup form
POST /signup-form (email=...)     -> HTML "code sent" page linking to /verify-page
GET  /verify-page?email=...       -> HTML code entry form
POST /verify-form (email, code)   -> HTML verified page with the PDF download link
GET  /form.pdf?email=...          -> the intake AcroForm, only for verified addresses
"""
import html as html_mod
import json
import os
import secrets
import smtplib
import threading
from pathlib import Path
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

SMTP_HOST = os.environ.get("SMTP_HOST", "stalwart")
PUBLIC = os.environ.get("PUBLIC_URL", "http://signup-test:8090")
lock = threading.Lock()
pending: dict[str, dict] = {}
verified: set[str] = set()
FORM_PDF = Path(__file__).with_name("intake-form.pdf")

PAGE = """<!doctype html><html><head><title>Signup Test</title></head><body>
<h1>Signup Test</h1>%s</body></html>"""


def _signup(email: str) -> None:
    code, token = f"{secrets.randbelow(10**6):06d}", secrets.token_urlsafe(16)
    with lock:
        pending[email] = {"code": code, "token": token}
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = "Signup Test <noreply@signup.test>", email, "Your verification code"
    msg.set_content(f"Your verification code is {code}.\n\nOr open this link: {PUBLIC}/magic?token={token}\n")
    with smtplib.SMTP(SMTP_HOST, 25, timeout=20) as s:
        s.send_message(msg)


def _verify(email: str, code: str) -> bool:
    with lock:
        ok = email in pending and secrets.compare_digest(pending[email]["code"], code)
        if ok:
            verified.add(email)
            pending.pop(email)
    return ok


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
            _signup(email)
            return self._json(202, {"status": "code sent"})
        if path == "/verify":
            b = self._body()
            ok = _verify(str(b.get("email", "")), str(b.get("code", "")))
            return self._json(200 if ok else 400, {"verified": ok})
        if path in ("/signup-form", "/verify-form"):
            form = parse_qs(self.rfile.read(int(self.headers.get("content-length") or 0)).decode())
            email = (form.get("email") or [""])[0]
            if path == "/signup-form":
                if "@" not in email:
                    return self._html(400, "<p>email required</p>")
                _signup(email)
                e = html_mod.escape(email, quote=True)
                return self._html(200, f'<p id="sent">Code sent to {e}.</p>'
                                       f'<a id="to-verify" href="/verify-page?email={e}">Enter your code</a>')
            ok = _verify(email, (form.get("code") or [""])[0])
            if not ok:
                return self._html(400, "<p>wrong code</p>")
            e = html_mod.escape(email, quote=True)
            return self._html(200, f'<p id="verified">Verified.</p>'
                                   f'<a id="download" href="/form.pdf?email={e}">Download your intake form (PDF)</a>')
        self._json(404, {"error": "not found"})

    def _html(self, code, body):
        data = (PAGE % body).encode()
        self.send_response(code)
        self.send_header("content-type", "text/html; charset=utf-8")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path == "/health":
            return self._json(200, {"status": "ok"})
        if u.path == "/":
            return self._html(200, '<form id="signup" method="post" action="/signup-form">'
                                   '<label>Email <input id="email" name="email" type="email"></label>'
                                   '<button id="submit" type="submit">Sign up</button></form>')
        if u.path == "/verify-page":
            e = html_mod.escape((q.get("email") or [""])[0], quote=True)
            return self._html(200, f'<form id="verify" method="post" action="/verify-form">'
                                   f'<input type="hidden" name="email" value="{e}">'
                                   f'<label>Code <input id="code" name="code"></label>'
                                   f'<button id="submit" type="submit">Verify</button></form>')
        if u.path == "/form.pdf":
            email = (q.get("email") or [""])[0]
            if email not in verified:
                return self._json(403, {"error": "verify first"})
            data = FORM_PDF.read_bytes()
            self.send_response(200)
            self.send_header("content-type", "application/pdf")
            self.send_header("content-disposition", 'attachment; filename="intake-form.pdf"')
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
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
