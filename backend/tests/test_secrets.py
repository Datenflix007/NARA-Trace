from __future__ import annotations

from naratrace.core import secrets
from naratrace.core.config import reset_settings_cache


def test_get_nara_api_key_reads_dotenv_fallback(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("NARA_API_KEY", raising=False)
    monkeypatch.setattr(secrets, "_read_keyring_value", lambda: None)
    (tmp_path / ".env").write_text("NARA_API_KEY=dotenv-test-key\n", encoding="utf-8")
    reset_settings_cache()

    try:
        api_key, source = secrets.get_nara_api_key()
    finally:
        reset_settings_cache()

    assert api_key == "dotenv-test-key"
    assert source == "environment"


def test_get_nara_api_key_prefers_keyring_over_environment(monkeypatch):
    monkeypatch.setenv("NARA_API_KEY", "env-test-key")
    monkeypatch.setattr(secrets, "_read_keyring_value", lambda: " keyring-test-key ")
    reset_settings_cache()

    try:
        api_key, source = secrets.get_nara_api_key()
    finally:
        reset_settings_cache()

    assert api_key == "keyring-test-key"
    assert source == "keyring"
