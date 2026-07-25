from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, SecretStr


class HealthResponse(BaseModel):
    status: Literal["ok"]
    app: str
    version: str
    mock_mode: bool
    bind_host: str
    bind_port: int
    data_dir: str
    database_path: str


class SettingsResponse(BaseModel):
    mock_mode: bool
    data_dir: str
    cache_dir: str
    database_path: str
    nara_api_key_configured: bool
    nara_api_key_source: Literal["keyring", "environment", "none"]


class SettingsUpdate(BaseModel):
    nara_api_key: SecretStr | None = Field(
        default=None,
        description="Persönlicher NARA API-Schlüssel. Wird nur im OS-Keyring gespeichert.",
    )


class ApiKeyTestResponse(BaseModel):
    ok: bool
    live_tested: bool
    message: str


class SearchRequest(BaseModel):
    first_name: str | None = None
    last_name: str = Field(min_length=1)
    variants: str | None = None
    birth_date: str | None = None
    birth_year: int | None = Field(default=None, ge=0, le=2100)
    residence_places: str | None = None
    membership_number: str | None = None
    naid: str | None = None
    record_group: str | None = None
    max_candidates: int = Field(default=50, ge=1, le=500)
    demo_mode: bool = False


class SearchJobResponse(BaseModel):
    id: str
    status: str
    mode: str
    title: str | None
    progress_current: int
    progress_total: int
    warnings: list[str]
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None
    result_count: int
    mock_mode: bool


class MatchEvidenceResponse(BaseModel):
    kind: str
    label: str
    detail: str | None
    score_delta: float
    source_type: str | None


class SearchResultResponse(BaseModel):
    id: int
    job_id: str
    match_score: float
    category: str
    suspected_person_name: str | None
    birth_date: str | None
    birth_place: str | None
    relevant_pages_count: int
    naid: str
    title: str | None
    record_group: str | None
    series: str | None
    original_url: str | None
    text_origin: str
    data_source: Literal["NARA", "MOCK", "LOCAL"]
    retrieved_at: datetime | None
    evidences: list[MatchEvidenceResponse]
