#!/usr/bin/env python3
"""Encrypted, maintenance-window backup of the single-node Docker deployment.

Requires age and Docker Compose on the host. Never prints environment values.
Keep the age private key OFF the server. Restore only into an isolated host.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def compose(*args: str, **kwargs):
    return subprocess.run(
        ["docker", "compose", "--env-file", ".env.production", "-f", "compose.prod.yaml", *args],
        cwd=ROOT, check=True, **kwargs,
    )


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_archive(archive: Path) -> None:
    """Validate a decrypted archive without extracting files or executing SQL."""
    with tarfile.open(archive, "r:gz") as bundle:
        members = bundle.getmembers()
        expected = {"revenueos.dump", "keycloak.dump", "media.tar", ".env.production", "realm.json", "manifest.json"}
        if len(members) != len(expected) or {m.name for m in members} != expected:
            raise ValueError("Unexpected or duplicate backup members")
        if any(not m.isfile() for m in members):
            raise ValueError("Backup must contain regular files only")
        manifest = json.load(bundle.extractfile("manifest.json"))
        if manifest.get("version") != 1 or set(manifest.get("sha256", {})) != expected - {"manifest.json"}:
            raise ValueError("Unsupported or incomplete manifest")
        for name, checksum in manifest["sha256"].items():
            with bundle.extractfile(name) as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != checksum:
                    raise ValueError(f"Checksum mismatch: {name}")
        with bundle.extractfile("media.tar") as stream, tarfile.open(fileobj=stream, mode="r|") as media:
            names = set()
            for member in media:
                path = PurePosixPath(member.name)
                if (path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] != "media"
                        or not (member.isfile() or member.isdir()) or member.name in names):
                    raise ValueError("Unsafe media archive member")
                names.add(member.name)
    print("Backup structure and checksums verified. Database/media restoration still requires a drill.")


def backup(recipient: str, output: Path) -> None:
    if os.name != "posix":
        raise RuntimeError("Run backups on the Linux deployment host")
    if not recipient.startswith("age1") or any(c.isspace() for c in recipient):
        raise ValueError("Supply an age public recipient, never a private key")
    if not shutil.which("age") or not shutil.which("docker"):
        raise RuntimeError("Install age and Docker Compose before backing up")
    for filename in (".env.production", "infra/keycloak/revenueos-production-realm.json"):
        if not (ROOT / filename).is_file():
            raise RuntimeError("Production configuration is incomplete")
    output = output.resolve()
    if not output.name.endswith(".tar.gz.age"):
        raise ValueError("Output must end in .tar.gz.age")
    if output.exists() or Path(str(output) + ".partial").exists():
        raise ValueError("Refusing to overwrite an existing backup")
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.umask(0o077)
    running = compose("ps", "--status", "running", "--services", capture_output=True, text=True).stdout.split()
    if "db" not in running or "api" not in running:
        raise RuntimeError("Database and API must be running; refusing an ambiguous backup")
    writers = [service for service in ("web", "api", "keycloak") if service in running]
    partial = Path(str(output) + ".partial")
    try:
        # Stop all application/identity writers for a consistent database + media snapshot.
        compose("stop", "--timeout", "60", *writers, stdout=subprocess.DEVNULL)
        with tempfile.TemporaryDirectory(prefix="revenueos-backup-") as temporary:
            staging = Path(temporary)
            for database in ("revenueos", "keycloak"):
                with (staging / f"{database}.dump").open("wb") as stream:
                    compose("exec", "-T", "db", "sh", "-c",
                            'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U postgres -Fc --dbname="$1"',
                            "backup", database, stdout=stream)
            with (staging / "media.tar").open("wb") as stream:
                compose("run", "--rm", "--no-deps", "-T", "api", "python", "-c",
                        "import sys,tarfile; t=tarfile.open(fileobj=sys.stdout.buffer,mode='w|'); "
                        "t.add('/data/media',arcname='media'); t.close()", stdout=stream)
            shutil.copyfile(ROOT / ".env.production", staging / ".env.production")
            shutil.copyfile(ROOT / "infra/keycloak/revenueos-production-realm.json", staging / "realm.json")
            manifest = {"version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
                        "sha256": {p.name: digest(p) for p in staging.iterdir()}}
            (staging / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with partial.open("xb") as encrypted:
                process = subprocess.Popen(["age", "-r", recipient], stdin=subprocess.PIPE, stdout=encrypted)
                try:
                    with tarfile.open(fileobj=process.stdin, mode="w|gz") as bundle:
                        for path in sorted(staging.iterdir()):
                            bundle.add(path, arcname=path.name, recursive=False)
                    process.stdin.close()
                    if process.wait() != 0:
                        raise RuntimeError("Backup encryption failed")
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.wait()
                encrypted.flush()
                os.fsync(encrypted.fileno())
            partial.rename(output)
            print("Encrypted backup created. Copy it off-host and run an isolated restore drill.")
    finally:
        partial.unlink(missing_ok=True)
        # Restart only services that were running before maintenance, even if backup failed.
        compose("start", *writers, stdout=subprocess.DEVNULL)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("--recipient", required=True)
    create.add_argument("--output", type=Path, required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("archive", type=Path, help="Decrypted .tar.gz on an isolated recovery host")
    args = parser.parse_args()
    if args.command == "create":
        backup(args.recipient, args.output)
    else:
        verify_archive(args.archive)


if __name__ == "__main__":
    main()
