from __future__ import annotations

import asyncio
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import delete, desc, func, select
from sqlalchemy.orm import Session, selectinload

from naratrace.api.schemas import (
    MatchEvidenceResponse,
    ResultMediaPageResponse,
    SearchJobResponse,
    SearchRequest,
    SearchResultResponse,
)
from naratrace.core.config import get_settings
from naratrace.core.secrets import get_nara_api_key
from naratrace.database.models import (
    CandidateRecord,
    CandidatePage,
    DigitalObject,
    ExtractedText,
    ManualCorrection,
    MatchEvidence,
    SearchField,
    SearchJob,
    SearchProfile,
    SearchQuery,
    SearchResult,
    SearchVariant,
)
from naratrace.database.session import session_scope
from naratrace.nara.client import NaraCatalogClient, NaraClientError, NaraRecord, NaraSearchResponse
from naratrace.processing.documents import (
    MaterializedPage,
    ensure_display_image,
    is_browser_display_url,
    is_browser_video_file,
    is_browser_video_url,
    materialize_digital_object,
    materialize_relevant_pages,
)
from naratrace.nsdap.manifest import NsdapDataError
from naratrace.nsdap.models import FrameMatch
from naratrace.processing.nsdap_candidates import NsdapCandidate, retrieve_nsdap_candidates


LOCAL_DEMO_PDF_PATH = Path.home() / "Downloads" / "SchulzeNaumburg_NSDAP_Kartei1931.pdf"
LOCAL_DEMO_PDF_SERIES = "A3340-MFKL-R0013.pdf"
LOCAL_DEMO_PDF_PAGE_COUNT = 4
NARA_QUERY_MAX_LENGTH = 1024
NARA_SEARCH_PAGE_SIZE = 100
NARA_SEARCH_MAX_CANDIDATES = 2000
RECORD_YEAR_PATTERN = re.compile(r"\b(17\d{2}|18\d{2}|19\d{2}|20\d{2})\b")
TERMINAL_JOB_STATUSES = {"complete", "failed", "cancelled"}


async def create_search_job(payload: SearchRequest) -> SearchJobResponse:
    settings = get_settings()
    mock_mode = settings.mock_mode or payload.demo_mode
    with session_scope() as session:
        title = build_job_title(payload)
        now = datetime.now(timezone.utc)
        job = SearchJob(
            status="queued",
            mode="quick",
            title=title,
            progress_current=0,
            progress_total=8,
            started_at=now,
            warnings=[],
        )
        session.add(job)
        session.flush()

        profile = SearchProfile(job_id=job.id, display_name=title, mock_mode=mock_mode)
        session.add(profile)
        session.flush()
        add_profile_fields(session, profile, payload)
        add_queries(session, job, payload)

        session.flush()
        return serialize_job(session, job.id)


async def run_search_job(job_id: str, payload: SearchRequest) -> None:
    try:
        await execute_search_job(job_id, payload)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        fail_search_job(job_id, "Interner Fehler beim Suchlauf.", [str(exc)])


async def execute_search_job(job_id: str, payload: SearchRequest) -> None:
    settings = get_settings()
    mock_mode = settings.mock_mode or payload.demo_mode
    if not update_job_state(job_id, "preparing_search", 1):
        return

    with session_scope() as session:
        job = session.get(SearchJob, job_id)
        if job is None or job.status == "cancelled":
            return
        title = job.title or build_job_title(payload)
        if mock_mode:
            add_mock_results(session, job, title)
            job.status = "complete"
            job.progress_current = 6
            job.completed_at = datetime.now(timezone.utc)
            job.warnings = [
                "Demo-Modus: Treffer stammen aus lokalen Demo-Daten oder künstlichen Beispieldaten.",
                "Echte NARA-Daten werden nur mit gültigem NARA API-Schlüssel abgerufen.",
            ]
            session.flush()
            return

        api_key, key_source = get_nara_api_key()
    if not update_job_state(job_id, "indexing_a3340_corpus", 2):
        return
    try:
        nsdap_candidates, nsdap_warnings = await retrieve_nsdap_candidates(payload)
    except NsdapDataError as exc:
        nsdap_candidates, nsdap_warnings = [], [str(exc)]

    if nsdap_candidates:
        if not update_job_state(job_id, "materializing_card_frames", 4):
            return
        stored_count, materialization_warnings = await store_nsdap_candidates(job_id, payload, nsdap_candidates)
        if not update_job_state(job_id, "ranking", 7):
            return
        with session_scope() as session:
            job = session.get(SearchJob, job_id)
            if job is None or job.status == "cancelled":
                return
            job.status = "complete"
            job.progress_current = 8
            job.completed_at = datetime.now(timezone.utc)
            job.warnings = nsdap_warnings + materialization_warnings
            job.warnings.append("A3340-Ergebnisse verweisen auf einzelne Kartenframes, nicht auf ein Rollen-PDF.")
            if stored_count == 0:
                job.warnings.append("A3340-Frames wurden gefunden, konnten aber nicht als Kartenansicht gespeichert werden.")
            session.flush()
        return

    if not api_key:
        fail_search_job(
            job_id,
            "NARA API-Schlüssel fehlt.",
            nsdap_warnings
            + [
                "Bitte in den Einstellungen einen NARA API-Schluessel speichern oder NARA_API_KEY setzen.",
                "Ohne gültigen Schlüssel kann NARATrace keine echten NARA-Treffer abrufen.",
            ],
        )
        return

    if not update_job_state(job_id, "searching_catalog", 3):
        return
    try:
        nara_response = await run_nara_candidate_search(payload, api_key)
    except NaraClientError as exc:
        fail_search_job(job_id, str(exc), [str(exc), f"API-Schlüsselquelle: {key_source}."])
        return

    if is_search_job_cancelled(job_id):
        return
    if not update_job_state(job_id, "downloading_pages_ocr", 5):
        return
    stored_count, materialization_warnings = await store_nara_candidates(job_id, payload, nara_response)
    if not update_job_state(job_id, "ranking", 7):
        return
    with session_scope() as session:
        job = session.get(SearchJob, job_id)
        if job is None or job.status == "cancelled":
            return
        job.status = "complete"
        job.progress_current = 8
        job.completed_at = datetime.now(timezone.utc)
        job.warnings = list(getattr(nara_response, "warnings", []))
        job.warnings.extend(materialization_warnings)
        if stored_count == 0:
            job.warnings.extend(
                [
                    "NARA-Abfrage erfolgreich, aber keine Kandidaten gefunden.",
                    "Versuche weniger enge Angaben oder andere Namensvarianten.",
                ]
            )
        session.flush()


def update_job_state(job_id: str, status: str, progress_current: int) -> bool:
    with session_scope() as session:
        job = session.get(SearchJob, job_id)
        if job is None:
            return False
        if job.status in TERMINAL_JOB_STATUSES:
            return False
        job.status = status
        job.progress_current = progress_current
        session.flush()
        return True


def fail_search_job(job_id: str, message: str, warnings: list[str] | None = None) -> None:
    with session_scope() as session:
        job = session.get(SearchJob, job_id)
        if job is None:
            return
        if job.status == "cancelled":
            return
        job.status = "failed"
        job.completed_at = datetime.now(timezone.utc)
        job.error_message = message
        job.warnings = warnings or [message]
        session.flush()


def is_search_job_cancelled(job_id: str) -> bool:
    with session_scope() as session:
        job = session.get(SearchJob, job_id)
        return job is None or job.status == "cancelled"


def cancel_search_job(job_id: str) -> SearchJobResponse | None:
    with session_scope() as session:
        job = session.get(SearchJob, job_id)
        if job is None:
            return None
        if job.status not in TERMINAL_JOB_STATUSES:
            job.status = "cancelled"
            job.completed_at = datetime.now(timezone.utc)
            job.warnings = [
                *(job.warnings or []),
                "Suchjob wurde vom Benutzer abgebrochen.",
            ]
            session.flush()
        return serialize_job(session, job.id)


def list_search_jobs(limit: int = 20) -> list[SearchJobResponse]:
    with session_scope() as session:
        jobs = session.scalars(
            select(SearchJob).options(selectinload(SearchJob.profile)).order_by(desc(SearchJob.created_at)).limit(limit)
        ).all()
        job_ids = [job.id for job in jobs]
        if not job_ids:
            return []
        result_counts = dict(
            session.execute(
                select(SearchResult.job_id, func.count(SearchResult.id))
                .where(SearchResult.job_id.in_(job_ids))
                .group_by(SearchResult.job_id)
            ).all()
        )
        previews = build_job_previews(session, job_ids)
        return [serialize_job_model(job, result_counts.get(job.id, 0), previews.get(job.id)) for job in jobs]


def get_search_job(job_id: str) -> SearchJobResponse | None:
    with session_scope() as session:
        if not session.get(SearchJob, job_id):
            return None
        return serialize_job(session, job_id)


def get_search_results(job_id: str) -> list[SearchResultResponse] | None:
    with session_scope() as session:
        if not session.get(SearchJob, job_id):
            return None
        results = session.scalars(
            select(SearchResult)
            .where(SearchResult.job_id == job_id)
            .options(
                selectinload(SearchResult.candidate_record),
                selectinload(SearchResult.candidate_record)
                .selectinload(CandidateRecord.digital_objects)
                .selectinload(DigitalObject.pages)
                .selectinload(CandidatePage.texts),
                selectinload(SearchResult.candidate_record)
                .selectinload(CandidateRecord.digital_objects)
                .selectinload(DigitalObject.pages)
                .selectinload(CandidatePage.manual_corrections),
                selectinload(SearchResult.evidences),
            )
            .order_by(desc(SearchResult.match_score))
        ).all()
        return [serialize_result(result) for result in results]


def delete_search_job(job_id: str) -> bool:
    with session_scope() as session:
        job = session.get(SearchJob, job_id)
        if job is None:
            return False
        session.delete(job)
        session.flush()
        return True


def delete_search_result(job_id: str, result_id: int) -> bool:
    with session_scope() as session:
        result = session.scalar(
            select(SearchResult).where(SearchResult.job_id == job_id, SearchResult.id == result_id)
        )
        if result is None:
            return False
        session.execute(delete(MatchEvidence).where(MatchEvidence.result_id == result.id))
        session.delete(result)
        session.flush()
        return True


def update_search_result_transcript(job_id: str, result_id: int, transcript_text: str) -> SearchResultResponse | None:
    with session_scope() as session:
        result = load_result_for_serialization(session, job_id, result_id)
        if result is None:
            return None
        page = get_relevant_page(result) or create_transcript_only_page(session, result)
        previous_text, _, _ = current_page_text(page)
        selected_text = select_current_extracted_text(page)
        if selected_text is not None:
            selected_text.human_reviewed = True
            selected_text.manually_corrected = True
        session.add(
            ManualCorrection(
                page=page,
                extracted_text=selected_text,
                previous_text=previous_text,
                corrected_text=transcript_text,
            )
        )
        session.flush()
        refreshed = load_result_for_serialization(session, job_id, result_id)
        assert refreshed is not None
        return serialize_result(refreshed)


def get_candidate_page_media_path(page_id: int) -> Path | None:
    with session_scope() as session:
        page = session.get(CandidatePage, page_id)
        if page is None or not page.local_path:
            return None
        path = Path(page.local_path)
        if not path.exists() or not path.is_file():
            return None
        if is_browser_video_file(path):
            return path
        display_path = ensure_display_image(path)
        if not display_path.exists() or not display_path.is_file():
            return None
        return display_path


def get_candidate_page_image_path(page_id: int) -> Path | None:
    media_path = get_candidate_page_media_path(page_id)
    if media_path is None or is_browser_video_file(media_path):
        return None
    return media_path


def load_result_for_serialization(session: Session, job_id: str, result_id: int) -> SearchResult | None:
    return session.scalar(
        select(SearchResult)
        .where(SearchResult.job_id == job_id, SearchResult.id == result_id)
        .options(
            selectinload(SearchResult.candidate_record)
            .selectinload(CandidateRecord.digital_objects)
            .selectinload(DigitalObject.pages)
            .selectinload(CandidatePage.texts),
            selectinload(SearchResult.candidate_record)
            .selectinload(CandidateRecord.digital_objects)
            .selectinload(DigitalObject.pages)
            .selectinload(CandidatePage.manual_corrections),
            selectinload(SearchResult.evidences),
        )
    )


def create_transcript_only_page(session: Session, result: SearchResult) -> CandidatePage:
    digital_object = DigitalObject(
        candidate_record_id=result.candidate_record_id,
        object_type="transcript-only",
        retrieved_at=datetime.now(timezone.utc),
    )
    session.add(digital_object)
    session.flush()
    page = CandidatePage(
        digital_object_id=digital_object.id,
        page_number=1,
        is_relevant=True,
        retrieved_at=datetime.now(timezone.utc),
    )
    session.add(page)
    session.flush()
    return page


def select_current_extracted_text(page: CandidatePage) -> ExtractedText | None:
    texts = [text for text in page.texts if text.raw_text and text.raw_text.strip()]
    texts.sort(key=text_priority)
    return texts[0] if texts else None


def build_job_title(payload: SearchRequest) -> str:
    name = " ".join(value for value in [payload.first_name, payload.last_name] if value).strip()
    return name or payload.last_name


def add_profile_fields(session: Session, profile: SearchProfile, payload: SearchRequest) -> None:
    fields = [
        ("name", "first_name", payload.first_name, 1.0),
        ("name", "last_name", payload.last_name, 1.5),
        ("name", "variants", payload.variants, 1.2),
        ("life", "birth_date", payload.birth_date, 1.8),
        ("life", "birth_year", str(payload.birth_year) if payload.birth_year else None, 1.4),
        ("places", "residence_places", payload.residence_places, 1.1),
        ("identifiers", "membership_number", payload.membership_number, 2.0),
        ("archive", "naid", payload.naid, 2.0),
        ("archive", "record_group", payload.record_group, 1.0),
        ("limits", "max_candidates", str(payload.max_candidates), 0.5),
    ]
    for section, field_name, value, weight in fields:
        if value is None or not str(value).strip():
            continue
        field = SearchField(
            profile_id=profile.id,
            section=section,
            field_name=field_name,
            original_value=str(value).strip(),
            normalized_value=normalize_text(str(value)),
            weight=weight,
        )
        session.add(field)
        session.flush()
        for variant_value, source, variant_weight in build_variants(field_name, str(value), weight):
            session.add(
                SearchVariant(
                    field_id=field.id,
                    value=variant_value,
                    normalized_value=normalize_text(variant_value),
                    source=source,
                    weight=variant_weight,
                )
            )


def add_queries(session: Session, job: SearchJob, payload: SearchRequest) -> None:
    query_parts = [payload.last_name]
    if payload.first_name:
        query_parts.insert(0, payload.first_name)
    if payload.birth_year:
        query_parts.append(str(payload.birth_year))
    if payload.residence_places:
        first_place = next((line.strip() for line in payload.residence_places.splitlines() if line.strip()), "")
        if first_place:
            query_parts.append(first_place)
    if payload.membership_number:
        query_parts.append(payload.membership_number)
    if payload.record_group:
        query_parts.append(payload.record_group)
    query_text = " ".join(part for part in query_parts if part).strip()
    session.add(
        SearchQuery(
            job_id=job.id,
            phase="query_expansion",
            query_text=query_text,
            endpoint="/api/v2/records/search",
            params={
                "max_candidates": payload.max_candidates,
                "birth_date": payload.birth_date,
                "birth_year": payload.birth_year,
                "residence_places": payload.residence_places,
                "membership_number": payload.membership_number,
                "naid": payload.naid,
                "record_group": payload.record_group,
            },
            result_count=0,
        )
    )


async def run_nara_candidate_search(payload: SearchRequest, api_key: str) -> NaraSearchResponse:
    client = NaraCatalogClient(api_key=api_key)
    requested_candidates = max(1, min(payload.max_candidates, NARA_SEARCH_MAX_CANDIDATES))
    items = []
    warnings: list[str] = []
    total: int | None = None
    page_count = 0
    page = 1

    while len(items) < requested_candidates:
        page_limit = min(NARA_SEARCH_PAGE_SIZE, requested_candidates - len(items))
        response = await client.search_records(build_nara_params(payload, page=page, limit=page_limit))
        page_count += 1
        if total is None:
            total = response.total
        warnings.extend(response.warnings)
        items.extend(response.items)

        if len(response.items) < page_limit:
            break
        if total is not None and len(items) >= total:
            break
        page += 1

    return NaraSearchResponse(
        items=items[:requested_candidates],
        total=total,
        raw={
            "requested_candidates": requested_candidates,
            "page_count": page_count,
            "page_size": NARA_SEARCH_PAGE_SIZE,
            "total": total,
        },
        warnings=dedupe_warnings(warnings),
    )


def build_nara_params(payload: SearchRequest, page: int = 1, limit: int | None = None) -> dict[str, Any]:
    effective_limit = max(1, min(limit or payload.max_candidates, NARA_SEARCH_PAGE_SIZE))
    params: dict[str, Any] = {
        "limit": effective_limit,
        "page": max(1, page),
        "includeExtractedText": "true",
        "availableOnline": "true",
    }
    if payload.naid and payload.naid.strip().isdigit():
        params["naId_is"] = int(payload.naid.strip())
        params["q"] = payload.last_name
    else:
        params["q"] = build_nara_query(payload)
    if payload.record_group:
        params["recordGroupNumber"] = payload.record_group.strip()
    return params


def dedupe_warnings(warnings: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for warning in warnings:
        key = warning.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(key)
    return deduped


def build_nara_query(payload: SearchRequest) -> str:
    clauses: list[str] = []
    full_name = " ".join(value for value in [payload.first_name, payload.last_name] if value).strip()
    if full_name:
        clauses.append(full_name)
    if payload.last_name:
        clauses.append(payload.last_name)
    if payload.membership_number:
        digits = re.sub(r"\D+", "", payload.membership_number)
        if digits:
            clauses.append(digits)
        clauses.append(payload.membership_number)
    if payload.birth_year:
        clauses.append(str(payload.birth_year))
    if payload.residence_places:
        clauses.extend(line.strip() for line in payload.residence_places.splitlines() if line.strip())
    if payload.variants:
        clauses.extend(line.strip() for line in payload.variants.splitlines() if line.strip())
    terms = dedupe_query_terms([sanitize_nara_query_term(clause) for clause in clauses])
    return join_nara_query_terms(terms) or sanitize_nara_query_term(payload.last_name) or payload.last_name


def sanitize_nara_query_term(value: str) -> str:
    cleaned = value.strip().replace('"', " ")
    cleaned = cleaned.replace("-", " ")
    return re.sub(r"\s+", " ", cleaned).strip()


def join_nara_query_terms(terms: list[str]) -> str:
    query = ""
    for term in terms:
        separator = " OR " if query else ""
        next_query = f"{query}{separator}{term}"
        if len(next_query) > NARA_QUERY_MAX_LENGTH:
            break
        query = next_query
    return query


def dedupe_query_terms(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = value.strip()
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
    return result


async def store_nara_candidates(job_id: str, payload: SearchRequest, nara_response) -> tuple[int, list[str]]:
    stored = 0
    warnings: list[str] = []
    seen_naids: set[str] = set()
    for item in nara_response.items:
        if is_search_job_cancelled(job_id):
            return stored, warnings
        record = item.record
        naid = str(record.naId or "").strip()
        if not naid or naid in seen_naids:
            continue
        seen_naids.add(naid)
        materialized_pages = await materialize_relevant_pages(job_id, naid, record, payload)
        for materialized_page in materialized_pages:
            if materialized_page.warning:
                warnings.append(f"NAID {naid}: {materialized_page.warning}")
        with session_scope() as session:
            job = session.get(SearchJob, job_id)
            if job is None or job.status == "cancelled":
                return stored, warnings
            stored += store_nara_candidate(session, job, payload, item, materialized_pages)
    return stored, warnings


async def store_nsdap_candidates(
    job_id: str, payload: SearchRequest, candidates: list[NsdapCandidate]
) -> tuple[int, list[str]]:
    """Persist individual card frames as results; a roll PDF is never a result."""
    stored = 0
    warnings: list[str] = []
    for candidate in candidates:
        if is_search_job_cancelled(job_id):
            return stored, warnings
        frame = candidate.frame
        frame_naid = frame.object_id or f"{candidate.roll.naid}-frame-{frame.frame_number}"
        try:
            materialized = await materialize_digital_object(
                job_id,
                frame_naid,
                frame.frame_number - 1,
                frame.raw,
                extract_ocr=False,
            )
        except Exception as exc:
            warnings.append(f"{candidate.roll.collection} {candidate.roll.box}, Frame {frame.frame_number}: {exc}")
            continue
        if materialized.warning:
            warnings.append(f"{candidate.roll.collection} {candidate.roll.box}, Frame {frame.frame_number}: {materialized.warning}")
        with session_scope() as session:
            job = session.get(SearchJob, job_id)
            if job is None or job.status == "cancelled":
                return stored, warnings
            stored += store_nsdap_candidate(session, job, payload, candidate, materialized)
    return stored, warnings


def store_nsdap_candidate(
    session: Session,
    job: SearchJob,
    payload: SearchRequest,
    candidate: NsdapCandidate,
    materialized_page: MaterializedPage,
) -> int:
    frame = candidate.frame
    roll = candidate.roll
    frame_naid = frame.object_id or f"{roll.naid}-frame-{frame.frame_number}"
    record = CandidateRecord(
        job_id=job.id,
        naid=frame_naid,
        parent_naid=roll.naid,
        title=f"{roll.collection} {roll.box} – Kartenframe {frame.frame_number}",
        description=f"{roll.title}; {frame.object_filename or f'Frame {frame.frame_number}'}",
        record_group="Record Group 242",
        series="Records Relating to Membership in the NSDAP (A3340)",
        local_identifier=f"{roll.collection}-{roll.box}-{frame.frame_number}",
        original_url=f"https://catalog.archives.gov/id/{roll.naid}",
        has_digital_objects=True,
        text_origin="NARA A3340 Extracted Text",
        retrieved_at=datetime.now(timezone.utc),
        raw_metadata={
            "source": "NARA A3340 Open Dataset",
            "collection": roll.collection,
            "roll": roll.box,
            "roll_naid": roll.naid,
            "roll_title": roll.title,
            "frame": frame.frame_number,
            "object_filename": frame.object_filename,
            "object_url": frame.object_url,
            "retrieval_strategy": candidate.frame_match.strategy,
            "matched_variants": list(candidate.frame_match.matched_variants),
            "highlight_terms": build_a3340_highlight_terms(payload, candidate.frame_match),
        },
    )
    session.add(record)
    session.flush()
    page = add_materialized_page(session, record, materialized_page)
    score = candidate.frame_match.retrieval_score
    result = SearchResult(
        job_id=job.id,
        candidate_record_id=record.id,
        match_score=score,
        category=category_for_score(score),
        suspected_person_name=build_job_title(payload),
        relevant_pages_count=1,
    )
    session.add(result)
    session.flush()
    evidence_items = [
        ("positive", "A3340-Rollenbereich", f"{roll.collection} {roll.box}: {roll.title}", 0.0, "NARA A3340 Manifest"),
        ("positive", "Konkreter Kartenframe", frame.object_filename or f"Frame {frame.frame_number}", 0.0, "NARA A3340 Roll-JSON"),
        ("uncertainty", "Retrieval Score ist kein Identitätsnachweis", candidate.frame_match.strategy, 0.0, "NARA-Trace"),
    ]
    if page and page.local_path:
        evidence_items.append(("positive", "Kartenbild lokal für Browseransicht materialisiert", page.original_url, 0.0, "NARA Originalbild"))
    for kind, label, detail, delta, source_type in evidence_items:
        session.add(
            MatchEvidence(
                job_id=job.id,
                candidate_record_id=record.id,
                candidate_page_id=page.id if page else None,
                result_id=result.id,
                kind=kind,
                label=label,
                detail=detail,
                score_delta=delta,
                source_type=source_type,
            )
        )
    return 1


def build_a3340_highlight_terms(payload: SearchRequest, match: FrameMatch) -> list[str]:
    """Expose searched identity terms to the transcript marker without asserting identity."""
    values = [
        *match.matched_variants,
        payload.first_name or "",
        payload.last_name or "",
        payload.membership_number or "",
        *(line.strip() for line in (payload.variants or "").splitlines()),
    ]
    return dedupe_query_terms(values)


def store_nara_candidate(
    session: Session,
    job: SearchJob,
    payload: SearchRequest,
    item,
    materialized_pages: list[MaterializedPage],
) -> int:
    record = item.record
    naid = str(record.naId or "").strip()
    if not naid:
        return 0

    candidate = CandidateRecord(
        job_id=job.id,
        naid=naid,
        title=record.title,
        description=record.description,
        record_group=extract_record_group(record),
        series=extract_series(record),
        local_identifier=record.localIdentifier,
        original_url=f"https://catalog.archives.gov/id/{naid}",
        rights_statement=stringify_restrictions(record),
        has_digital_objects=bool(record.digitalObjects),
        text_origin=detect_text_origin(record),
        retrieved_at=datetime.now(timezone.utc),
        raw_metadata=item.raw,
    )
    session.add(candidate)
    session.flush()
    pages = add_materialized_pages(session, candidate, materialized_pages)
    page = get_best_page_for_candidate_pages(pages)
    score, category, evidences = score_record(payload, record)
    if page is not None:
        score = min(score + 8, 100)
        category = category_for_score(score)
        evidences.append(
            (
                "positive",
                "Relevante Originalseite lokal geladen"
                if page.local_path
                else "Relevante Originalseite aus NARA-Digitalobjekt erkannt",
                page.original_url or page.image_url,
                8,
                "NARA-Digitalobjekt",
            )
        )
        page_text = current_page_text(page)
        if page_text[0]:
            evidences.append(
                (
                    "positive",
                    "Transkript für die Originalseite verfügbar",
                    page_text[1],
                    6,
                    page_text[1],
                )
            )
    result = SearchResult(
        job_id=job.id,
        candidate_record_id=candidate.id,
        match_score=score,
        category=category,
        suspected_person_name=build_job_title(payload),
        relevant_pages_count=len(pages) if pages else count_relevant_objects(record),
    )
    session.add(result)
    session.flush()
    for kind, label, detail, delta, source_type in evidences:
        session.add(
            MatchEvidence(
                job_id=job.id,
                candidate_record_id=candidate.id,
                result_id=result.id,
                kind=kind,
                label=label,
                detail=detail,
                score_delta=delta,
                source_type=source_type,
            )
        )
    return 1


def add_materialized_pages(session: Session, candidate: CandidateRecord, materialized_pages: list[MaterializedPage]) -> list[CandidatePage]:
    pages: list[CandidatePage] = []
    for materialized_page in materialized_pages:
        page = add_materialized_page(session, candidate, materialized_page)
        if page is not None:
            pages.append(page)
    return pages


def add_materialized_page(session: Session, candidate: CandidateRecord, materialized_page: MaterializedPage | None) -> CandidatePage | None:
    if materialized_page is None:
        return None

    now = datetime.now(timezone.utc)
    digital_object_data = materialized_page.object_data
    digital_object = DigitalObject(
        candidate_record_id=candidate.id,
        object_id=stringify_optional(digital_object_data.get("objectId") or digital_object_data.get("object_id")),
        object_type=stringify_optional(digital_object_data.get("objectType") or digital_object_data.get("type")),
        url=materialized_page.image_url,
        thumbnail_url=first_string(
            digital_object_data,
            "thumbnailUrl",
            "thumbnail_url",
            "thumbnail",
        ),
        file_name=first_string(digital_object_data, "objectFilename", "filename", "fileName"),
        mime_type=first_string(digital_object_data, "mimeType", "mime_type", "contentType"),
        size_bytes=parse_optional_int(digital_object_data.get("objectFileSize") or digital_object_data.get("sizeBytes")),
        retrieved_at=now if materialized_page.local_path or materialized_page.nara_text or materialized_page.ocr_text else None,
    )
    session.add(digital_object)
    session.flush()

    page = CandidatePage(
        digital_object_id=digital_object.id,
        page_number=materialized_page.page_number,
        image_url=materialized_page.image_url,
        local_path=materialized_page.local_path,
        original_url=materialized_page.image_url,
        is_relevant=materialized_page.is_relevant,
        retrieved_at=now if materialized_page.local_path else None,
    )
    session.add(page)
    session.flush()

    if materialized_page.nara_text:
        session.add(
            ExtractedText(
                page=page,
                raw_text=materialized_page.nara_text,
                normalized_text=normalize_text(materialized_page.nara_text),
                source_type="NARA Extracted Text",
                engine="NARA Catalog",
                language=None,
            )
        )
    if materialized_page.ocr_text and normalize_text(materialized_page.ocr_text) != normalize_text(materialized_page.nara_text or ""):
        session.add(
            ExtractedText(
                page=page,
                raw_text=materialized_page.ocr_text,
                normalized_text=normalize_text(materialized_page.ocr_text),
                source_type="lokal erzeugte OCR",
                engine=materialized_page.ocr_engine,
                language="deu+eng",
            )
        )
    session.flush()
    return page


def get_best_page_for_candidate_pages(pages: list[CandidatePage]) -> CandidatePage | None:
    if not pages:
        return None
    candidates = [page for page in pages if page.is_relevant] or pages
    candidates.sort(key=lambda page: (0 if page.local_path else 1, page.page_number, page.id))
    return candidates[0]


def current_page_text(page: CandidatePage) -> tuple[str | None, str | None, bool]:
    corrections = sorted(page.manual_corrections, key=lambda correction: correction.created_at, reverse=True)
    if corrections:
        return corrections[0].corrected_text, "manuelle Korrektur", True

    texts = [text for text in page.texts if text.raw_text and text.raw_text.strip()]
    texts.sort(key=text_priority)
    if not texts:
        return None, None, False
    selected = texts[0]
    return selected.raw_text, selected.source_type, selected.manually_corrected


def text_priority(text: ExtractedText) -> tuple[int, datetime]:
    source_priority = {
        "NARA-Transkription": 0,
        "NARA Extracted Text": 1,
        "lokal erzeugte OCR": 2,
    }
    return source_priority.get(text.source_type, 10), text.created_at


def stringify_optional(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def first_string(values: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = values.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def parse_optional_int(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        digits = re.sub(r"\D+", "", value)
        if digits:
            return int(digits)
    return None


def extract_record_group(record: NaraRecord) -> str | None:
    if record.recordGroupNumber is not None:
        return f"Record Group {record.recordGroupNumber}"
    for ancestor in record.ancestors:
        value = ancestor.get("recordGroupNumber") or ancestor.get("title")
        if value:
            return str(value)
    return None


def extract_series(record: NaraRecord) -> str | None:
    for ancestor in record.ancestors:
        level = str(ancestor.get("levelOfDescription") or "").lower()
        if "series" in level and ancestor.get("title"):
            return str(ancestor["title"])
    return None


def stringify_restrictions(record: NaraRecord) -> str | None:
    values = [record.useRestriction, record.accessRestriction]
    text_values = [stringify_value(value) for value in values if value]
    return " | ".join(value for value in text_values if value) or None


def stringify_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("status", "note", "description", "termName", "specificAccessRestriction"):
            if value.get(key):
                return str(value[key])
        return " ".join(str(v) for v in value.values() if v)
    return str(value)


def detect_text_origin(record: NaraRecord) -> str:
    for digital_object in record.digitalObjects:
        if digital_object.get("transcription") or digital_object.get("transcriptions"):
            return "NARA-Transkription"
        if digital_object.get("extractedText") or digital_object.get("otherExtractedText"):
            return "NARA Extracted Text"
    return "kein Text verfügbar"


def count_relevant_objects(record: NaraRecord) -> int:
    count = 0
    for digital_object in record.digitalObjects:
        if digital_object.get("extractedText") or digital_object.get("otherExtractedText") or digital_object.get("objectUrl"):
            count += 1
    return count


def score_record(payload: SearchRequest, record: NaraRecord) -> tuple[float, str, list[tuple[str, str, str | None, float, str | None]]]:
    haystack = normalize_text(" ".join(extract_record_text_parts(record)))
    evidences: list[tuple[str, str, str | None, float, str | None]] = []
    score = 0.0

    if payload.last_name and normalize_text(payload.last_name) in haystack:
        score += 24
        evidences.append(("positive", "Nachname im NARA-Datensatz gefunden", record.title, 24, "NARA-Metadaten"))
    if payload.first_name and normalize_text(payload.first_name) in haystack:
        score += 16
        evidences.append(("positive", "Vorname im NARA-Datensatz gefunden", record.title, 16, "NARA-Metadaten"))
    if payload.birth_year and str(payload.birth_year) in haystack:
        score += 12
        evidences.append(("positive", "Geburtsjahr im NARA-Datensatz gefunden", None, 12, "NARA-Metadaten"))
    if payload.membership_number:
        digits = re.sub(r"\D+", "", payload.membership_number)
        haystack_digits = re.sub(r"\D+", "", haystack)
        if digits and digits in haystack_digits:
            score += 36
            evidences.append(("positive", "Mitgliedsnummer exakt im Datensatz gefunden", None, 36, "NARA-Metadaten/Text"))
    if payload.residence_places:
        for place in [line.strip() for line in payload.residence_places.splitlines() if line.strip()]:
            if normalize_text(place) in haystack:
                score += 8
                evidences.append(("positive", f"Wohnort gefunden: {place}", None, 8, "NARA-Metadaten/Text"))
                break
    if record.digitalObjects:
        score += 5
        evidences.append(("positive", "Datensatz enthält digitale Objekte", None, 5, "NARA-Metadaten"))

    if not evidences:
        score = 10
        evidences.append(("uncertainty", "Kandidat wurde von NARA zur Suchanfrage geliefert, aber lokale Evidenz ist schwach", None, 0, "NARA-Suche"))

    score = min(score, 100)
    return score, category_for_score(score), evidences


def extract_record_text_parts(record: NaraRecord) -> list[str]:
    parts = [
        record.title,
        record.description,
        str(record.naId) if record.naId is not None else None,
        record.localIdentifier,
        str(record.recordGroupNumber) if record.recordGroupNumber is not None else None,
    ]
    for ancestor in record.ancestors:
        parts.extend(str(value) for value in ancestor.values() if isinstance(value, (str, int)))
    for digital_object in record.digitalObjects:
        for key in ("extractedText", "otherExtractedText", "transcription", "title", "objectDescription"):
            value = digital_object.get(key)
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, list):
                parts.extend(str(item) for item in value if isinstance(item, (str, int)))
    return [part for part in parts if part]


def category_for_score(score: float) -> str:
    if score >= 85:
        return "sehr wahrscheinlich"
    if score >= 65:
        return "wahrscheinlich"
    if score >= 35:
        return "möglich"
    if score >= 15:
        return "schwach"
    return "ausgeschlossen"


def build_variants(field_name: str, value: str, weight: float) -> list[tuple[str, str, float]]:
    raw_values = [line.strip() for line in value.splitlines() if line.strip()]
    if not raw_values:
        raw_values = [value.strip()]

    variants: list[tuple[str, str, float]] = []
    for raw in raw_values:
        variants.append((raw, "original", weight))
        normalized = normalize_text(raw)
        if normalized != raw:
            variants.append((normalized, "normalisiert", max(weight - 0.1, 0.1)))
        if "-" in raw:
            variants.append((raw.replace("-", " "), "Bindestrich als Leerzeichen", max(weight - 0.1, 0.1)))
            variants.append((raw.replace("-", ""), "Bindestrich entfernt", max(weight - 0.2, 0.1)))
        if field_name == "membership_number":
            digits = re.sub(r"\D+", "", raw)
            if digits:
                variants.extend(build_number_variants(digits, weight))
    return dedupe_variants(variants)


def build_number_variants(digits: str, weight: float) -> list[tuple[str, str, float]]:
    grouped = f"{digits[:-3]}.{digits[-3:]}" if len(digits) > 3 else digits
    spaced = f"{digits[:-3]} {digits[-3:]}" if len(digits) > 3 else digits
    dashed = f"{digits[:-3]}-{digits[-3:]}" if len(digits) > 3 else digits
    return [
        (digits, "Nummernvariante ohne Trennzeichen", weight),
        (grouped, "Nummernvariante mit Punkt", max(weight - 0.05, 0.1)),
        (spaced, "Nummernvariante mit Leerzeichen", max(weight - 0.1, 0.1)),
        (dashed, "Nummernvariante mit Bindestrich", max(weight - 0.1, 0.1)),
        (f"Nr. {digits}", "Nummernvariante mit Nr.", max(weight - 0.15, 0.1)),
        (f"Mitgliedsnummer {grouped}", "Nummernvariante mit Mitgliedsnummer", max(weight - 0.15, 0.1)),
    ]


def dedupe_variants(variants: list[tuple[str, str, float]]) -> list[tuple[str, str, float]]:
    seen: set[str] = set()
    deduped: list[tuple[str, str, float]] = []
    for value, source, weight in variants:
        key = value.strip().casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append((value, source, weight))
    return deduped


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().lower()
    normalized = normalized.replace("ß", "ss")
    normalized = normalized.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
    normalized = re.sub(r"[.,;:]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def add_mock_results(session: Session, job: SearchJob, title: str) -> None:
    mock_records = [
        {
            "naid": "LOCAL-PDF-SCHULTZE-NAUMBURG-1931",
            "title": "Lokale Demo-Datei: Paul Schultze-Naumburg, NSDAP-Kartei 1931",
            "score": 96.0,
            "category": "sehr wahrscheinlich",
            "text_origin": "lokale PDF ohne extrahierbare Textschicht",
            "birth_date": "1869-06-10",
            "birth_place": "Almrich",
            "residence_places": ["Naumburg", "Weimar"],
            "record_group": "Lokale Demo-Datei",
            "series": LOCAL_DEMO_PDF_SERIES,
            "original_url": str(LOCAL_DEMO_PDF_PATH),
            "relevant_pages_count": LOCAL_DEMO_PDF_PAGE_COUNT,
            "raw_metadata": build_local_demo_metadata(),
            "evidence": [
                ("positive", "Lokale PDF zu Paul Schultze-Naumburg eingebunden", str(LOCAL_DEMO_PDF_PATH), 28.0),
                (
                    "positive",
                    "PDF-Metadaten passen zum Kartei-Kontext",
                    f"Titel: {LOCAL_DEMO_PDF_SERIES}; Seiten: {LOCAL_DEMO_PDF_PAGE_COUNT}.",
                    22.0,
                ),
                (
                    "positive",
                    "Mitgliedsnummer auf der Karte",
                    "347 541.",
                    16.0,
                ),
                (
                    "positive",
                    "Geburtsort und Wohnorte aus der Karte",
                    "Geboren in Almrich; Wohnorte Naumburg und später Weimar.",
                    14.0,
                ),
                (
                    "uncertainty",
                    "Manuelle Demo-Transkription",
                    "Die lokale Datei ist eingebunden; eine automatische OCR-Pipeline ist noch offen.",
                    -4.0,
                ),
            ],
        },
        {
            "naid": "MOCK-NAID-0002",
            "title": "MOCK-DATENSATZ: Möglicher Beispieltreffer, keine NARA-Daten",
            "score": 58.0,
            "category": "möglich",
            "text_origin": "NARA-Transkription",
            "evidence": [
                ("positive", "Nachname ähnlich gefunden", "Mock-Daten, keine echte NARA-Antwort", 11.0),
                ("uncertainty", "Vorname nicht eindeutig", "Mock-Daten, keine echte NARA-Antwort", -4.0),
            ],
        },
        {
            "naid": "MOCK-NAID-0003",
            "title": "MOCK-DATENSATZ: Widersprüchliches Geburtsdatum, keine NARA-Daten",
            "score": 34.0,
            "category": "schwach",
            "text_origin": "lokal erzeugte OCR",
            "evidence": [
                ("negative", "Geburtsdatum widerspricht dem Suchprofil", "Mock-Daten, keine echte NARA-Antwort", -18.0),
            ],
        },
        {
            "naid": "MOCK-NAID-0004",
            "title": "MOCK-DATENSATZ: Ausgeschlossener Beispieltreffer, keine NARA-Daten",
            "score": 5.0,
            "category": "ausgeschlossen",
            "text_origin": "kein Text verfügbar",
            "evidence": [
                ("negative", "Eindeutig andere Person", "Mock-Daten, keine echte NARA-Antwort", -45.0),
            ],
        },
    ]

    for record_data in mock_records:
        record = CandidateRecord(
            job_id=job.id,
            naid=record_data["naid"],
            title=record_data["title"],
            record_group=record_data.get("record_group", "MOCK - keine echte Record Group"),
            series=record_data.get("series", "MOCK - keine echte Serie"),
            original_url=record_data.get("original_url", "https://catalog.archives.gov/"),
            has_digital_objects=record_data.get("has_digital_objects", True),
            text_origin=record_data["text_origin"],
            retrieved_at=datetime.now(timezone.utc),
            raw_metadata=record_data.get("raw_metadata", {"mock": True}),
        )
        session.add(record)
        session.flush()
        result = SearchResult(
            job_id=job.id,
            candidate_record_id=record.id,
            match_score=record_data["score"],
            category=record_data["category"],
            suspected_person_name=title,
            birth_date=record_data.get("birth_date"),
            birth_place=record_data.get("birth_place"),
            relevant_pages_count=record_data.get("relevant_pages_count", 1),
        )
        session.add(result)
        session.flush()
        for kind, label, detail, delta in record_data["evidence"]:
            session.add(
                MatchEvidence(
                    job_id=job.id,
                    candidate_record_id=record.id,
                    result_id=result.id,
                    kind=kind,
                    label=label,
                    detail=detail,
                    score_delta=delta,
                    source_type=record_data["text_origin"],
                )
            )


def build_local_demo_metadata() -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "demo": True,
        "source": "local_pdf",
        "local_pdf_path": str(LOCAL_DEMO_PDF_PATH),
        "pdf_title": LOCAL_DEMO_PDF_SERIES,
        "page_count": LOCAL_DEMO_PDF_PAGE_COUNT,
        "birth_place": "Almrich",
        "residence_places": ["Naumburg", "Weimar"],
    }
    if LOCAL_DEMO_PDF_PATH.exists():
        stat = LOCAL_DEMO_PDF_PATH.stat()
        metadata.update(
            {
                "exists": True,
                "size_bytes": stat.st_size,
                "last_modified_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            }
        )
    else:
        metadata["exists"] = False
    return metadata


def serialize_job(session: Session, job_id: str) -> SearchJobResponse:
    job = session.get(SearchJob, job_id)
    if job is None:
        raise LookupError(job_id)
    result_count = session.scalar(
        select(func.count(SearchResult.id)).where(SearchResult.job_id == job_id)
    ) or 0
    return serialize_job_model(job, result_count, build_job_preview(session, job_id))


def serialize_job_model(job: SearchJob, result_count: int, preview: dict[str, str | None] | None = None) -> SearchJobResponse:
    mock_mode = bool(job.profile.mock_mode) if job.profile else False
    return SearchJobResponse(
        id=job.id,
        status=job.status,
        mode=job.mode,
        title=job.title,
        progress_current=job.progress_current,
        progress_total=job.progress_total,
        warnings=list(job.warnings or []),
        error_message=job.error_message,
        created_at=job.created_at,
        completed_at=job.completed_at,
        result_count=result_count,
        mock_mode=mock_mode,
        preview_title=preview.get("title") if preview else None,
        preview_subtitle=preview.get("subtitle") if preview else None,
        preview_media_url=preview.get("media_url") if preview else None,
        preview_media_type=preview.get("media_type") if preview else None,
    )


def build_job_previews(session: Session, job_ids: list[str]) -> dict[str, dict[str, str | None]]:
    previews: dict[str, dict[str, str | None]] = {}
    results = session.scalars(
        select(SearchResult)
        .where(SearchResult.job_id.in_(job_ids))
        .options(
            selectinload(SearchResult.candidate_record)
            .selectinload(CandidateRecord.digital_objects)
            .selectinload(DigitalObject.pages),
        )
        .order_by(SearchResult.job_id, desc(SearchResult.match_score))
    ).all()
    for result in results:
        if result.job_id in previews:
            continue
        previews[result.job_id] = build_result_preview(result)
    return previews


def build_job_preview(session: Session, job_id: str) -> dict[str, str | None] | None:
    result = session.scalar(
        select(SearchResult)
        .where(SearchResult.job_id == job_id)
        .options(
            selectinload(SearchResult.candidate_record)
            .selectinload(CandidateRecord.digital_objects)
            .selectinload(DigitalObject.pages),
        )
        .order_by(desc(SearchResult.match_score))
        .limit(1)
    )
    return build_result_preview(result) if result else None


def build_result_preview(result: SearchResult) -> dict[str, str | None]:
    record = result.candidate_record
    media_page = first_displayable_media_page(result)
    return {
        "title": result.suspected_person_name or record.title or f"NAID {record.naid}",
        "subtitle": record.title or record.series or record.record_group or record.naid,
        "media_url": media_page.media_url if media_page else None,
        "media_type": media_page.media_type if media_page else None,
    }


def extract_result_years(result: SearchResult) -> list[int]:
    record = result.candidate_record
    metadata_sources = [
        record.title,
        record.description,
        record.record_group,
        record.series,
        record.local_identifier,
        record.original_url,
    ]
    for digital_object in record.digital_objects:
        metadata_sources.extend(
            [
                digital_object.object_id,
                digital_object.object_type,
                digital_object.url,
                digital_object.thumbnail_url,
                digital_object.file_name,
                digital_object.mime_type,
            ]
        )
        for page in digital_object.pages:
            metadata_sources.extend([page.image_url, page.original_url, page.local_path])
    metadata_sources.extend(collect_year_source_values(record.raw_metadata))
    years = years_from_sources(metadata_sources)
    if years:
        return years

    text_sources: list[str | None] = []
    for digital_object in record.digital_objects:
        for page in digital_object.pages:
            text_sources.extend((text.raw_text[:4000] if text.raw_text else None) for text in page.texts)
    return years_from_sources(text_sources)


def collect_year_source_values(value: Any, depth: int = 0) -> list[str]:
    if depth > 5:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (int, float)):
        return [str(value)]
    if isinstance(value, list):
        values: list[str] = []
        for item in value[:50]:
            values.extend(collect_year_source_values(item, depth + 1))
        return values
    if not isinstance(value, dict):
        return []

    values: list[str] = []
    for key, child in value.items():
        key_text = str(key).casefold()
        if any(token in key_text for token in ("date", "year", "title", "description", "identifier", "filename", "object")):
            values.extend(collect_year_source_values(child, depth + 1))
        elif key_text in {"record", "_source", "source", "body"}:
            values.extend(collect_year_source_values(child, depth + 1))
    return values[:120]


def years_from_sources(values: list[str | None]) -> list[int]:
    current_year = datetime.now(timezone.utc).year
    years: set[int] = set()
    for value in values:
        if not value:
            continue
        for match in RECORD_YEAR_PATTERN.finditer(str(value)):
            year = int(match.group(1))
            if 1700 <= year <= current_year:
                years.add(year)
    return sorted(years)


def serialize_result(result: SearchResult) -> SearchResultResponse:
    record = result.candidate_record
    if record.naid.startswith("LOCAL-"):
        data_source = "LOCAL"
    elif record.naid.startswith("MOCK-"):
        data_source = "MOCK"
    else:
        data_source = "NARA"
    page = get_relevant_page(result)
    transcript_text, transcript_source, transcript_edited = current_page_text(page) if page else (None, None, False)
    media_pages = build_result_media_pages(result)
    return SearchResultResponse(
        id=result.id,
        job_id=result.job_id,
        match_score=result.match_score,
        category=result.category,
        suspected_person_name=result.suspected_person_name,
        birth_date=result.birth_date,
        birth_place=result.birth_place,
        relevant_pages_count=result.relevant_pages_count,
        naid=record.naid,
        title=record.title,
        record_group=record.record_group,
        series=record.series,
        original_url=record.original_url,
        text_origin=record.text_origin,
        data_source=data_source,
        retrieved_at=record.retrieved_at,
        source_page_id=page.id if page else None,
        source_page_url=build_source_page_url(page) if page else None,
        source_page_label=build_source_page_label(record, page) if page else None,
        transcript_text=transcript_text,
        transcript_source=transcript_source,
        transcript_edited=transcript_edited,
        media_pages=media_pages,
        record_years=extract_result_years(result),
        highlight_terms=[
            value
            for value in record.raw_metadata.get("highlight_terms", [])
            if isinstance(value, str) and value.strip()
        ],
        evidences=[
            MatchEvidenceResponse(
                kind=evidence.kind,
                label=evidence.label,
                detail=evidence.detail,
                score_delta=evidence.score_delta,
                source_type=evidence.source_type,
            )
            for evidence in result.evidences
        ],
    )


def get_relevant_page(result: SearchResult) -> CandidatePage | None:
    pages = get_result_pages(result)
    if not pages:
        return None
    relevant = [page for page in pages if page.is_relevant]
    candidates = relevant or pages
    candidates.sort(key=lambda page: (0 if page.local_path else 1, page.page_number, page.id))
    return candidates[0]


def get_result_pages(result: SearchResult) -> list[CandidatePage]:
    pages: list[CandidatePage] = []
    for digital_object in result.candidate_record.digital_objects:
        pages.extend(digital_object.pages)
    pages.sort(key=lambda page: (page.page_number, page.id))
    return pages


def build_result_media_pages(result: SearchResult) -> list[ResultMediaPageResponse]:
    record = result.candidate_record
    return [build_result_media_page(record, page) for page in get_result_pages(result)]


def build_result_media_page(record: CandidateRecord, page: CandidatePage) -> ResultMediaPageResponse:
    transcript_text, transcript_source, transcript_edited = current_page_text(page)
    return ResultMediaPageResponse(
        page_id=page.id,
        page_number=page.page_number,
        label=build_source_page_label(record, page) or f"Objekt/Seite {page.page_number}",
        media_url=build_page_media_url(page),
        media_type=build_page_media_type(page),
        original_url=page.original_url or page.image_url,
        thumbnail_url=build_page_thumbnail_url(page),
        mime_type=page.digital_object.mime_type if page.digital_object else None,
        transcript_text=transcript_text,
        transcript_source=transcript_source,
        transcript_edited=transcript_edited,
    )


def first_displayable_media_page(result: SearchResult) -> ResultMediaPageResponse | None:
    media_pages = build_result_media_pages(result)
    for page in media_pages:
        if page.media_url:
            return page
    return media_pages[0] if media_pages else None


def build_source_page_url(page: CandidatePage | None) -> str | None:
    if page is None:
        return None
    if page.local_path and Path(page.local_path).exists():
        if is_browser_video_file(Path(page.local_path)):
            return f"/api/pages/{page.id}/media"
        return f"/api/pages/{page.id}/image"
    if is_browser_display_url(page.image_url):
        return page.image_url
    if is_browser_video_url(page.image_url):
        return page.image_url
    if page.digital_object and is_browser_display_url(page.digital_object.thumbnail_url):
        return page.digital_object.thumbnail_url
    return None


def build_page_media_url(page: CandidatePage) -> str | None:
    if page.local_path and Path(page.local_path).exists():
        return f"/api/pages/{page.id}/media"
    if is_browser_display_url(page.image_url) or is_browser_video_url(page.image_url):
        return page.image_url
    if page.digital_object and is_browser_display_url(page.digital_object.thumbnail_url):
        return page.digital_object.thumbnail_url
    return None


def build_page_media_type(page: CandidatePage) -> str:
    if page.local_path and Path(page.local_path).exists():
        path = Path(page.local_path)
        return "video" if is_browser_video_file(path) else "image"
    media_url = build_page_media_url(page)
    if is_browser_video_url(media_url):
        return "video"
    if is_browser_display_url(media_url):
        return "image"
    if page.original_url or page.image_url:
        return "catalog"
    return "unknown"


def build_page_thumbnail_url(page: CandidatePage) -> str | None:
    if page.digital_object and is_browser_display_url(page.digital_object.thumbnail_url):
        return page.digital_object.thumbnail_url
    return build_page_media_url(page) if build_page_media_type(page) == "image" else None


def build_source_page_label(record: CandidateRecord, page: CandidatePage | None) -> str | None:
    if page is None:
        return None
    file_name = page.digital_object.file_name if page.digital_object else None
    title = file_name or record.title or f"NAID {record.naid}"
    return f"{title}, Objekt/Seite {page.page_number}"
