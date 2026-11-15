"""Sandbox test gating. Locally, tests needing Bubblewrap skip when bwrap is absent. CI sets
REVENUEOS_REQUIRE_SANDBOX=1, where a missing bwrap is a failure: a control that did not run
never counts as passing (INV-05)."""
import os
import shutil

import pytest

HAVE_BWRAP = shutil.which("bwrap") is not None
REQUIRED = os.environ.get("REVENUEOS_REQUIRE_SANDBOX") == "1"

if REQUIRED and not HAVE_BWRAP:
    raise RuntimeError("REVENUEOS_REQUIRE_SANDBOX=1 but bubblewrap (bwrap) is not installed")

needs_sandbox = pytest.mark.skipif(not HAVE_BWRAP, reason="bubblewrap not installed (required in CI)")
