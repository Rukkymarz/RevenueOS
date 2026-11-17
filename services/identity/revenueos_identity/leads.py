"""Runs the leads agent's signup flow (spec 2.6) inside the sandbox and records every step it
reports on the task's timeline and in the audit ledger."""
import json
import os
from urllib.parse import urlparse

import requests

from revenueos_common.db import Database

SUPERVISOR = os.environ.get("SANDBOX_SUPERVISOR_URL", "http://sandbox-supervisor:8300")


def record_steps(db: Database, agent_id: str, task_id: str, stdout: str) -> list[dict]:
    steps = []
    for line in stdout.splitlines():
        try:
            s = json.loads(line)
        except ValueError:
            continue
        if not isinstance(s, dict) or "step" not in s or "status" not in s:
            continue
        steps.append(s)
        timeline = db.scalar(
            "INSERT INTO timelines(thing_type, thing_id) VALUES ('task', $task) "
            "ON CONFLICT (thing_type, thing_id) DO UPDATE SET thing_id = EXCLUDED.thing_id RETURNING id", task=task_id)
        db.scalar("INSERT INTO timeline_events(timeline_id, event_type, payload) "
                  "VALUES ($tl::uuid, 'leads.signup.' || $step, #payload) RETURNING id",
                  tl=timeline, step=str(s["step"]), payload={**s, "agent_id": agent_id})
        db.scalar("SELECT audit_append($actor, $action, $target, #payload) IS NULL AS ok",
                  actor=f"agent:{agent_id}", action=f"leads.signup.{s['step']}.{s['status']}", target=task_id, payload=s)
    return steps


def leads_signup(db: Database, agent_id: str, task_id: str, service: str, mode: str = "otp",
                 supervisor: str = SUPERVISOR, timeout_s: int = 90) -> dict:
    email = db.scalar("SELECT address FROM agent_identities WHERE agent_id=$a::uuid AND kind='email' AND status='active' "
                      "ORDER BY created_at LIMIT 1", a=agent_id)
    if not email:
        raise RuntimeError("INV-09: the agent has no active email identity of its own")
    host = urlparse(service).netloc.lower()
    db.scalar("INSERT INTO egress_rules(agent_id, task_id, host, created_by) VALUES ($a::uuid, $t::uuid, $h, 'leads-signup') "
              "ON CONFLICT DO NOTHING RETURNING id", a=agent_id, t=task_id, h=host)
    argv = ["python3", "-m", "revenueos_identity.leads_agent", "--email", email, "--service", service,
            "--mode", mode, "--timeout", str(timeout_s - 20)]
    r = requests.post(f"{supervisor}/v1/run", timeout=timeout_s + 30,
                      json={"agent_id": agent_id, "task_id": task_id, "egress": True, "argv": argv,
                            "quotas": {"wall_seconds": timeout_s}})
    r.raise_for_status()
    run = r.json()
    steps = record_steps(db, agent_id, task_id, run.get("stdout", ""))
    return {"status": run["status"], "exit_code": run["exit_code"], "email": email, "steps": steps,
            "stderr_tail": run.get("stderr", "")[-2000:]}
