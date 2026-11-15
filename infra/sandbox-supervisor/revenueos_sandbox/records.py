"""Postgres records for sandbox runs (sandbox_sessions) and egress sessions (egress_sessions).
Triggers in migration 0002 write the matching audit entries."""
from revenueos_common.db import Database

STATUS = {"ok": "finished", "failed": "failed", "blocked": "blocked", "timeout": "timeout", "killed": "failed"}


class Recorder:
    def __init__(self, db: Database, backend: str = "bubblewrap"):
        self.db, self.backend = db, backend

    def start(self, agent_id, task_id, yolo, workspace, command_hash) -> str:
        return self.db.scalar(
            "INSERT INTO sandbox_sessions(agent_id, task_id, backend, yolo, workspace, shadow_path, command_hash) "
            "VALUES ($agent::uuid, nullif($task,'')::uuid, $backend, ($yolo)::boolean, $ws, 'pending', $hash) RETURNING id",
            agent=agent_id, task=task_id or "", backend=self.backend, yolo=str(bool(yolo)).lower(),
            ws=str(workspace or "(empty)"), hash=command_hash)

    def finish(self, session_id: str, result) -> None:
        self.db.scalar(
            "UPDATE sandbox_sessions SET status=$status, exit_code=nullif($rc,'')::int, reason=nullif($reason,''), "
            "changeset_hash=nullif($cs,''), shadow_path=$shadow, ended_at=now() WHERE id=$id::uuid RETURNING id",
            status=STATUS[result.status], rc="" if result.exit_code is None else str(result.exit_code),
            reason=result.reason or "", cs=result.changeset_hash or "",
            shadow=str(result.shadow or "(discarded)"), id=session_id)


def egress_hooks(db: Database):
    def opened(session):
        db.scalar("INSERT INTO egress_sessions(id, agent_id, task_id, socket_path) "
                  "VALUES ($id::uuid, $agent::uuid, nullif($task,'')::uuid, $path) RETURNING id",
                  id=session.session_id, agent=session.agent_id, task=session.task_id or "", path=str(session.socket_path))

    def closed(session):
        db.scalar("UPDATE egress_sessions SET closed_at=now() WHERE id=$id::uuid RETURNING id", id=session.session_id)
    return opened, closed
