"""The trace/log secret scanner (spec 2.4) finds live secret values and leak patterns, and
refuses to pass when there was nothing to scan."""
import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("scan_traces", Path(__file__).resolve().parents[2] / "scripts" / "scan_traces.py")
scan_traces = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scan_traces)


def _keychain(tmp_path):
    kc = tmp_path / "kc"
    kc.mkdir()
    (kc / "upstream-echo-token").write_text("0f" * 32 + "\n")
    (kc / "api-principals").write_text('[{"token_sha256":"' + "a" * 64 + '"}]')
    return kc


def test_clean_traces_pass(tmp_path, capsys):
    t = tmp_path / "traces.jsonl"
    t.write_text('{"name":"egress","attributes":{"injected_headers":["authorization"]}}\n')
    assert scan_traces.main(["--keychain", str(_keychain(tmp_path)), "--require", str(t), str(t)]) == 0
    assert '"PASS"' in capsys.readouterr().out


def test_leaked_secret_value_in_a_trace_fails(tmp_path, capsys):
    t = tmp_path / "traces.jsonl"
    t.write_text('{"attributes":{"http.request.header.authorization":"Bearer ' + "0f" * 32 + '"}}\n')
    assert scan_traces.main(["--keychain", str(_keychain(tmp_path)), str(t)]) == 1
    assert "upstream-echo-token" in capsys.readouterr().out


def test_leak_pattern_in_a_log_fails(tmp_path):
    log = tmp_path / "compose.log"
    log.write_text("api | starting with key AKIA" + "A" * 16 + "\n")
    assert scan_traces.main(["--keychain", str(_keychain(tmp_path)), str(log)]) == 1


def test_nothing_to_scan_is_do_not_file(tmp_path, capsys):
    assert scan_traces.main(["--keychain", str(_keychain(tmp_path)), "--require", str(tmp_path / "none.jsonl"),
                             str(tmp_path)]) == 1
    assert "DO_NOT_FILE" in capsys.readouterr().out
