"""runtime-os CLI: issue-token (secrets by reference only) and reap."""
def test_issue_token_cli_stores_by_reference_only(nava, pgdb, tmp_path, monkeypatch, capsys):
    """`revenueos-runtime-os issue-token` prints the keychain ref, never the token (2.4)."""
    import revenueos_runtime_os.__main__ as main_mod
    import revenueos_runtime_os.app as app_mod
    monkeypatch.setitem(app_mod._state, "k", nava.k)
    monkeypatch.setenv("REVENUEOS_KEYCHAIN_DIR", str(tmp_path / "kc"))
    (tmp_path / "kc").mkdir(mode=0o700)
    monkeypatch.setattr("sys.argv", ["revenueos-runtime-os", "issue-token", nava.agent])
    main_mod.main()
    out = capsys.readouterr().out.strip()
    assert out == f"keychain://nava-agent-{nava.agent}"
    stored = (tmp_path / "kc" / f"nava-agent-{nava.agent}").read_text().strip()
    assert stored.startswith("nava_") and stored not in out
    assert nava.k.authenticate(stored) == nava.agent


def test_reap_cli(nava, monkeypatch, capsys):
    import revenueos_runtime_os.__main__ as main_mod
    import revenueos_runtime_os.app as app_mod
    monkeypatch.setitem(app_mod._state, "k", nava.k)
    monkeypatch.setattr("sys.argv", ["revenueos-runtime-os", "reap", "--older-than", "60"])
    main_mod.main()          # nothing stuck: prints nothing, exits clean
    assert capsys.readouterr().out == ""
