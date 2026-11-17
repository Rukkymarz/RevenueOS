"""Sandbox test gating. Locally, tests needing Bubblewrap (or the real aegis-os binary) skip
when the tool is absent. CI sets REVENUEOS_REQUIRE_SANDBOX=1 / REVENUEOS_REQUIRE_AEGIS=1, where
a missing tool is a failure: a control that did not run never counts as passing (INV-05, D10)."""
import os
import shutil

import pytest

HAVE_BWRAP = shutil.which("bwrap") is not None
REQUIRED = os.environ.get("REVENUEOS_REQUIRE_SANDBOX") == "1"

if REQUIRED and not HAVE_BWRAP:
    raise RuntimeError("REVENUEOS_REQUIRE_SANDBOX=1 but bubblewrap (bwrap) is not installed")

needs_sandbox = pytest.mark.skipif(not HAVE_BWRAP, reason="bubblewrap not installed (required in CI)")

HAVE_AEGIS = shutil.which("aegis-os") is not None
AEGIS_REQUIRED = os.environ.get("REVENUEOS_REQUIRE_AEGIS") == "1"

if AEGIS_REQUIRED and not HAVE_AEGIS:
    raise RuntimeError("REVENUEOS_REQUIRE_AEGIS=1 but the aegis-os binary is not installed")

needs_aegis = pytest.mark.skipif(not HAVE_AEGIS, reason="aegis-os binary not installed (required in CI)")
