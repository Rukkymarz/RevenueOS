"""Process entrypoint: the real scan loop (watchers.py) runs in a background daemon thread,
and this process serves /health and /v1/info in the foreground -- giving ambient-watchers the
same contract-shaped health surface as every other service (spec 1.1) without turning the
scanner itself into an HTTP handler."""
import argparse
import threading
import time

from revenueos_common.service import run

from . import DEFAULT_PORT
from .app import app
from .watchers import AmbientWatchers, ensure_registered


def _scan_loop(interval: float) -> None:  # pragma: no cover - long-running loop
    from revenueos_common.db import Database
    db = Database(actor="ambient-watchers")
    agent_id = ensure_registered(db)
    watchers = AmbientWatchers(db, self_agent_id=agent_id)
    while True:
        watchers.scan_and_emit()
        time.sleep(interval)


def main() -> None:  # pragma: no cover - process entrypoint
    p = argparse.ArgumentParser(prog="revenueos-ambient-watchers-service")
    p.add_argument("--interval", type=float, default=30.0, help="seconds between scans")
    args, _ = p.parse_known_args()
    threading.Thread(target=_scan_loop, args=(args.interval,), daemon=True, name="ambient-scan-loop").start()
    run(app, DEFAULT_PORT)


if __name__ == "__main__":  # pragma: no cover
    main()
