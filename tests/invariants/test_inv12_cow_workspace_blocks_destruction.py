"""INV-12: every agent write lands in a copy-on-write shadow workspace; destructive host
operations are blocked in every mode, including YOLO.

The sandbox lands in Phase 2; these attacks are strict expected failures until then."""
import pytest

PHASE = "control lands in Phase 2 (sandbox supervisor)"


@pytest.mark.xfail(strict=True, raises=ImportError, reason=PHASE)
def test_rm_rf_root_blocked_in_yolo_mode(tmp_path):
    from revenueos_sandbox.supervisor import run_in_sandbox
    result = run_in_sandbox(["rm", "-rf", "/"], workspace=tmp_path, yolo=True)
    assert result.status == "blocked"
    assert result.exit_code is None


@pytest.mark.xfail(strict=True, raises=ImportError, reason=PHASE)
def test_workspace_write_lands_in_shadow_not_host(tmp_path):
    from revenueos_sandbox.supervisor import run_in_sandbox
    (tmp_path / "keep.txt").write_text("original")
    result = run_in_sandbox(["sh", "-c", "echo changed > keep.txt"], workspace=tmp_path)
    assert result.exit_code == 0
    assert (tmp_path / "keep.txt").read_text() == "original"
    assert "keep.txt" in result.changeset
