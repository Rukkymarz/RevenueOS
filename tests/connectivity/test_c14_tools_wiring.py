"""Spec 6.4: every C14 tool is built on mcp-common (so it gets auth, validation, rate limit, span, approval
gate and receipt), and nothing can bypass that: no direct tool registration, no receipts written outside
mcp-common. A tool that is declared but not registered, or registered but not declared, fails CI."""
import ast
import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
C14 = ("photo-generator", "scraper", "outreach")


def registered(server_py: Path) -> dict[str, str]:
    tools = {}
    for node in ast.walk(ast.parse(server_py.read_text())):
        if isinstance(node, ast.FunctionDef):
            for d in node.decorator_list:
                if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr == "tool":
                    risk = next(k.value.value for k in d.keywords if k.arg == "risk_class")
                    tools[d.args[0].value] = risk
    return tools


def test_every_c14_tool_is_declared_registered_and_risk_matched():
    for name in C14:
        d = ROOT / "mcp" / name
        manifest = json.loads((d / "manifest.json").read_text())
        pkg = next(p for p in d.iterdir() if p.is_dir() and p.name.startswith("revenueos_mcp_"))
        reg = registered(pkg / "server.py")
        assert reg == {t["name"]: t["risk_class"] for t in manifest["tools"]}, (name, reg)
        assert "create_server" in (pkg / "server.py").read_text()


def test_no_bypass_of_the_receipt_path():
    offenders = []
    for base in ("mcp", "services"):
        for f in (ROOT / base).rglob("*.py"):
            text = f.read_text(errors="ignore")
            if re.search(r"INSERT\s+INTO\s+tool_calls", text, re.I) or re.search(r"\.mcp\.tool\(|@mcp\.tool", text):
                offenders.append(str(f.relative_to(ROOT)))
    assert not offenders, f"tool registered or receipt written outside mcp-common: {offenders}"


def test_high_risk_outreach_send_is_the_only_c14_high_tool():
    highs = {n: [t for t, r in registered(next((ROOT / "mcp" / n).glob("revenueos_mcp_*/server.py"))).items() if r == "high"] for n in C14}
    assert highs == {"photo-generator": [], "scraper": [], "outreach": ["outreach_send"]}


def test_c14_servers_are_in_the_stack_and_get_tokens():
    compose = yaml.safe_load((ROOT / "infra" / "compose.yaml").read_text())["services"]
    boot = (ROOT / "infra" / "bootstrap.sh").read_text()
    for name in C14:
        assert name in compose and f"./mcp/{name}" in compose[name]["build"]["args"]["PACKAGES"], name
    assert "photo-generator scraper outreach" in boot
