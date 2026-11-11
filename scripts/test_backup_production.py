"""Recovery validation must reject tampering, traversal and duplicate members."""
import hashlib
import io
import json
from pathlib import Path
import tarfile
from types import SimpleNamespace
import os

import pytest

from backup_production import verify_archive
import backup_production as implementation


def fixture_archive(path: Path, *, corrupt=False, extra=None, unsafe_media=False):
    files = {name: b"recovery-test" for name in
             ("revenueos.dump", "keycloak.dump", "media.tar", ".env.production", "realm.json")}
    media = io.BytesIO()
    with tarfile.open(fileobj=media, mode="w") as archive:
        entry = tarfile.TarInfo("media/../../escape" if unsafe_media else "media")
        entry.type = tarfile.DIRTYPE
        archive.addfile(entry)
    files["media.tar"] = media.getvalue()
    manifest = {"version": 1, "sha256": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}
    if corrupt:
        files["revenueos.dump"] = b"tampered"
    files["manifest.json"] = json.dumps(manifest).encode()
    with tarfile.open(path, "w:gz") as archive:
        for name, data in files.items():
            entry = tarfile.TarInfo(name)
            entry.size = len(data)
            archive.addfile(entry, io.BytesIO(data))
        if extra:
            entry = tarfile.TarInfo(extra)
            archive.addfile(entry, io.BytesIO(b""))


def test_valid_archive(tmp_path):
    path = tmp_path / "valid.tar.gz"
    fixture_archive(path)
    verify_archive(path)


@pytest.mark.parametrize("extra", ["../escape", "manifest.json"])
def test_reject_unsafe_members(tmp_path, extra):
    path = tmp_path / "invalid.tar.gz"
    fixture_archive(path, extra=extra)
    with pytest.raises(ValueError, match="Unexpected or duplicate"):
        verify_archive(path)


def test_reject_modified_dump(tmp_path):
    path = tmp_path / "invalid.tar.gz"
    fixture_archive(path, corrupt=True)
    with pytest.raises(ValueError, match="Checksum mismatch"):
        verify_archive(path)


def test_reject_media_traversal_even_with_valid_checksum(tmp_path):
    path = tmp_path / "invalid-media.tar.gz"
    fixture_archive(path, unsafe_media=True)
    with pytest.raises(ValueError, match="Unsafe media"):
        verify_archive(path)


@pytest.mark.parametrize("encryption_status", [0, 1])
def test_writers_restart_and_failed_backups_are_not_published(tmp_path, monkeypatch, encryption_status):
    root = tmp_path / "checkout"
    (root / "infra/keycloak").mkdir(parents=True)
    (root / ".env.production").write_text("disposable-test-config")
    (root / "infra/keycloak/revenueos-production-realm.json").write_text("{}")
    monkeypatch.setattr(implementation, "ROOT", root)
    # The orchestration is platform independent except for the real host guard.
    monkeypatch.setattr(implementation, "os", SimpleNamespace(name="posix", umask=lambda value: None, fsync=os.fsync))
    monkeypatch.setattr(implementation.shutil, "which", lambda name: name)
    calls = []

    def fake_compose(*args, **kwargs):
        calls.append(args)
        if args[0] == "ps":
            return SimpleNamespace(stdout="db\napi\nkeycloak\n")
        if args[0] in ("exec", "run"):
            kwargs["stdout"].write(b"disposable database/media contents")
        return SimpleNamespace()

    class FakeEncryption:
        def __init__(self, *args, **kwargs):
            self.stdin = io.BytesIO()
            kwargs["stdout"].write(b"fake ciphertext for orchestration test only")

        def wait(self):
            return encryption_status

        def poll(self):
            return encryption_status

    monkeypatch.setattr(implementation, "compose", fake_compose)
    monkeypatch.setattr(implementation.subprocess, "Popen", FakeEncryption)
    output = tmp_path / "backup.tar.gz.age"
    if encryption_status:
        with pytest.raises(RuntimeError, match="encryption failed"):
            implementation.backup("age1disposable", output)
    else:
        implementation.backup("age1disposable", output)
    assert calls[-1] == ("start", "api", "keycloak")
    assert ("stop", "--timeout", "60", "api", "keycloak") in calls
    assert output.exists() is (encryption_status == 0)
    assert not Path(str(output) + ".partial").exists()
