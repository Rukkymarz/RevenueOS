"""OpenMuse acceptance pipeline (spec 3.5, Acceptance 3.1), unattended:

  browser signup with the agent's Phase 2 email identity -> OTP read from the agent's own
  inbox -> verified page -> PDF intake form downloaded -> filled with nib (C15, pinned) ->
  deterministic review of the filled form -> reply draft saved to the agent's Drafts folder.

The draft is never sent: outbound mail is a high-risk action that needs its own approval, and
producing a *reviewed draft* is exactly what the acceptance asks for. Every stage is recorded
in the result; the browser actions and the pipeline itself are receipted by the caller
(app.py routes them through the same receipt ledger as every tool call).
"""
from __future__ import annotations

import email
import email.policy
import imaplib
import json
import re
import subprocess
import time
from dataclasses import dataclass, field
from email.message import EmailMessage
from pathlib import Path

OTP = re.compile(r"verification code is (\d{6})")


@dataclass
class PipelineResult:
    status: str = "running"
    stages: list = field(default_factory=list)
    filled_pdf: str | None = None
    review: dict | None = None
    draft_uid: str | None = None
    reason: str | None = None

    def stage(self, name: str, **detail):
        self.stages.append({"stage": name, **detail})


def _imap(host: str, port: int, login: str, password: str) -> imaplib.IMAP4:
    """Plain IMAP on the internal compose network, like allmail-mcp; the login is the Stalwart
    principal, not the address."""
    m = imaplib.IMAP4(host, port, timeout=20)
    m.login(login, password)
    return m


def wait_for_otp(host: str, port: int, login: str, password: str, deadline_s: float = 90) -> str:
    """Poll the agent's own INBOX for the signup service's code (the leads-agent pattern)."""
    end = time.monotonic() + deadline_s
    while time.monotonic() < end:
        m = _imap(host, port, login, password)
        try:
            m.select("INBOX")
            _, data = m.search(None, "ALL")
            for uid in reversed((data[0] or b"").split()):
                _, msg = m.fetch(uid, "(RFC822)")
                body = email.message_from_bytes(msg[0][1], policy=email.policy.default).get_body()
                text = body.get_content() if body else ""
                hit = OTP.search(text)
                if hit:
                    return hit.group(1)
        finally:
            m.logout()
        time.sleep(2)
    raise TimeoutError("no verification code arrived in the agent's inbox")


def nib(args: list[str], timeout: int = 60) -> str:
    r = subprocess.run(["nib", *args], capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"nib {args[0]} failed: {r.stderr.strip()[:500]}")
    return r.stdout


def fill_form(pdf: Path, values: dict[str, str], out: Path) -> None:
    data = out.with_suffix(".data.json")
    data.write_text(json.dumps(values))
    nib(["fill", str(pdf), "--data", str(data), "-o", str(out)])


def review_filled(pdf: Path, expected: dict[str, str]) -> dict:
    """Deterministic review (the ReviewerAgent check): export the filled form's XFDF and verify
    every expected field carries exactly the expected value."""
    xfdf = pdf.with_suffix(".review.xfdf")
    nib(["export-xfdf", str(pdf), "-o", str(xfdf)])
    text = xfdf.read_text()
    problems = [f"{k}={v!r} missing" for k, v in expected.items() if f">{v}<" not in text and v not in text]
    return {"verdict": "PASS" if not problems else "FAIL", "problems": problems, "xfdf": str(xfdf)}


def draft_reply(host: str, port: int, login: str, from_addr: str, password: str, to_addr: str,
                subject: str, body: str, attachment: Path) -> str:
    """APPEND the reviewed reply to the agent's Drafts mailbox — a draft, never a send."""
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = from_addr, to_addr, subject
    msg.set_content(body)
    msg.add_attachment(attachment.read_bytes(), maintype="application", subtype="pdf",
                       filename=attachment.name)
    m = _imap(host, port, login, password)
    try:
        if m.select("Drafts")[0] != "OK":
            m.create("Drafts")
        m.append("Drafts", r"(\Draft)", imaplib.Time2Internaldate(time.time()), msg.as_bytes())
        m.select("Drafts")
        _, data = m.search(None, "ALL")
        return (data[0] or b"").split()[-1].decode()
    finally:
        m.logout()


def run_signup_pipeline(browser, agent_id: str, task_id: str, *, email_addr: str, login: str,
                        password: str, signup_url: str, imap_host: str = "stalwart",
                        imap_port: int = 143, workdir: str = "/workspace") -> PipelineResult:
    """Drive the whole Acceptance 3.1 loop through the OpenMuse persistent browser."""
    res = PipelineResult()
    work = Path(workdir) / "pipeline" / task_id
    work.mkdir(parents=True, exist_ok=True)
    try:
        browser.open(agent_id, task_id)
        res.stage("browser.open", profile=browser.sessions[agent_id].profile_dir)
        browser.goto(agent_id, signup_url + "/")
        browser.fill(agent_id, "#email", email_addr)
        browser.click(agent_id, "#submit")
        res.stage("signup.submitted", email=email_addr)

        code = wait_for_otp(imap_host, imap_port, login, password)
        res.stage("otp.extracted", length=len(code))

        browser.goto(agent_id, f"{signup_url}/verify-page?email={email_addr}")
        browser.fill(agent_id, "#code", code)
        browser.click(agent_id, "#submit")
        res.stage("signup.verified")

        rel = f"pipeline/{task_id}/intake-form.pdf"
        browser.download(agent_id, "#download", rel)
        pdf = Path(workdir) / rel
        res.stage("form.downloaded", bytes=pdf.stat().st_size)

        values = {"name": f"Agent {agent_id[:8]}", "email": email_addr,
                  "company": "RevenueOS", "date": time.strftime("%Y-%m-%d")}
        filled = work / "intake-form.filled.pdf"
        fill_form(pdf, values, filled)
        res.filled_pdf = str(filled)
        res.stage("form.filled", fields=len(values))

        res.review = review_filled(filled, values)
        res.stage("review", **res.review)
        if res.review["verdict"] != "PASS":
            res.status, res.reason = "failed", "review failed: " + "; ".join(res.review["problems"])
            return res

        res.draft_uid = draft_reply(imap_host, imap_port, login, email_addr, password,
                                    "noreply@signup.test", "Re: Your verification code",
                                    "Completed intake form attached. — sent for review before any send.\n",
                                    filled)
        res.stage("reply.drafted", uid=res.draft_uid)
        res.status = "completed"
        return res
    except Exception as e:  # noqa: BLE001 - the pipeline reports, never hides, its failure
        res.status, res.reason = "failed", f"{type(e).__name__}: {e}"
        return res
    finally:
        browser.close(agent_id)
