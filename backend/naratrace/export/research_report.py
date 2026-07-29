from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from naratrace.database.models import CandidatePage, CandidateRecord, DigitalObject, SearchJob, SearchProfile, SearchQuery, SearchResult
from naratrace.database.session import session_scope
from naratrace.processing.documents import safe_name
from naratrace.processing.jobs import serialize_result


def build_search_report_markdown(job_id: str) -> tuple[str, str] | None:
    with session_scope() as session:
        job = session.get(
            SearchJob,
            job_id,
            options=[
                selectinload(SearchJob.profile).selectinload(SearchProfile.fields),
                selectinload(SearchJob.queries),
            ],
        )
        if job is None:
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
            .order_by(SearchResult.match_score.desc())
        ).all()

        lines: list[str] = []
        title = job.title or f"Suchjob {job.id}"
        filename = f"naratrace-recherchebericht-{safe_name(title) or safe_name(job.id)}.md"

        lines.extend(
            [
                f"# NARATrace Recherchebericht: {title}",
                "",
                f"Erstellt: {format_datetime(datetime.now(timezone.utc))}",
                "",
                "> Automatische Treffer in NARATrace sind Forschungshinweise und keine gesicherten Identifizierungen.",
                "",
                "## Suchjob",
                "",
                f"- Job-ID: `{job.id}`",
                f"- Status: {job.status}",
                f"- Modus: {job.mode}",
                f"- Mock-Modus: {'ja' if job.profile and job.profile.mock_mode else 'nein'}",
                f"- Erstellt: {format_datetime(job.created_at)}",
                f"- Abgeschlossen: {format_datetime(job.completed_at) if job.completed_at else 'nicht abgeschlossen'}",
                f"- Treffer: {len(results)}",
                "",
            ]
        )

        if job.error_message:
            lines.extend(["## Fehler", "", job.error_message, ""])

        if job.warnings:
            lines.extend(["## Hinweise", ""])
            lines.extend(f"- {warning}" for warning in job.warnings)
            lines.append("")

        append_profile(lines, job)
        append_queries(lines, job.queries)
        append_results(lines, results)
        append_attribution(lines)

        return filename, "\n".join(lines).strip() + "\n"


def append_profile(lines: list[str], job: SearchJob) -> None:
    fields = job.profile.fields if job.profile else []
    lines.extend(["## Suchprofil", ""])
    if not fields:
        lines.extend(["Keine Suchfelder gespeichert.", ""])
        return
    lines.extend(["| Abschnitt | Feld | Eingabe | Normalisiert |", "| --- | --- | --- | --- |"])
    for field in fields:
        lines.append(
            f"| {table_cell(field.section)} | {table_cell(field.field_name)} | {table_cell(field.original_value)} | {table_cell(field.normalized_value or '')} |"
        )
    lines.append("")


def append_queries(lines: list[str], queries: Iterable[SearchQuery]) -> None:
    query_list = list(queries)
    lines.extend(["## Abfragen", ""])
    if not query_list:
        lines.extend(["Keine Abfragen gespeichert.", ""])
        return
    for query in sorted(query_list, key=lambda item: item.created_at):
        lines.extend(
            [
                f"### {query.phase}",
                "",
                f"- Endpunkt: `{query.endpoint}`",
                f"- Ergebniszahl laut API: {query.result_count if query.result_count is not None else 'nicht gespeichert'}",
                "",
                "```text",
                query.query_text,
                "```",
                "",
            ]
        )


def append_results(lines: list[str], results: list[SearchResult]) -> None:
    lines.extend(["## Treffer", ""])
    if not results:
        lines.extend(["Keine Treffer gespeichert.", ""])
        return

    for index, result in enumerate(results, start=1):
        item = serialize_result(result)
        lines.extend(
            [
                f"### {index}. {item.suspected_person_name or item.title or item.naid}",
                "",
                f"- Trefferwahrscheinlichkeit: {round(item.match_score)} %",
                f"- Kategorie: {item.category}",
                f"- Datenquelle: {item.data_source}",
                f"- NAID: {item.naid}",
                f"- Titel: {item.title or 'nicht ermittelt'}",
                f"- Record Group: {item.record_group or 'nicht ermittelt'}",
                f"- Serie: {item.series or 'nicht ermittelt'}",
                f"- Original-URL: {item.original_url or 'nicht ermittelt'}",
                f"- Originalseite: {item.source_page_label or 'nicht ermittelt'}",
                f"- Textquelle: {item.transcript_source or item.text_origin}",
                f"- Transkript manuell korrigiert: {'ja' if item.transcript_edited else 'nein'}",
                "",
                "#### Evidenz",
                "",
            ]
        )
        if item.evidences:
            for evidence in item.evidences:
                detail = f": {evidence.detail}" if evidence.detail else ""
                lines.append(f"- {evidence.kind} | {evidence.label}{detail} ({evidence.score_delta:+.1f})")
        else:
            lines.append("- keine Evidenzdetails gespeichert")
        lines.append("")

        if item.transcript_text:
            lines.extend(["#### Transkript", "", "```text", item.transcript_text.strip(), "```", ""])


def append_attribution(lines: list[str]) -> None:
    lines.extend(
        [
            "## Attribution und Grenzen",
            "",
            "NARATrace ist ein unabhängiges, inoffizielles Forschungswerkzeug. Es steht nicht in Verbindung mit der U.S. National Archives and Records Administration und wird nicht von NARA betrieben oder unterstützt.",
            "",
            "Archivische Metadaten, Rechtehinweise und Zitierweisen müssen für wissenschaftliche Nutzung am Originaldatensatz geprüft werden.",
            "",
        ]
    )


def format_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def table_cell(value: str) -> str:
    return value.replace("\n", "<br>").replace("|", "\\|")
