"""INV-12: every agent write lands in a copy-on-write shadow workspace; destructive host
operations are blocked in every mode, including YOLO."""
import pytest

from sandbox_kit import needs_sandbox

@needs_sandbox
def test_rm_rf_root_blocked_in_yolo_mode(tmp_path):
    from revenueos_sandbox.supervisor import run_in_sandbox
    result = run_in_sandbox(["rm", "-rf", "/"], workspace=tmp_path, yolo=True)
    assert result.status == "blocked"
    assert result.exit_code is None


@needs_sandbox
def test_workspace_write_lands_in_shadow_not_host(tmp_path):
    from revenueos_sandbox.supervisor import run_in_sandbox
    (tmp_path / "keep.txt").write_text("original")
    result = run_in_sandbox(["sh", "-c", "echo changed > keep.txt"], workspace=tmp_path)
    assert result.exit_code == 0
    assert (tmp_path / "keep.txt").read_text() == "original"
    assert "keep.txt" in result.changeset


@needs_sandbox
def test_host_paths_are_not_mounted(tmp_path):
    from revenueos_sandbox.supervisor import run_in_sandbox
    secret = tmp_path / "host-only.txt"
    secret.write_text("host data")
    result = run_in_sandbox(["sh", "-c", f"cat {secret}; ls /home /root /var 2>&1; echo x > /usr/evil"])
    assert "host data" not in result.stdout
    assert not (secret.parent / "evil").exists()
    assert result.exit_code != 0   # /usr is read-only


@needs_sandbox
def test_blocklist_holds_inside_shell_payloads_in_yolo(tmp_path):
    from revenueos_sandbox.supervisor import run_in_sandbox
    for argv in (["bash", "-lc", "cd /tmp && rm -rf --no-preserve-root /"], ["sh", "-c", "dd if=/dev/zero of=/dev/sda"],
                 ["sh", "-c", ":(){ :|:& };:"]):
        r = run_in_sandbox(argv, workspace=tmp_path, yolo=True)
        assert r.status == "blocked" and r.exit_code is None, argv
