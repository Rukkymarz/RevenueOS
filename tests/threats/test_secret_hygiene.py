"""Q7 (Phase 1 subset): no literal secrets in the repository, and the ledger never stores
secret values. Full threat-model suite grows phase by phase (spec 15.2)."""
import re
import subprocess
from pathlib import Path

from revenueos_common.canonical import redact

ROOT = Path(__file__).resolve().parents[2]
PATTERNS = {
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "aws key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "github token": re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"),
    "slack token": re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    "openai/anthropic key": re.compile(r"sk-(?:ant-)?[A-Za-z0-9_-]{32,}"),
    "password assignment": re.compile(r"(?i)(?:password|passwd|secret)\s*[:=]\s*['\"][^'\"$<{]{8,}['\"]"),
}


def tracked_files():
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    return [ROOT / f for f in out if (ROOT / f).is_file() and (ROOT / f).stat().st_size < 2_000_000]


def test_no_literal_secrets_in_tracked_files():
    hits = []
    for f in tracked_files():
        if f.suffix in (".png", ".jpg", ".ico", ".woff2"):
            continue
        text = f.read_text(errors="ignore")
        for name, rx in PATTERNS.items():
            if rx.search(text) and "tests/threats" not in str(f):
                hits.append(f"{f.relative_to(ROOT)}: {name}")
    assert not hits, hits


def test_secret_directories_are_git_ignored():
    for p in ["infra/secrets/pgpass", "infra/secrets/keychain/x", ".env"]:
        r = subprocess.run(["git", "check-ignore", "-q", p], cwd=ROOT)
        assert r.returncode == 0, f"{p} is not git-ignored"


def test_previews_and_logs_redact_secret_fields():
    payload = {"to": "a@b.co", "api_key": "k", "headers": {"Authorization": "Bearer t", "Cookie": "c"}}
    assert redact(payload) == {"to": "a@b.co", "api_key": "[redacted]",
                               "headers": {"Authorization": "[redacted]", "Cookie": "[redacted]"}}
