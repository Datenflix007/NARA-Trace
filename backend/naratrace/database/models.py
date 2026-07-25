from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from naratrace.database.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def uuid_str() -> str:
    return str(uuid4())


class SearchJob(Base):
    __tablename__ = "search_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="queued")
    mode: Mapped[str] = mapped_column(String(64), nullable=False, default="quick")
    title: Mapped[str | None] = mapped_column(String(512))
    progress_current: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warnings: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    profile: Mapped["SearchProfile | None"] = relationship(
        back_populates="job",
        uselist=False,
        cascade="all, delete-orphan",
    )
    queries: Mapped[list["SearchQuery"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    candidate_records: Mapped[list["CandidateRecord"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    results: Mapped[list["SearchResult"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    evidences: Mapped[list["MatchEvidence"]] = relationship(back_populates="job", cascade="all, delete-orphan")


class SearchProfile(Base):
    __tablename__ = "search_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("search_jobs.id", ondelete="CASCADE"), unique=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(512))
    mock_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    job: Mapped["SearchJob"] = relationship(back_populates="profile")
    fields: Mapped[list["SearchField"]] = relationship(back_populates="profile", cascade="all, delete-orphan")


class SearchField(Base):
    __tablename__ = "search_fields"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("search_profiles.id", ondelete="CASCADE"), nullable=False)
    section: Mapped[str] = mapped_column(String(128), nullable=False)
    field_name: Mapped[str] = mapped_column(String(128), nullable=False)
    original_value: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_value: Mapped[str | None] = mapped_column(Text)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)

    profile: Mapped["SearchProfile"] = relationship(back_populates="fields")
    variants: Mapped[list["SearchVariant"]] = relationship(back_populates="field", cascade="all, delete-orphan")


class SearchVariant(Base):
    __tablename__ = "search_variants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("search_fields.id", ondelete="CASCADE"), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_value: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)

    field: Mapped["SearchField"] = relationship(back_populates="variants")


class SearchQuery(Base):
    __tablename__ = "search_queries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("search_jobs.id", ondelete="CASCADE"), nullable=False)
    phase: Mapped[str] = mapped_column(String(128), nullable=False)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    endpoint: Mapped[str] = mapped_column(String(512), nullable=False)
    params: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    result_count: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    job: Mapped["SearchJob"] = relationship(back_populates="queries")


class CandidateRecord(Base):
    __tablename__ = "candidate_records"
    __table_args__ = (UniqueConstraint("job_id", "naid", name="uq_candidate_records_job_naid"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("search_jobs.id", ondelete="CASCADE"), nullable=False)
    naid: Mapped[str] = mapped_column(String(128), nullable=False)
    parent_naid: Mapped[str | None] = mapped_column(String(128))
    title: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    record_group: Mapped[str | None] = mapped_column(Text)
    series: Mapped[str | None] = mapped_column(Text)
    local_identifier: Mapped[str | None] = mapped_column(String(512))
    original_url: Mapped[str | None] = mapped_column(Text)
    rights_statement: Mapped[str | None] = mapped_column(Text)
    has_digital_objects: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    text_origin: Mapped[str] = mapped_column(String(128), nullable=False, default="kein Text verfügbar")
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    job: Mapped["SearchJob"] = relationship(back_populates="candidate_records")
    digital_objects: Mapped[list["DigitalObject"]] = relationship(back_populates="candidate_record", cascade="all, delete-orphan")
    evidences: Mapped[list["MatchEvidence"]] = relationship(back_populates="candidate_record")
    result: Mapped["SearchResult | None"] = relationship(back_populates="candidate_record", uselist=False)


class DigitalObject(Base):
    __tablename__ = "digital_objects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_record_id: Mapped[int] = mapped_column(ForeignKey("candidate_records.id", ondelete="CASCADE"), nullable=False)
    object_id: Mapped[str | None] = mapped_column(String(256))
    object_type: Mapped[str | None] = mapped_column(String(128))
    url: Mapped[str | None] = mapped_column(Text)
    thumbnail_url: Mapped[str | None] = mapped_column(Text)
    file_name: Mapped[str | None] = mapped_column(String(512))
    mime_type: Mapped[str | None] = mapped_column(String(128))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    candidate_record: Mapped["CandidateRecord"] = relationship(back_populates="digital_objects")
    pages: Mapped[list["CandidatePage"]] = relationship(back_populates="digital_object", cascade="all, delete-orphan")


class CandidatePage(Base):
    __tablename__ = "candidate_pages"
    __table_args__ = (UniqueConstraint("digital_object_id", "page_number", name="uq_candidate_pages_object_page"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    digital_object_id: Mapped[int] = mapped_column(ForeignKey("digital_objects.id", ondelete="CASCADE"), nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    image_url: Mapped[str | None] = mapped_column(Text)
    thumbnail_path: Mapped[str | None] = mapped_column(Text)
    local_path: Mapped[str | None] = mapped_column(Text)
    original_url: Mapped[str | None] = mapped_column(Text)
    is_relevant: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    digital_object: Mapped["DigitalObject"] = relationship(back_populates="pages")
    texts: Mapped[list["ExtractedText"]] = relationship(back_populates="page", cascade="all, delete-orphan")
    evidences: Mapped[list["MatchEvidence"]] = relationship(back_populates="candidate_page")
    manual_corrections: Mapped[list["ManualCorrection"]] = relationship(back_populates="page", cascade="all, delete-orphan")


class ExtractedText(Base):
    __tablename__ = "extracted_texts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("candidate_pages.id", ondelete="CASCADE"), nullable=False)
    raw_text: Mapped[str | None] = mapped_column(Text)
    normalized_text: Mapped[str | None] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(128), nullable=False)
    engine: Mapped[str | None] = mapped_column(String(128))
    engine_version: Mapped[str | None] = mapped_column(String(128))
    language: Mapped[str | None] = mapped_column(String(32))
    confidence: Mapped[float | None] = mapped_column(Float)
    human_reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    manually_corrected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    page: Mapped["CandidatePage"] = relationship(back_populates="texts")
    manual_corrections: Mapped[list["ManualCorrection"]] = relationship(back_populates="extracted_text")


class MatchEvidence(Base):
    __tablename__ = "match_evidences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("search_jobs.id", ondelete="CASCADE"), nullable=False)
    candidate_record_id: Mapped[int | None] = mapped_column(ForeignKey("candidate_records.id", ondelete="CASCADE"))
    candidate_page_id: Mapped[int | None] = mapped_column(ForeignKey("candidate_pages.id", ondelete="CASCADE"))
    result_id: Mapped[int | None] = mapped_column(ForeignKey("search_results.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(512), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    score_delta: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    source_type: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    job: Mapped["SearchJob"] = relationship(back_populates="evidences")
    candidate_record: Mapped["CandidateRecord | None"] = relationship(back_populates="evidences")
    candidate_page: Mapped["CandidatePage | None"] = relationship(back_populates="evidences")
    result: Mapped["SearchResult | None"] = relationship(back_populates="evidences")


class SearchResult(Base):
    __tablename__ = "search_results"
    __table_args__ = (UniqueConstraint("job_id", "candidate_record_id", name="uq_search_results_job_record"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("search_jobs.id", ondelete="CASCADE"), nullable=False)
    candidate_record_id: Mapped[int] = mapped_column(ForeignKey("candidate_records.id", ondelete="CASCADE"), nullable=False)
    match_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="möglich")
    suspected_person_name: Mapped[str | None] = mapped_column(String(512))
    birth_date: Mapped[str | None] = mapped_column(String(64))
    birth_place: Mapped[str | None] = mapped_column(String(512))
    relevant_pages_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    job: Mapped["SearchJob"] = relationship(back_populates="results")
    candidate_record: Mapped["CandidateRecord"] = relationship(back_populates="result")
    evidences: Mapped[list["MatchEvidence"]] = relationship(back_populates="result")


class ManualCorrection(Base):
    __tablename__ = "manual_corrections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("candidate_pages.id", ondelete="CASCADE"), nullable=False)
    extracted_text_id: Mapped[int | None] = mapped_column(ForeignKey("extracted_texts.id", ondelete="SET NULL"))
    previous_text: Mapped[str | None] = mapped_column(Text)
    corrected_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    page: Mapped["CandidatePage"] = relationship(back_populates="manual_corrections")
    extracted_text: Mapped["ExtractedText | None"] = relationship(back_populates="manual_corrections")


class ApplicationSetting(Base):
    __tablename__ = "application_settings"

    key: Mapped[str] = mapped_column(String(256), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class CacheEntry(Base):
    __tablename__ = "cache_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cache_key: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    namespace: Mapped[str] = mapped_column(String(128), nullable=False)
    request_url: Mapped[str | None] = mapped_column(Text)
    request_params: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    response_body: Mapped[str | None] = mapped_column(Text)
    status_code: Mapped[int | None] = mapped_column(Integer)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
