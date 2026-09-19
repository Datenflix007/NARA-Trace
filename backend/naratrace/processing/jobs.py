from __future__ import annotations

import asyncio
import re
import unicodedata
from dataclasses import dataclass
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
    materialize_relevant_pages,
)


LOCAL_DEMO_PDF_PATH = Path.home() / "Downloads" / "SchulzeNaumburg_NSDAP_Kartei1931.pdf"
LOCAL_DEMO_PDF_SERIES = "A3340-MFKL-R0013.pdf"
LOCAL_DEMO_PDF_PAGE_COUNT = 4
NARA_QUERY_MAX_LENGTH = 1024
NARA_SEARCH_MAX_QUERIES = 8
NARA_SEARCH_PAGE_SIZE = 100
NARA_SEARCH_MAX_CANDIDATES = 2000
NARA_STORE_MAX_CANDIDATES = 300
NARA_MATERIALIZE_MAX_CANDIDATES = 50
NARA_RELAXED_METADATA_HINTS = 25
RECORD_YEAR_PATTERN = re.compile(r"\b(17\d{2}|18\d{2}|19\d{2}|20\d{2})\b")
TERMINAL_JOB_STATUSES = {"complete", "failed", "cancelled"}
OTHER_SOURCE_CATEGORY_ID = "other"
OTHER_SOURCE_CATEGORY_LABEL = "Sonstige Quellen"


@dataclass(frozen=True)
class SourceCategoryDefinition:
    id: str
    label: str
    type_of_materials: tuple[str, ...]
    query_terms: tuple[str, ...]
    match_terms: tuple[str, ...]
    media_suffixes: tuple[str, ...] = ()
    requires_keyword: bool = False


SOURCE_CATEGORY_DEFINITIONS: tuple[SourceCategoryDefinition, ...] = (
    SourceCategoryDefinition(
        id="nsdap_membership_cards",
        label="NSDAP-Karteikarten",
        type_of_materials=("Textual Records",),
        query_terms=(
            "A3340-MFKL",
            "Mitgliedskarte",
            "NSDAP membership card",
            "Nazi Party membership card",
            "A3340",
            "National Socialist German Workers Party membership",
            "NSDAP Kartei",
        ),
        match_terms=(
            "A3340-MFKL",
            "NSDAP",
            "Nazi Party",
            "National Socialist German Workers Party",
            "membership card",
            "Mitgliedskarte",
            "Karteikarte",
            "A3340",
        ),
        requires_keyword=True,
    ),
    SourceCategoryDefinition(
        id="personnel_service_records",
        label="Personal- und Dienstunterlagen",
        type_of_materials=("Textual Records",),
        query_terms=("personnel file", "service record", "personnel record", "staff file", "employee record"),
        match_terms=("personnel file", "service record", "personnel record", "staff file", "employee record", "Personalakte"),
        requires_keyword=True,
    ),
    SourceCategoryDefinition(
        id="correspondence_telegrams",
        label="Korrespondenz und Telegramme",
        type_of_materials=("Textual Records",),
        query_terms=("correspondence", "letter", "telegram", "memorandum"),
        match_terms=("correspondence", "letter", "telegram", "memorandum", "Schreiben", "Brief"),
        requires_keyword=True,
    ),
    SourceCategoryDefinition(
        id="reports_publications",
        label="Berichte und Drucksachen",
        type_of_materials=("Textual Records",),
        query_terms=("report", "publication", "press release", "bulletin", "newspaper", "magazine"),
        match_terms=("report", "publication", "press release", "bulletin", "newspaper", "magazine", "Bericht"),
        requires_keyword=True,
    ),
    SourceCategoryDefinition(
        id="photographs_portraits",
        label="Fotos und Porträts",
        type_of_materials=("Photographs and other Graphic Materials",),
        query_terms=("photograph", "portrait", "photo", "negative", "print"),
        match_terms=("photograph", "portrait", "photo", "negative", "print", "image", "jpg", "jpeg", "tif", "tiff"),
        media_suffixes=(".jpg", ".jpeg", ".png", ".webp", ".gif", ".tif", ".tiff"),
    ),
    SourceCategoryDefinition(
        id="war_photographs",
        label="Kriegsaufnahmen",
        type_of_materials=("Photographs and other Graphic Materials", "Moving Images"),
        query_terms=("war photograph", "combat photograph", "military photograph", "World War II", "battle", "wartime"),
        match_terms=("war", "combat", "military", "World War II", "World War 2", "battle", "wartime", "Krieg"),
        media_suffixes=(".jpg", ".jpeg", ".png", ".webp", ".gif", ".tif", ".tiff", ".mp4", ".webm", ".mov"),
        requires_keyword=True,
    ),
    SourceCategoryDefinition(
        id="moving_images",
        label="Film- und Videoaufnahmen",
        type_of_materials=("Moving Images",),
        query_terms=("moving image", "motion picture", "newsreel", "film", "video"),
        match_terms=("moving image", "motion picture", "newsreel", "film", "video", "mp4", "webm"),
        media_suffixes=(".mp4", ".webm", ".ogg", ".ogv", ".mov"),
    ),
    SourceCategoryDefinition(
        id="maps_plans",
        label="Karten und Pläne",
        type_of_materials=("Maps and Charts",),
        query_terms=("map", "chart", "plan", "aerial map"),
        match_terms=("map", "chart", "plan", "Karte", "Lageplan"),
    ),
    SourceCategoryDefinition(
        id="sound_recordings",
        label="Tonaufnahmen",
        type_of_materials=("Sound Recordings",),
        query_terms=("sound recording", "audio", "oral history", "tape"),
        match_terms=("sound recording", "audio", "oral history", "tape", "mp3", "wav"),
        media_suffixes=(".mp3", ".wav", ".m4a", ".ogg"),
    ),
    SourceCategoryDefinition(
        id="legal_case_files",
        label="Gerichts- und Ermittlungsakten",
        type_of_materials=("Textual Records",),
        query_terms=("case file", "investigation", "court", "trial", "interrogation", "affidavit"),
        match_terms=("case file", "investigation", "court", "trial", "interrogation", "affidavit", "Ermittlung"),
        requires_keyword=True,
    ),
)
SOURCE_CATEGORY_BY_ID = {category.id: category for category in SOURCE_CATEGORY_DEFINITIONS}


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
            progress_total=6,
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
        if not api_key:
            job.status = "failed"
            job.progress_current = 1
            job.completed_at = datetime.now(timezone.utc)
            job.error_message = "NARA API-Schlüssel fehlt."
            job.warnings = [
                "Bitte in den Einstellungen einen NARA API-Schlüssel speichern oder NARA_API_KEY als Umgebungsvariable setzen.",
                "Ohne gültigen Schlüssel kann NARATrace keine echten NARA-Treffer abrufen.",
            ]
            session.flush()
            return

    if not update_job_state(job_id, "searching_catalog", 2):
        return
    try:
        nara_response = await run_nara_candidate_search(payload, api_key)
    except NaraClientError as exc:
        fail_search_job(job_id, str(exc), [str(exc), f"API-Schlüsselquelle: {key_source}."])
        return

    if is_search_job_cancelled(job_id):
        return
    if not update_job_state(job_id, "downloading_pages_ocr", 4):
        return
    stored_count, materialization_warnings = await store_nara_candidates(job_id, payload, nara_response)
    if not update_job_state(job_id, "ranking", 5):
        return
    with session_scope() as session:
        job = session.get(SearchJob, job_id)
        if job is None or job.status == "cancelled":
            return
        job.status = "complete"
        job.progress_current = 6
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
                selectinload(SearchResult.job)
                .selectinload(SearchJob.profile)
                .selectinload(SearchProfile.fields)
                .selectinload(SearchField.variants),
                selectinload(SearchResult.evidences),
            )
            .order_by(desc(SearchResult.match_score))
        ).all()
        return sort_search_result_responses([serialize_result(result) for result in results])


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
            selectinload(SearchResult.job)
            .selectinload(SearchJob.profile)
            .selectinload(SearchProfile.fields)
            .selectinload(SearchField.variants),
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
        ("sources", "source_categories", source_category_profile_value(payload), 0.8),
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
    category_labels = source_category_labels(payload)
    if category_labels:
        query_parts.append(", ".join(category_labels))
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
                "source_categories": selected_source_category_ids(payload),
            },
            result_count=0,
        )
    )


async def run_nara_candidate_search(payload: SearchRequest, api_key: str) -> NaraSearchResponse:
    client = NaraCatalogClient(api_key=api_key)
    requested_candidates = max(1, min(payload.max_candidates, NARA_SEARCH_MAX_CANDIDATES))
    items = []
    seen_naids: set[str] = set()
    warnings: list[str] = []
    total: int | None = None
    page_count = 0
    query_count = 0

    for query in build_nara_queries(payload):
        query_count += 1
        page = 1
        query_total: int | None = None
        while len(items) < requested_candidates:
            page_limit = min(NARA_SEARCH_PAGE_SIZE, requested_candidates - len(items))
            response = await client.search_records(build_nara_params(payload, page=page, limit=page_limit, query=query))
            page_count += 1
            if total is None:
                total = response.total
            if query_total is None:
                query_total = response.total
            warnings.extend(response.warnings)
            new_items = 0
            for item in response.items:
                naid = str(item.record.naId or "").strip()
                if not naid or naid in seen_naids:
                    continue
                seen_naids.add(naid)
                items.append(item)
                new_items += 1

            if len(response.items) < page_limit:
                break
            if query_total is not None and page * NARA_SEARCH_PAGE_SIZE >= query_total:
                break
            if new_items == 0 and page > 3:
                break
            page += 1

    return NaraSearchResponse(
        items=items[:requested_candidates],
        total=total,
        raw={
            "requested_candidates": requested_candidates,
            "page_count": page_count,
            "page_size": NARA_SEARCH_PAGE_SIZE,
            "query_count": query_count,
            "total": total,
        },
        warnings=dedupe_warnings(warnings),
    )


def build_nara_params(payload: SearchRequest, page: int = 1, limit: int | None = None, query: str | None = None) -> dict[str, Any]:
    effective_limit = max(1, min(limit or payload.max_candidates, NARA_SEARCH_PAGE_SIZE))
    params: dict[str, Any] = {
        "limit": effective_limit,
        "page": max(1, page),
        "includeExtractedText": "true",
        "availableOnline": "true",
    }
    if payload.naid and payload.naid.strip().isdigit():
        params["naId_is"] = int(payload.naid.strip())
        params["q"] = query or payload.last_name
    else:
        params["q"] = query or build_nara_query(payload)
    if payload.record_group:
        params["recordGroupNumber"] = payload.record_group.strip()
    material_filters = source_category_type_of_materials(payload)
    if material_filters:
        params["typeOfMaterials"] = material_filters[0] if len(material_filters) == 1 else material_filters
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


def build_nara_queries(payload: SearchRequest) -> list[str]:
    broad_query = build_nara_query(payload)
    identifier_queries: list[str] = []
    name_queries: list[str] = []
    full_name_variants = build_full_name_variants(payload)
    surname_variants = build_surname_search_variants(payload.last_name)
    digits = re.sub(r"\D+", "", payload.membership_number or "")
    category_terms = source_category_query_terms(payload)

    if digits:
        identifier_queries.extend(f"{variant} {digits}" for variant in full_name_variants[:4])
        identifier_queries.extend(f"{digits} {term}" for term in category_terms[:6])
        identifier_queries.extend([digits, payload.membership_number or ""])
    name_queries.extend(full_name_variants)
    name_queries.extend(surname_variants)

    category_queries: list[str] = []
    if category_terms:
        category_name_terms = prioritize_exact_names_for_source_categories(payload, full_name_variants)[:6]
        category_surname_terms = prioritize_exact_names_for_source_categories(payload, surname_variants)[:4]
        for name_term in [*category_name_terms, *category_surname_terms]:
            for category_term in category_terms[:6]:
                category_queries.append(f"{name_term} {category_term}")

    queries = [sanitize_nara_query_term(term) for term in [*identifier_queries, *category_queries, *name_queries] if term]
    if broad_query:
        queries.append(broad_query)
    deduped = dedupe_query_terms([query for query in queries if query])
    return deduped[:NARA_SEARCH_MAX_QUERIES] or [sanitize_nara_query_term(payload.last_name)]


def prioritize_exact_names_for_source_categories(payload: SearchRequest, variants: list[str]) -> list[str]:
    if not selected_source_category_ids(payload):
        return variants
    return sorted(variants, key=lambda variant: (is_common_ocr_name_variant(variant), variants.index(variant)))


def is_common_ocr_name_variant(value: str) -> bool:
    normalized = normalize_text(value)
    return "nauburg" in normalized and "naumburg" not in normalized


def build_nara_query(payload: SearchRequest) -> str:
    clauses: list[str] = []
    clauses.extend(build_full_name_variants(payload))
    clauses.extend(build_surname_search_variants(payload.last_name))
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


def build_full_name_variants(payload: SearchRequest) -> list[str]:
    surname_variants = build_full_surname_variants(payload.last_name)
    if not payload.first_name:
        return surname_variants
    return dedupe_query_terms(build_full_person_name_variants(payload) + surname_variants)


def build_full_person_name_variants(payload: SearchRequest) -> list[str]:
    if not payload.first_name:
        return []
    first_name = payload.first_name.strip()
    return dedupe_query_terms([f"{first_name} {surname}" for surname in build_full_surname_variants(payload.last_name)])


def build_surname_search_variants(last_name: str | None) -> list[str]:
    if not last_name:
        return []
    raw = last_name.strip()
    spaced = sanitize_nara_query_term(raw)
    tokens = [token for token in re.split(r"[\s-]+", raw) if token]
    joined = "".join(tokens)
    variants = build_full_surname_variants(last_name)
    variants.extend(tokens)
    base_values = [raw, spaced, joined, *tokens]
    variants.extend(build_schultze_schulze_variants(value) for value in base_values)
    for value in base_values:
        variants.extend(prioritize_common_ocr_name_variants(value))
    return dedupe_query_terms([variant for variant in variants if variant])


def build_full_surname_variants(last_name: str | None) -> list[str]:
    if not last_name:
        return []
    raw = last_name.strip()
    spaced = sanitize_nara_query_term(raw)
    tokens = [token for token in re.split(r"[\s-]+", raw) if token]
    joined = "".join(tokens)
    base_values = [raw, spaced, joined]
    variants: list[str] = []
    for value in base_values:
        variants.extend(prioritize_common_ocr_name_variants(value))
    variants.extend(build_schultze_schulze_variants(value) for value in base_values)
    return dedupe_query_terms([variant for variant in variants if variant])


def build_schultze_schulze_variants(value: str) -> str:
    return re.sub("schultze", "schulze", value, flags=re.IGNORECASE)


def build_common_ocr_name_variants(value: str) -> list[str]:
    variants: list[str] = []
    if re.search("naumburg", value, flags=re.IGNORECASE):
        variants.append(re.sub("naumburg", "nauburg", value, flags=re.IGNORECASE))
    if re.search("nauburg", value, flags=re.IGNORECASE):
        variants.append(re.sub("nauburg", "naumburg", value, flags=re.IGNORECASE))
    return variants


def prioritize_common_ocr_name_variants(value: str) -> list[str]:
    variants = build_common_ocr_name_variants(value)
    if re.search("naumburg", value, flags=re.IGNORECASE):
        return [*variants, value]
    return [value, *variants]


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


def selected_source_category_ids(payload: SearchRequest) -> list[str]:
    return dedupe_query_terms([category_id for category_id in payload.source_categories if category_id in SOURCE_CATEGORY_BY_ID])


def source_category_labels(payload: SearchRequest) -> list[str]:
    return [SOURCE_CATEGORY_BY_ID[category_id].label for category_id in selected_source_category_ids(payload)]


def source_category_profile_value(payload: SearchRequest) -> str | None:
    labels = source_category_labels(payload)
    return "\n".join(labels) if labels else None


def source_category_type_of_materials(payload: SearchRequest) -> list[str]:
    material_types: list[str] = []
    for category_id in selected_source_category_ids(payload):
        material_types.extend(SOURCE_CATEGORY_BY_ID[category_id].type_of_materials)
    return dedupe_query_terms(material_types)


def source_category_query_terms(payload: SearchRequest) -> list[str]:
    terms: list[str] = []
    for category_id in selected_source_category_ids(payload):
        terms.extend(SOURCE_CATEGORY_BY_ID[category_id].query_terms)
    return dedupe_query_terms(terms)


def record_matches_selected_source_categories(payload: SearchRequest, record: NaraRecord) -> bool:
    category_ids = selected_source_category_ids(payload)
    if not category_ids:
        return True
    return any(record_matches_source_category(record, SOURCE_CATEGORY_BY_ID[category_id]) for category_id in category_ids)


def classify_record_source_category(record: CandidateRecord | NaraRecord, preferred_ids: list[str] | None = None) -> tuple[str, str]:
    category_ids = preferred_ids or [category.id for category in SOURCE_CATEGORY_DEFINITIONS]
    for category_id in category_ids:
        category = SOURCE_CATEGORY_BY_ID.get(category_id)
        if category and record_matches_source_category(record, category):
            return category.id, category.label
    return OTHER_SOURCE_CATEGORY_ID, OTHER_SOURCE_CATEGORY_LABEL


def record_matches_source_category(record: CandidateRecord | NaraRecord, category: SourceCategoryDefinition) -> bool:
    haystack = normalize_text(" ".join(record_source_strings(record)))
    if not haystack:
        return False
    keyword_match = any(normalize_text(term) in haystack for term in [*category.match_terms, *category.query_terms])
    material_match = any(normalize_text(material) in haystack for material in category.type_of_materials)
    suffix_match = any(haystack_contains_media_suffix(haystack, suffix) for suffix in category.media_suffixes)
    if category.requires_keyword:
        return keyword_match
    return keyword_match or material_match or suffix_match


def haystack_contains_media_suffix(haystack: str, suffix: str) -> bool:
    normalized_suffix = normalize_text(suffix.lstrip("."))
    return bool(normalized_suffix and re.search(rf"\b{re.escape(normalized_suffix)}\b", haystack))


def record_source_strings(record: CandidateRecord | NaraRecord) -> list[str]:
    if isinstance(record, CandidateRecord):
        values: list[Any] = [
            record.title,
            record.description,
            record.record_group,
            record.series,
            record.local_identifier,
            record.original_url,
            record.text_origin,
            record.raw_metadata,
        ]
        for digital_object in record.digital_objects:
            values.extend(
                [
                    digital_object.object_type,
                    digital_object.url,
                    digital_object.thumbnail_url,
                    digital_object.file_name,
                    digital_object.mime_type,
                ]
            )
        return collect_record_strings(values)
    return collect_record_strings(record.model_dump(mode="python", exclude_none=True))


def collect_record_strings(value: Any, depth: int = 0) -> list[str]:
    if depth > 8:
        return []
    if isinstance(value, (str, int, float)):
        return [str(value)]
    if isinstance(value, dict):
        strings: list[str] = []
        for child in value.values():
            strings.extend(collect_record_strings(child, depth + 1))
        return strings
    if isinstance(value, (list, tuple, set)):
        strings: list[str] = []
        for child in value:
            strings.extend(collect_record_strings(child, depth + 1))
        return strings
    return []


async def store_nara_candidates(job_id: str, payload: SearchRequest, nara_response) -> tuple[int, list[str]]:
    stored = 0
    warnings: list[str] = []
    ranked_items, used_relaxed_ranking = rank_nara_search_items(payload, nara_response.items)
    store_limit = min(payload.max_candidates, NARA_STORE_MAX_CANDIDATES)
    materialize_limit = min(store_limit, NARA_MATERIALIZE_MAX_CANDIDATES)
    if used_relaxed_ranking and ranked_items:
        warnings.append(
            "Einige NARA-Kandidaten passen nicht zu allen lokalen Quellenartfiltern; "
            "NARATrace behält sie als schwächere Metadatenhinweise bei, wenn Name oder NARA-Ranking dafür sprechen."
        )
    if len(ranked_items) > materialize_limit:
        warnings.append(
            f"Originalseiten und OCR wurden aus Laufzeitgründen auf die {materialize_limit} stärksten Kandidaten begrenzt; "
            "weitere Treffer bleiben als Metadatenhinweise sichtbar."
        )
    if len(ranked_items) > store_limit:
        warnings.append(
            f"NARA lieferte {len(ranked_items)} plausible Kandidaten; gespeichert wurden die {store_limit} stärksten nach Vorbewertung."
        )

    for index, item in enumerate(ranked_items[:store_limit]):
        if is_search_job_cancelled(job_id):
            return stored, warnings
        record = item.record
        naid = str(record.naId or "").strip()
        if not naid:
            continue
        materialized_pages = []
        if index < materialize_limit:
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


def rank_nara_search_items(payload: SearchRequest, items: list[Any]) -> tuple[list[Any], bool]:
    strict_ranked: list[tuple[float, float, int, Any]] = []
    coherent_relaxed_ranked: list[tuple[float, float, int, Any]] = []
    relaxed_ranked: list[tuple[float, float, int, Any]] = []
    seen_naids: set[str] = set()
    for index, item in enumerate(items):
        record = item.record
        naid = str(record.naId or "").strip()
        if not naid or naid in seen_naids:
            continue
        score, _, _ = score_record(payload, record)
        nara_score = extract_nara_item_score(item)
        has_coherent_name = is_record_name_coherent(payload, record)
        matches_source_category = record_matches_selected_source_categories(payload, record)
        seen_naids.add(naid)
        if has_coherent_name and matches_source_category:
            strict_ranked.append((score, nara_score, index, item))
        elif has_coherent_name:
            coherent_relaxed_ranked.append((max(0, score - 8), nara_score, index, item))
        else:
            relaxed_score = score
            if not matches_source_category:
                relaxed_score -= 8
            relaxed_score -= 18
            relaxed_ranked.append((max(0, relaxed_score), nara_score, index, item))

    if strict_ranked:
        strict_ranked.sort(key=lambda entry: (-entry[0], -entry[1], entry[2]))
        coherent_relaxed_ranked.sort(key=lambda entry: (-entry[0], -entry[1], entry[2]))
        relaxed_ranked.sort(key=lambda entry: (-entry[1], -entry[0], entry[2]))
        nara_ranked_hints = [entry for entry in relaxed_ranked if entry[1] > 0][:NARA_RELAXED_METADATA_HINTS]
        ranked = [*strict_ranked, *coherent_relaxed_ranked, *nara_ranked_hints]
        return [item for _, _, _, item in ranked], bool(coherent_relaxed_ranked or nara_ranked_hints)

    if coherent_relaxed_ranked:
        coherent_relaxed_ranked.sort(key=lambda entry: (-entry[0], -entry[1], entry[2]))
        relaxed_ranked.sort(key=lambda entry: (-entry[1], -entry[0], entry[2]))
        nara_ranked_hints = [entry for entry in relaxed_ranked if entry[1] > 0][:NARA_RELAXED_METADATA_HINTS]
        ranked = [*coherent_relaxed_ranked, *nara_ranked_hints]
        return [item for _, _, _, item in ranked], True

    relaxed_ranked.sort(key=lambda entry: (-entry[0], -entry[1], entry[2]))
    return [item for _, _, _, item in relaxed_ranked], bool(relaxed_ranked)


def extract_nara_item_score(item: Any) -> float:
    raw = getattr(item, "raw", None)
    if isinstance(raw, dict):
        score = raw.get("_score")
        if isinstance(score, (int, float)):
            return float(score)
        source = raw.get("_source")
        if isinstance(source, dict):
            nested_score = source.get("_score")
            if isinstance(nested_score, (int, float)):
                return float(nested_score)
    return 0.0


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
        page_score, page_evidences = score_relevant_page_alignment(payload, page)
        score += page_score
        evidences.extend(page_evidences)
        score = min(score + 8, 100)
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
            score = min(score + 6, 100)
    score = max(0, min(score, 100))
    category = category_for_score(score)
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

    name_score, name_evidences = score_name_coherence(payload, record, haystack)
    score += name_score
    evidences.extend(name_evidences)
    if payload.first_name and normalize_text(payload.first_name) in haystack:
        score += 16
        evidences.append(("positive", "Vorname im NARA-Datensatz gefunden", record.title, 16, "NARA-Metadaten"))
    birth_status, birth_year = birth_year_match_details(payload, haystack)
    if birth_status == "contextual":
        score += 18
        evidences.append(("positive", "Geburtsjahr mit Geburtskontext im Datensatz gefunden", birth_year, 18, "NARA-Metadaten/Text"))
    elif birth_status == "generic":
        score += 6
        evidences.append(("positive", "Jahr aus dem Suchprofil im Datensatz gefunden", birth_year, 6, "NARA-Metadaten/Text"))
    elif birth_status == "conflict":
        score -= 24
        evidences.append(("negative", "Abweichendes Geburtsjahr mit Geburtskontext gefunden", birth_year, -24, "NARA-Metadaten/Text"))
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
    selected_categories = selected_source_category_ids(payload)
    if selected_categories:
        source_category_id, source_category_label = classify_record_source_category(record, selected_categories)
        if source_category_id != OTHER_SOURCE_CATEGORY_ID:
            score += 6
            evidences.append(("positive", f"Quellenart passt: {source_category_label}", None, 6, "NARA-Metadaten"))
    if record.digitalObjects:
        score += 5
        evidences.append(("positive", "Datensatz enthält digitale Objekte", None, 5, "NARA-Metadaten"))

    if not evidences:
        score = 10
        evidences.append(("uncertainty", "Kandidat wurde von NARA zur Suchanfrage geliefert, aber lokale Evidenz ist schwach", None, 0, "NARA-Suche"))

    score = max(0, min(score, 100))
    return score, category_for_score(score), evidences


def score_relevant_page_alignment(
    payload: SearchRequest, page: CandidatePage
) -> tuple[float, list[tuple[str, str, str | None, float, str | None]]]:
    transcript_text, transcript_source, _ = current_page_text(page)
    digital_object = page.digital_object
    page_sources = [
        transcript_text,
        page.image_url,
        page.original_url,
        digital_object.object_id if digital_object else None,
        digital_object.object_type if digital_object else None,
        digital_object.url if digital_object else None,
        digital_object.file_name if digital_object else None,
    ]
    haystack = normalize_text(" ".join(value for value in page_sources if value))
    if not haystack:
        return 0.0, []

    score = 0.0
    matched_buckets: set[str] = set()
    evidences: list[tuple[str, str, str | None, float, str | None]] = []
    source_type = transcript_source or "NARA-Digitalobjekt"

    name_matched, name_label = name_match_details(payload, haystack)
    if name_matched:
        delta = 16.0 if name_label == "voller Name" else 10.0
        score += delta
        matched_buckets.add("name")
        evidences.append(("positive", "Name auf relevanter Originalseite gefunden", name_label, delta, source_type))
        if name_label != "voller Name" and payload.first_name and normalize_text(payload.first_name) in haystack:
            score += 5.0
            evidences.append(("positive", "Vorname und Nachname stehen auf derselben Originalseite", None, 5.0, source_type))

    if exact_identifier_match(payload, haystack):
        score += 20.0
        matched_buckets.add("identifier")
        evidences.append(("positive", "Mitgliedsnummer auf relevanter Originalseite gefunden", None, 20.0, source_type))

    birth_status, birth_year = birth_year_match_details(payload, haystack)
    if birth_status == "contextual":
        score += 10.0
        matched_buckets.add("life")
        evidences.append(("positive", "Geburtsjahr auf relevanter Originalseite gefunden", birth_year, 10.0, source_type))
    elif birth_status == "generic":
        score += 4.0
        matched_buckets.add("life")
        evidences.append(("positive", "Jahr aus dem Suchprofil auf relevanter Originalseite gefunden", birth_year, 4.0, source_type))
    elif birth_status == "conflict":
        score -= 16.0
        evidences.append(("negative", "Abweichendes Geburtsjahr auf relevanter Originalseite gefunden", birth_year, -16.0, source_type))

    places = matched_place_names(payload, haystack)
    if places:
        delta = min(12.0, 6.0 + max(0, len(places) - 1) * 3.0)
        score += delta
        matched_buckets.add("place")
        evidences.append(("positive", "Ortsangabe auf relevanter Originalseite gefunden", ", ".join(places), delta, source_type))

    if len(matched_buckets) >= 3:
        score += 10.0
        evidences.append(
            (
                "positive",
                "Mehrere unabhängige Suchmerkmale stehen auf derselben Originalseite",
                ", ".join(sorted(matched_buckets)),
                10.0,
                source_type,
            )
        )
    elif len(matched_buckets) == 2:
        score += 5.0
        evidences.append(
            (
                "positive",
                "Zwei unabhängige Suchmerkmale stehen auf derselben Originalseite",
                ", ".join(sorted(matched_buckets)),
                5.0,
                source_type,
            )
        )

    if transcript_text and not matched_buckets:
        score -= 24.0
        evidences.append(
            (
                "uncertainty",
                "Transkript der relevanten Originalseite enthält keine Suchmerkmale",
                None,
                -24.0,
                source_type,
            )
        )

    return score, evidences


def is_record_name_coherent(payload: SearchRequest, record: NaraRecord) -> bool:
    if payload.naid and str(record.naId or "").strip() == payload.naid.strip():
        return True
    haystack = normalize_text(" ".join(extract_record_text_parts(record)))
    if exact_identifier_match(payload, haystack):
        return True
    return name_match_details(payload, haystack)[0]


def score_name_coherence(
    payload: SearchRequest, record: NaraRecord, haystack: str
) -> tuple[float, list[tuple[str, str, str | None, float, str | None]]]:
    matched, label = name_match_details(payload, haystack)
    if not matched:
        return 0.0, []
    if label == "voller Name":
        return 34.0, [("positive", "Name oder Namensvariante im NARA-Datensatz gefunden", record.title, 34, "NARA-Metadaten/Text")]
    return 24.0, [("positive", f"Nachname oder plausible Schreibvariante gefunden: {label}", record.title, 24, "NARA-Metadaten/Text")]


def name_match_details(payload: SearchRequest, haystack: str) -> tuple[bool, str]:
    for variant in build_full_person_name_variants(payload):
        normalized = normalize_text(variant)
        if normalized and normalized in haystack and len(normalized) >= 5:
            return True, "voller Name"
    for variant in build_full_surname_variants(payload.last_name):
        normalized = normalize_text(variant)
        if normalized and len(normalized) >= 4 and normalized in haystack:
            return True, variant
    surname_parts = significant_surname_parts(payload.last_name)
    if len(surname_parts) > 1:
        if all(normalize_text(part) in haystack for part in surname_parts):
            return True, "mehrteiliger Nachname"
        return False, ""
    for variant in build_primary_surname_variants(payload.last_name):
        normalized = normalize_text(variant)
        if normalized and len(normalized) >= 4 and normalized in haystack:
            return True, variant
    return False, ""


def significant_surname_parts(last_name: str | None) -> list[str]:
    if not last_name:
        return []
    return [part for part in re.split(r"[\s-]+", last_name.strip()) if len(normalize_text(part)) >= 4]


def build_primary_surname_variants(last_name: str | None) -> list[str]:
    if not last_name:
        return []
    raw_tokens = [token for token in re.split(r"[\s-]+", last_name.strip()) if token]
    primary_tokens = raw_tokens[:1] if len(raw_tokens) > 1 else raw_tokens
    variants = primary_tokens + [build_schultze_schulze_variants(token) for token in primary_tokens]
    return dedupe_query_terms(variants)


def exact_identifier_match(payload: SearchRequest, haystack: str) -> bool:
    if not payload.membership_number:
        return False
    needle = re.sub(r"\D+", "", payload.membership_number)
    haystack_digits = re.sub(r"\D+", "", haystack)
    return bool(needle and len(needle) >= 4 and needle in haystack_digits)


def birth_year_match_details(payload: SearchRequest, haystack: str) -> tuple[str, str | None]:
    if not payload.birth_year:
        return "none", None
    requested_year = str(payload.birth_year)
    contextual_years = contextual_birth_years(haystack)
    if requested_year in contextual_years:
        return "contextual", requested_year
    if contextual_years:
        return "conflict", ", ".join(contextual_years[:3])
    if requested_year in haystack:
        return "generic", requested_year
    return "none", None


def contextual_birth_years(haystack: str) -> list[str]:
    year_pattern = r"(17\d{2}|18\d{2}|19\d{2}|20\d{2})"
    context_pattern = r"(?:born|birth|geboren|geburts(?:datum|jahr)?|geb)"
    matches: list[str] = []
    for pattern in (
        rf"\b{context_pattern}\b\D{{0,40}}\b{year_pattern}\b",
        rf"\b{year_pattern}\b\D{{0,40}}\b{context_pattern}\b",
    ):
        for match in re.finditer(pattern, haystack):
            years = [group for group in match.groups() if group and re.fullmatch(year_pattern, group)]
            matches.extend(years)
    return dedupe_query_terms(matches)


def matched_place_names(payload: SearchRequest, haystack: str) -> list[str]:
    if not payload.residence_places:
        return []
    places = [line.strip() for line in re.split(r"[\n,;]+", payload.residence_places) if line.strip()]
    return [place for place in dedupe_query_terms(places) if normalize_text(place) in haystack]


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
    source_category, source_category_label = classify_record_source_category(record)
    return SearchResultResponse(
        id=result.id,
        job_id=result.job_id,
        match_score=result.match_score,
        category=result.category,
        source_category=source_category,
        source_category_label=source_category_label,
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


def sort_search_result_responses(results: list[SearchResultResponse]) -> list[SearchResultResponse]:
    return sorted(
        results,
        key=lambda result: (
            -result.match_score,
            min(result.record_years) if result.record_years else 9999,
            result.source_category_label or "",
            result.naid,
        ),
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


def build_result_match_terms(result: SearchResult) -> list[str]:
    profile = result.job.profile if result.job else None
    if not profile:
        return []
    values: list[str] = []
    for field in profile.fields:
        if field.field_name not in {
            "first_name",
            "last_name",
            "variants",
            "birth_date",
            "birth_year",
            "residence_places",
            "membership_number",
        }:
            continue
        values.extend(split_search_field_value(field.original_value))
        values.extend(variant.value for variant in field.variants)
        if field.field_name == "last_name":
            values.extend(build_full_surname_variants(field.original_value))
            values.extend(build_primary_surname_variants(field.original_value))
        if field.field_name == "membership_number":
            digits = re.sub(r"\D+", "", field.original_value)
            if digits:
                values.append(digits)
    terms = [term for term in dedupe_query_terms(values) if len(normalize_text(term)) >= 3]
    terms.sort(key=lambda term: (0 if re.search(r"\d", term) else 1, -len(term), term.casefold()))
    return terms[:24]


def split_search_field_value(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in re.split(r"[\n,;]+", value) if part.strip()]


def build_page_match_terms(
    record: CandidateRecord, page: CandidatePage, search_terms: list[str], transcript_text: str | None
) -> list[str]:
    digital_object = page.digital_object
    page_sources = [
        transcript_text,
        page.image_url,
        page.original_url,
        digital_object.file_name if digital_object else None,
        digital_object.object_id if digital_object else None,
        digital_object.object_type if digital_object else None,
        record.title,
        record.description,
    ]
    haystack = normalize_text(" ".join(value for value in page_sources if value))
    haystack_digits = re.sub(r"\D+", "", haystack)
    matches: list[str] = []
    for term in search_terms:
        normalized = normalize_text(term)
        if not normalized:
            continue
        digits = re.sub(r"\D+", "", term)
        if digits and len(digits) >= 4 and digits in haystack_digits:
            matches.append(term)
        elif len(normalized) >= 3 and normalized in haystack:
            matches.append(term)
    return dedupe_query_terms(matches)[:8]


def build_page_match_snippets(page: CandidatePage, transcript_text: str | None, match_terms: list[str]) -> list[str]:
    text = transcript_text or ""
    snippets: list[str] = []
    for term in match_terms:
        snippet = snippet_for_term(text, term)
        if snippet:
            snippets.append(snippet)
        elif page.digital_object and page.digital_object.file_name:
            snippets.append(f"{term} in {page.digital_object.file_name}")
        elif page.original_url or page.image_url:
            snippets.append(f"{term} in den Seitenmetadaten")
        if len(snippets) >= 5:
            break
    return dedupe_query_terms(snippets)


def snippet_for_term(text: str, term: str) -> str | None:
    if not text.strip():
        return None
    match = re.search(re.escape(term), text, flags=re.IGNORECASE)
    if not match:
        return None
    start = max(0, match.start() - 80)
    end = min(len(text), match.end() + 100)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    cleaned = re.sub(r"\s+", " ", text[start:end]).strip()
    return f"{prefix}{cleaned}{suffix}"


def build_result_media_pages(result: SearchResult) -> list[ResultMediaPageResponse]:
    record = result.candidate_record
    match_terms = build_result_match_terms(result)
    return [build_result_media_page(record, page, match_terms) for page in get_result_pages(result)]


def build_result_media_page(record: CandidateRecord, page: CandidatePage, search_terms: list[str]) -> ResultMediaPageResponse:
    transcript_text, transcript_source, transcript_edited = current_page_text(page)
    match_terms = build_page_match_terms(record, page, search_terms, transcript_text)
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
        match_terms=match_terms,
        match_snippets=build_page_match_snippets(page, transcript_text, match_terms),
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
