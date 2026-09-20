from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from naratrace import __version__


class AppSettings(BaseSettings):
    app_name: str = "NARATrace"
    version: str = __version__
    host: str = Field(default="127.0.0.1", alias="NARATRACE_HOST")
    port: int = Field(default=8765, alias="NARATRACE_PORT")
    mock_mode: bool = Field(default=False, alias="NARATRACE_MOCK_MODE")
    log_level: str = Field(default="info", alias="NARATRACE_LOG_LEVEL")
    data_dir: str | None = Field(default=None, alias="NARATRACE_DATA_DIR")
    nara_api_key: SecretStr | None = Field(default=None, alias="NARA_API_KEY")
    nara_monthly_request_limit: int = Field(default=10000, ge=1, alias="NARATRACE_NARA_MONTHLY_REQUEST_LIMIT")
    a3340_index_concurrency: int = Field(default=16, ge=1, le=32, alias="NARATRACE_A3340_INDEX_CONCURRENCY")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    return AppSettings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
