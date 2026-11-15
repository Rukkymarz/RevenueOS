"""Spec 1.3: CI fails if any MCP server or service imports the MCP SDK directly instead of
going through packages/mcp-common."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SDK_IMPORT = re.compile(r"^\s*(?:from|import)\s+(?:mcp|fastmcp)(?:\.|\s|$)", re.M)
ALLOWED = ROOT / "packages" / "mcp-common"


def test_only_mcp_common_imports_the_mcp_sdk():
    offenders = []
    for base in ("mcp", "services", "infra", "apps", "packages"):
        for f in (ROOT / base).rglob("*.py"):
            if ALLOWED in f.parents or "node_modules" in f.parts:
                continue
            if SDK_IMPORT.search(f.read_text(errors="ignore")):
                offenders.append(str(f.relative_to(ROOT)))
    assert not offenders, f"direct MCP SDK imports outside mcp-common: {offenders}"


def test_every_mcp_server_has_a_manifest_and_uses_mcp_common():
    servers = [d for d in (ROOT / "mcp").iterdir() if d.is_dir()]
    assert servers
    for d in servers:
        assert (d / "manifest.json").exists(), f"{d.name} lacks manifest.json"
        code = "".join(p.read_text() for p in d.rglob("*.py"))
        assert "revenueos_mcp_common" in code, f"{d.name} does not build on mcp-common"
