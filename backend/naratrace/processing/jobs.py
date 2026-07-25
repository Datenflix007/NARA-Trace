from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import delete, desc, func, select
from sqlalchemy.orm import Session, selectinload

from naratrace.api.schemas import (
    MatchEvidenceResponse,
    SearchJobResponse,
    SearchRequest,
    SearchResultResponse,
)
from naratrace.core.config import get_settings
from naratrace.core.secrets import get_nara_api_key
from naratrace.database.models import (
    CandidateRecord,
    MatchEvidence,
    SearchField,
    SearchJob,
    SearchProfile,
    SearchQuery,
    SearchResult,
    SearchVariant,
)
from naratrace.database.session import session_scope
from naratrace.nara.client import NaraCatalogClient, NaraClientError, NaraRecord


LOCAL_DEMO_PDF_PATH = Path.home() / "Downloads" / "SchulzeNaumburg_NSDAP_Kartei1931.pdf"
LOCAL_DEMO_PDF_SERIES = "A3340-MFKL-R0013.pdf"
LOCAL_DEMO_PDF_PAGE_COUNT = 4


async def create_search_job(payload: SearchRequest) -> SearchJobResponse:
    settings = get_settings()
    mock_mode = settings.mock_mode or payload.demo_mode
    with session_scope() as session:
        title = build_job_title(payload)
        now = datetime.now(timezone.utc)
        job = SearchJob(
            status="searching_catalog",
            mode="quick",
            title=title,
            progress_current=1,
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

        if mock_mode:
            add_mock_results(session, job, title)
            job.status = "complete"
            job.progress_current = 6
            job.completed_at = now
            job.warnings = [
                "Demo-Modus: Treffer stammen aus lokalen Demo-Daten oder künstlichen Beispieldaten, nicht aus einer Live-NARA-Abfrage.",
                "Der lokale PDF-Treffer ist als LOCAL markiert; künstliche Vergleichstreffer sind als MOCK markiert.",
                "Echte NARA-Daten werden nur mit gültigem NARA API-Schlüssel abgerufen.",
            ]
            session.flush()
            return serialize_job(session, job.id)

        api_key, key_source = get_nara_api_key()
        if not api_key:
            job.status = "failed"
            job.progress_current = 1
            job.completed_at = now
            job.error_message = "NARA API-Schlüssel fehlt."
            job.warnings = [
                "Bitte in den Einstellungen einen NARA API-Schlüssel speichern oder NARA_API_KEY als Umgebungsvariable setzen.",
                "Ohne gültigen Schlüssel kann NARATrace keine echten NARA-Treffer abrufen.",
            ]
            session.flush()
            return serialize_job(session, job.id)

    try:
        nara_response = await run_nara_candidate_search(payload, api_key)
    except NaraClientError as exc:
        with session_scope() as session:
            job = session.get(SearchJob, job.id)
            if job is None:
                raise
            job.status = "failed"
            job.progress_current = 1
            job.completed_at = datetime.now(timezone.utc)
            job.error_message = str(exc)
            job.warnings = [str(exc), f"API-Schlüsselquelle: {key_source}."]
            session.flush()
            return serialize_job(session, job.id)

    with session_scope() as session:
        job = session.get(SearchJob, job.id)
        if job is None:
            raise LookupError(job.id)
        job.status = "ranking"
        job.progress_current = 5
        stored_count = store_nara_candidates(session, job, payload, nara_response)
        job.status = "complete"
        job.progress_current = 6
        job.completed_at = datetime.now(timezone.utc)
        if stored_count == 0:
            job.warnings = [
                "NARA-Abfrage erfolgreich, aber keine Kandidaten gefunden.",
                "Versuche weniger enge Angaben oder andere Namensvarianten.",
            ]
        session.flush()
        return serialize_job(session, job.id)


def list_search_jobs(limit: int = 20) -> list[SearchJobResponse]:
    with session_scope() as session:
        job_ids = session.scalars(
            select(SearchJob.id).order_by(desc(SearchJob.created_at)).limit(limit)
        ).all()
        return [serialize_job(session, job_id) for job_id in job_ids]


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


async def run_nara_candidate_search(payload: SearchRequest, api_key: str):
    client = NaraCatalogClient(api_key=api_key)
    params = build_nara_params(payload)
    return await client.search_records(params)


def build_nara_params(payload: SearchRequest) -> dict[str, Any]:
    limit = max(1, min(payload.max_candidates, 100))
    params: dict[str, Any] = {
        "limit": limit,
        "page": 1,
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


def build_nara_query(payload: SearchRequest) -> str:
    clauses: list[str] = []
    full_name = " ".join(value for value in [payload.first_name, payload.last_name] if value).strip()
    if full_name:
        clauses.append(f'"{full_name}"')
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
    return " OR ".join(dedupe_query_terms(clauses)) or payload.last_name


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


def store_nara_candidates(session: Session, job: SearchJob, payload: SearchRequest, nara_response) -> int:
    stored = 0
    seen_naids: set[str] = set()
    for item in nara_response.items:
        record = item.record
        naid = str(record.naId or "").strip()
        if not naid or naid in seen_naids:
            continue
        seen_naids.add(naid)
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
        score, category, evidences = score_record(payload, record)
        result = SearchResult(
            job_id=job.id,
            candidate_record_id=candidate.id,
            match_score=score,
            category=category,
            suspected_person_name=build_job_title(payload),
            relevant_pages_count=count_relevant_objects(record),
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
        stored += 1
    return stored


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
    )


def serialize_result(result: SearchResult) -> SearchResultResponse:
    record = result.candidate_record
    if record.naid.startswith("LOCAL-"):
        data_source = "LOCAL"
    elif record.naid.startswith("MOCK-"):
        data_source = "MOCK"
    else:
        data_source = "NARA"
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
