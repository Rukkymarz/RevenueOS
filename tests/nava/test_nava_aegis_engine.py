"""`sandbox.run`'s `engine="aegis"` argument, as seen by the real NAVA gateway's own validation
(step 1 -- before `classify`, so it runs cleanly even without `omnipilot` installed; see
tests/unit/test_tools_sandbox_engine.py for the engine actually running, which goes through
`shell_run()` directly for that reason)."""


def test_sandbox_run_schema_accepts_engine_aegis_value(nava):
    # "aegis" is a valid enum value: validation (step 1) passes and the call proceeds past it.
    # It then fails at classify (no `omnipilot` package in this sandbox -- a pre-existing,
    # unrelated environment gap; tests/nava/test_nava_invariants.py already has the same failure
    # on over half its tests). What this proves is narrower, and still useful: "aegis" is not
    # rejected as an unknown argument value.
    r = nava.call(tool="sandbox.run", args={"workspace": "w", "argv": ["true"], "engine": "aegis"})
    assert r.step != "validate"


def test_sandbox_run_schema_rejects_unknown_engine(nava):
    r = nava.call(tool="sandbox.run", args={"workspace": "w", "argv": ["true"], "engine": "openhands"})
    assert r.status == "denied" and r.step == "validate"
