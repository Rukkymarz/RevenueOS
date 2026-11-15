"""D10: scanner verdicts. No report is DO_NOT_FILE (never PASS); high/critical real findings FAIL."""
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "autosecscan_verdict.py"


def run(tmp_path, report):
    out = tmp_path / ".security"
    out.mkdir()
    if report is not None:
        (out / "scan-1.json").write_text(json.dumps(report))
    r = subprocess.run([sys.executable, str(SCRIPT), str(out)], cwd=tmp_path, capture_output=True, text=True)
    return r.returncode, json.loads((out / "autosecscan.verdict.json").read_text())["verdict"], r.stdout


def test_missing_report_is_do_not_file(tmp_path):
    code, verdict, _ = run(tmp_path, None)
    assert (code, verdict) == (1, "DO_NOT_FILE")


def test_high_finding_fails_and_is_printed(tmp_path):
    rep = {"findings": [{"scanner": "semgrep", "title": "sqli", "severity": "high", "location": "a.py:3"},
                        {"scanner": "osv", "title": "minor", "severity": "low"}]}
    code, verdict, out = run(tmp_path, rep)
    assert (code, verdict) == (1, "FAIL")
    assert "sqli @ a.py:3" in out


def test_triaged_false_positive_and_downgrade_pass(tmp_path):
    rep = {"findings": [{"title": "fp", "severity": "critical", "ai_is_real": False},
                        {"title": "down", "severity": "high", "ai_severity": "medium"}]}
    code, verdict, _ = run(tmp_path, rep)
    assert (code, verdict) == (0, "PASS")


OH = Path(__file__).resolve().parents[2] / "scripts" / "openhack_verdict.py"


def oh(tmp_path, report):
    f = tmp_path / ".security" / "openhack.json"
    f.parent.mkdir(exist_ok=True)
    if report is not None:
        f.write_text(report if isinstance(report, str) else json.dumps(report))
    r = subprocess.run([sys.executable, str(OH), str(f)], cwd=tmp_path, capture_output=True, text=True)
    return r.returncode, json.loads((tmp_path / ".security" / "openhack.verdict.json").read_text())["verdict"]


def test_openhack_completed_clean_scan_passes(tmp_path):
    assert oh(tmp_path, {"status": "completed", "findings": []}) == (0, "PASS")


def test_openhack_unfinished_or_missing_scan_is_do_not_file(tmp_path):
    assert oh(tmp_path, {"status": "failed", "findings": []}) == (1, "DO_NOT_FILE")
    assert oh(tmp_path / "x" if (tmp_path / "x").mkdir() is None else tmp_path, None) == (1, "DO_NOT_FILE")


def test_openhack_high_finding_fails_even_if_unfinished(tmp_path):
    rep = {"status": "running", "findings": [{"severity": "high", "category": "sqli", "file_path": "a.py"}]}
    assert oh(tmp_path, rep) == (1, "FAIL")


def test_openhack_garbage_report_is_do_not_file(tmp_path):
    assert oh(tmp_path, "{not json") == (1, "DO_NOT_FILE")
