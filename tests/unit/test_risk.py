"""Shared risk classification (spec 3.2): one answer for every runtime; critical blocked in
every mode including YOLO; high always needs an approval (INV-06)."""
import pytest

from revenueos_risk import blocklist, classify, decide


@pytest.mark.parametrize("tool,args", [
    ("shell.run_command", {"command": "rm -rf /"}),
    ("shell.run_command", {"command": "sudo rm -rf --no-preserve-root /"}),
    ("shell.run_command", {"command": "echo hi; dd if=/dev/zero of=/dev/sda"}),
    ("sandbox.run", {"argv": ["sh", "-c", ":(){ :|:& };:"]}),
    ("sandbox.run", {"argv": ["rm", "-rf", "/"]}),
    ("python.run_python", {"code": "import shutil; shutil.rmtree('/')"}),
    ("python.run_python", {"code": "import os\nos.system('rm -rf /')"}),
])
@pytest.mark.parametrize("mode", ["ask", "auto", "yolo"])
def test_critical_is_blocked_in_every_mode(tool, args, mode):
    r = classify(tool, args)
    assert r.critical and decide(r, mode) == "block"


def test_high_needs_approval_even_in_yolo():
    r = classify("fs.delete_file", {"path": "/etc/passwd"})
    assert r.level == "high" and decide(r, "yolo") == "prompt"


def test_medium_prompts_only_in_ask_mode():
    r = classify("gui.click", {"x": 1, "y": 1})
    assert r.level == "medium"
    assert [decide(r, m) for m in ("ask", "auto", "yolo")] == ["prompt", "auto", "auto"]


def test_low_runs_and_declared_risk_is_a_floor():
    assert decide(classify("shell.run_command", {"command": "ls -la"}), "ask") == "auto"
    r = classify("mail_send", {"to": ["x@y.test"]}, declared="high")
    assert r.level == "high" and "declared high" in r.reasons


def test_bad_inputs_are_refused():
    with pytest.raises(ValueError):
        classify("x", {}, declared="spicy")
    with pytest.raises(ValueError):
        decide(classify("x"), "turbo")


def test_sandbox_uses_the_same_blocklist():
    from revenueos_sandbox import blocklist as sandbox_blocklist
    assert sandbox_blocklist.check is blocklist.check


def test_contained_runtimes_start_code_execution_at_medium_but_arguments_still_escalate():
    assert classify("shell.run_command", {"command": "ls"}, declared="high", context="contained").level == "medium"
    assert classify("shell.run_command", {"command": "ls"}, declared="high").level == "high"   # host view
    assert classify("shell.run_command", {"command": "echo x > /etc/passwd"}, declared="high",
                    context="contained").level == "high"
    assert classify("shell.run_command", {"command": "rm -rf /"}, context="contained").critical
    assert classify("processes.kill_process", {"name": "init"}, declared="high", context="contained").critical
    with pytest.raises(ValueError):
        classify("x", {}, context="space")
