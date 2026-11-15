"""INV-05: unknown or missing telemetry resolves to DO_NOT_FILE, never PASS.

The verdict reducer lands with veripipe in Phase 8. Until then this attack is a strict
expected failure: CI fails the moment the module exists and the marker is not removed."""
import pytest

PHASE = "control lands in Phase 8 (veripipe verdict reducer)"


@pytest.mark.xfail(strict=True, raises=ImportError, reason=PHASE)
def test_missing_telemetry_resolves_to_do_not_file():
    from revenueos_qc.verdict import resolve_verdict
    assert resolve_verdict(oracle_results=[], telemetry=None) == "DO_NOT_FILE"


@pytest.mark.xfail(strict=True, raises=ImportError, reason=PHASE)
def test_unknown_oracle_outcome_never_becomes_pass():
    from revenueos_qc.verdict import resolve_verdict
    verdict = resolve_verdict(oracle_results=[{"oracle": "http_status", "outcome": "unknown"}], telemetry={"spans": 0})
    assert verdict != "PASS"
    assert verdict == "DO_NOT_FILE"


def test_database_never_lets_do_not_file_complete_a_task(db, world):
    """The storage half exists today: a DO_NOT_FILE verdict cannot carry a task to QC_PASSED."""
    from dbkit import add_verification, advance_to_verifying
    advance_to_verifying(db, world)
    v = add_verification(db, world, verdict="DO_NOT_FILE")
    db.rejects(f"UPDATE tasks SET verification_id='{v}', state='QC_PASSED' WHERE id='{world['task']}'", "INV-01")
