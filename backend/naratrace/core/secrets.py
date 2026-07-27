from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

import keyring
from pydantic import SecretStr

from naratrace.core.config import get_settings

SERVICE_NAME = "NARATrace"
ACCOUNT_NAME = "nara-api-key"


@dataclass(frozen=True)
class NaraApiKeyStatus:
    configured: bool
    source: Literal["keyring", "environment", "none"]


def get_nara_api_key() -> tuple[str | None, Literal["keyring", "environment", "none"]]:
    keyring_value = _read_keyring_value()
    if keyring_value and keyring_value.strip():
        return keyring_value.strip(), "keyring"

    env_value = os.getenv("NARA_API_KEY")
    if env_value and env_value.strip():
        return env_value.strip(), "environment"

    settings_value = get_settings().nara_api_key
    if settings_value:
        secret = settings_value.get_secret_value().strip()
        if secret:
            return secret, "environment"

    return None, "none"


def get_nara_api_key_status() -> NaraApiKeyStatus:
    key, source = get_nara_api_key()
    return NaraApiKeyStatus(configured=bool(key), source=source)


def set_nara_api_key(value: SecretStr) -> None:
    secret = value.get_secret_value().strip()
    if not secret:
        raise RuntimeError("Der NARA API-Schlüssel darf nicht leer sein.")
    try:
        keyring.set_password(SERVICE_NAME, ACCOUNT_NAME, secret)
    except Exception as exc:  # pragma: no cover - depends on OS keyring backend
        raise RuntimeError("Der NARA API-Schlüssel konnte nicht im OS-Keyring gespeichert werden.") from exc


def delete_nara_api_key() -> None:
    try:
        keyring.delete_password(SERVICE_NAME, ACCOUNT_NAME)
    except keyring.errors.PasswordDeleteError:
        return
    except Exception as exc:  # pragma: no cover - depends on OS keyring backend
        raise RuntimeError("Der NARA API-Schlüssel konnte nicht aus dem OS-Keyring gelöscht werden.") from exc


def _read_keyring_value() -> str | None:
    try:
        return keyring.get_password(SERVICE_NAME, ACCOUNT_NAME)
    except Exception:
        return None
