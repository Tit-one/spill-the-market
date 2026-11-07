def test_explicit_mirofish_env_reuse_is_whitelisted_and_not_executed(tmp_path, monkeypatch):
    from spill_market.settings import load_env_file
    monkeypatch.delenv("SPILL_LLM_API_KEY", raising=False)
    monkeypatch.delenv("SPILL_LLM_MODEL", raising=False)
    monkeypatch.delenv("SPILL_LLM_BASE_URL", raising=False)
    path = tmp_path / "source.env"
    path.write_text('LLM_API_KEY="test-literal-$(not-executed)"\nLLM_MODEL_NAME="example-model"\n'
                    'LLM_BASE_URL=https://example.com/v1\nPYTHONPATH=untrusted\n', encoding="utf-8")
    metadata = load_env_file(path)
    import os
    assert os.environ["SPILL_LLM_API_KEY"] == "test-literal-$(not-executed)"
    assert os.environ["SPILL_LLM_MODEL"] == "example-model"
    assert "test-literal" not in str(metadata)
    assert "PYTHONPATH" not in metadata["loaded"]


def test_existing_environment_wins_and_no_implicit_file_scan(tmp_path, monkeypatch):
    from spill_market.settings import load_env_file
    monkeypatch.setenv("SPILL_LLM_API_KEY", "existing-test-value")
    path = tmp_path / ".env"
    path.write_text("SPILL_LLM_API_KEY=replacement-test-value\n", encoding="utf-8")
    load_env_file(path)
    import os
    assert os.environ["SPILL_LLM_API_KEY"] == "existing-test-value"
