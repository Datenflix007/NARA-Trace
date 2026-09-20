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


class NaraApiUsageResponse(BaseModel):
    request_count: int
    request_limit: int
    percent_used: float
    period: str
    reset_at: datetime
    counted_locally: bool


class SettingsResponse(BaseModel):
    mock_mode: bool
    data_dir: str
    cache_dir: str
    database_path: str
    nara_api_key_configured: bool
    nara_api_key_source: Literal["keyring", "environment", "none"]
    nara_api_usage: NaraApiUsageResponse


class SettingsUpdate(BaseModel):
    nara_api_key: SecretStr | None = Field(
        default=None,
        description="Persönlicher NARA API-Schlüssel. Wird nur im OS-Keyring gespeichert.",
    )


class ApiKeyTestResponse(BaseModel):
    ok: bool
    live_tested: bool
    message: str
    nara_api_usage: NaraApiUsageResponse | None = None


class LocalDocumentResponse(BaseModel):
    id: str
    file_name: str
    content_type: str | None
    size_bytes: int
    display_image_url: str | None
    ocr_text: str | None
    ocr_engine: str | None
    warnings: list[str]
    stored_at: datetime


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
    max_candidates: int = Field(default=50, ge=1, le=2000)
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
    preview_title: str | None = None
    preview_subtitle: str | None = None
    preview_media_url: str | None = None
    preview_media_type: Literal["image", "video", "catalog", "unknown"] | None = None


class MatchEvidenceResponse(BaseModel):
    kind: str
    label: str
    detail: str | None
    score_delta: float
    source_type: str | None


class ResultMediaPageResponse(BaseModel):
    page_id: int
    page_number: int
    label: str
    media_url: str | None
    media_type: Literal["image", "video", "catalog", "unknown"]
    original_url: str | None
    thumbnail_url: str | None
    mime_type: str | None
    transcript_text: str | None = None
    transcript_source: str | None = None
    transcript_edited: bool = False


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
    source_page_id: int | None = None
    source_page_url: str | None = None
    source_page_label: str | None = None
    transcript_text: str | None = None
    transcript_source: str | None = None
    transcript_edited: bool = False
    media_pages: list[ResultMediaPageResponse] = Field(default_factory=list)
    record_years: list[int] = Field(default_factory=list)
    highlight_terms: list[str] = Field(default_factory=list)
    evidences: list[MatchEvidenceResponse]


class TranscriptUpdate(BaseModel):
    transcript_text: str = Field(min_length=1)
