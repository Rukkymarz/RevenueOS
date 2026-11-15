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
