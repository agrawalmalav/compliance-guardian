import os
import pytest
from compliance_guardian.ui.pipeline_api import RunConfig, _set_api_key


def test_set_api_key_uses_env(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "from_env")
    cfg = RunConfig(provider="openai")
    assert _set_api_key(cfg) == "openai"
    assert os.getenv("OPENAI_API_KEY") == "from_env"


def test_set_api_key_missing(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    cfg = RunConfig(provider="gemini")
    with pytest.raises(RuntimeError):
        _set_api_key(cfg)
