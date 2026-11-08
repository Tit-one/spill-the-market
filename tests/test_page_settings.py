import json

import pytest

from spill_market.settings import load_provider_profile
from spill_market.settings import load_env_file


def test_saved_profile_reuses_selected_env_without_copying_key(tmp_path, monkeypatch):
    source = tmp_path / 'chosen.env'
    source.write_text('LLM_API_KEY=unit-test-placeholder\nLLM_MODEL_NAME=vision-test\n', encoding='utf-8')
    for name in ('SPILL_LLM_API_KEY', 'SPILL_LLM_MODEL', 'SPILL_VISION_ENABLED'):
        monkeypatch.delenv(name, raising=False)
    profile = {'env_file':str(source), 'public_settings':{'SPILL_VISION_ENABLED':'true'}}
    (tmp_path / 'provider-profile.json').write_text(json.dumps(profile), encoding='utf-8')
    result = load_provider_profile(tmp_path)
    import os
    assert os.environ['SPILL_LLM_API_KEY']=='unit-test-placeholder'
    assert os.environ['SPILL_VISION_ENABLED']=='true'
    assert result['values_disclosed'] is False
    assert 'unit-test-placeholder' not in (tmp_path / 'provider-profile.json').read_text()


def test_saved_profile_rejects_inline_credentials_and_preserves_explicit_env(tmp_path, monkeypatch):
    p = tmp_path / 'provider-profile.json'
    p.write_text(json.dumps({'public_settings':{'SPILL_LLM_API_KEY':'forbidden'}}))
    with pytest.raises(ValueError, match='public'):
        load_provider_profile(tmp_path)
    monkeypatch.setenv('SPILL_VISION_MODEL','explicit')
    p.write_text(json.dumps({'public_settings':{'SPILL_VISION_MODEL':'saved'}}))
    load_provider_profile(tmp_path)
    import os
    assert os.environ['SPILL_VISION_MODEL']=='explicit'


def test_explicit_mirofish_credential_reference_is_resolved_without_shell_expansion(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','unit-test-reference-value')
    monkeypatch.delenv('SPILL_LLM_API_KEY',raising=False)
    selected = tmp_path/'selected.env'
    selected.write_text('LLM_API_KEY=${OPENAI_API_KEY}\n',encoding='utf-8')
    load_env_file(selected)
    import os
    assert os.environ['SPILL_LLM_API_KEY']=='unit-test-reference-value'


def test_unresolved_reference_is_an_actionable_configuration_error(tmp_path, monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    monkeypatch.delenv('SPILL_LLM_API_KEY',raising=False)
    selected = tmp_path/'selected.env'
    selected.write_text('LLM_API_KEY=${OPENAI_API_KEY}\n',encoding='utf-8')
    with pytest.raises(ValueError,match='OPENAI_API_KEY'):
        load_env_file(selected)


def test_mirofish_reference_to_key_in_same_file_is_resolved(tmp_path, monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    monkeypatch.delenv('SPILL_LLM_API_KEY',raising=False)
    selected = tmp_path/'selected.env'
    selected.write_text('OPENAI_API_KEY=unit-test-same-file\nLLM_API_KEY=${OPENAI_API_KEY}\n',encoding='utf-8')
    load_env_file(selected)
    import os
    assert os.environ['SPILL_LLM_API_KEY']=='unit-test-same-file'
