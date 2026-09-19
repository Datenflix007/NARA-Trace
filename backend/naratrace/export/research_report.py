from __future__ import annotations

import html
import zipfile
from io import BytesIO
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, PageBreak, Paragraph, Preformatted, SimpleDocTemplate, Spacer, Table, TableStyle

from naratrace.core.paths import ensure_local_directories
from naratrace.database.models import (
    CandidatePage,
    CandidateRecord,
    DigitalObject,
    SearchField,
    SearchJob,
    SearchProfile,
    SearchQuery,
    SearchResult,
)
from naratrace.database.session import session_scope
from naratrace.processing.documents import ensure_display_image, is_browser_video_file
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
                selectinload(SearchResult.job)
                .selectinload(SearchJob.profile)
                .selectinload(SearchProfile.fields)
                .selectinload(SearchField.variants),
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


def build_search_report_pdf(job_id: str, result_id: int | None = None) -> tuple[str, bytes] | None:
    with session_scope() as session:
        job = load_report_job(session, job_id)
        if job is None:
            return None
        results = load_report_results(session, job_id, result_id)
        if result_id is not None and not results:
            return None

        title = job.title or f"Suchjob {job.id}"
        title_slug = safe_name(title) or safe_name(job.id)
        if result_id is not None:
            result_slug = safe_name(str(results[0].candidate_record.naid or results[0].id))
            filename = f"naratrace-treffer-{result_slug}-{title_slug}.pdf"
        else:
            filename = f"naratrace-recherchebericht-{title_slug}.pdf"
        buffer = BytesIO()
        document = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=16 * mm,
            leftMargin=16 * mm,
            topMargin=16 * mm,
            bottomMargin=16 * mm,
            title=title,
            author="NARATrace",
        )
        styles = build_pdf_styles()
        elements: list = []

        elements.append(Paragraph(pdf_escape(f"NARATrace Recherchebericht: {title}"), styles["Title"]))
        elements.append(Paragraph(pdf_escape(f"Erstellt: {format_datetime(datetime.now(timezone.utc))}"), styles["Meta"]))
        elements.append(
            Paragraph(
                "Automatische Treffer in NARATrace sind Forschungshinweise und keine gesicherten Identifizierungen.",
                styles["Warning"],
            )
        )
        elements.append(Spacer(1, 8))

        if result_id is None:
            append_job_pdf(elements, job, results, styles)
            append_profile_pdf(elements, job, styles)
            append_queries_pdf(elements, job.queries, styles)

        for index, result in enumerate(results, start=1):
            if index > 1 or result_id is None:
                elements.append(PageBreak())
            append_result_pdf(elements, result, index, styles, max_images=8 if result_id is not None else 2)

        append_pdf_attribution(elements, styles)
        document.build(elements)
        return filename, buffer.getvalue()


def build_search_report_zip(job_id: str) -> tuple[str, Path] | None:
    with session_scope() as session:
        job = load_report_job(session, job_id)
        if job is None:
            return None
        results = load_report_results(session, job_id)
        title = job.title or f"Suchjob {job.id}"
        paths = ensure_local_directories()
        filename = f"naratrace-suchverlauf-{safe_name(title) or safe_name(job.id)}.zip"
        target = paths.exports_dir / filename

        result_pages = []
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for index, result in enumerate(results, start=1):
                slug = f"{index:03d}-{safe_name(result.candidate_record.naid)}"
                result_path = f"results/{slug}.html"
                media_entries = write_result_media_to_zip(archive, result, slug)
                archive.writestr(result_path, build_result_html(result, index, media_entries))
                result_pages.append((result, result_path))
            archive.writestr("index.html", build_zip_index_html(job, results, result_pages))
            archive.writestr("README.txt", build_zip_readme(job))

        return filename, target


def load_report_job(session, job_id: str) -> SearchJob | None:
    return session.get(
        SearchJob,
        job_id,
        options=[
            selectinload(SearchJob.profile).selectinload(SearchProfile.fields).selectinload(SearchField.variants),
            selectinload(SearchJob.queries),
        ],
    )


def load_report_results(session, job_id: str, result_id: int | None = None) -> list[SearchResult]:
    statement = (
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
        .order_by(SearchResult.match_score.desc())
    )
    if result_id is not None:
        statement = statement.where(SearchResult.id == result_id)
    return list(session.scalars(statement).all())


def build_pdf_styles() -> dict[str, ParagraphStyle]:
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Meta", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#5f6868"), leading=12))
    styles.add(
        ParagraphStyle(
            name="Warning",
            parent=styles["Normal"],
            fontSize=9,
            leading=12,
            borderColor=colors.HexColor("#b08a3c"),
            borderPadding=6,
            backColor=colors.HexColor("#fff6dc"),
            textColor=colors.HexColor("#5d4515"),
            spaceBefore=8,
            spaceAfter=8,
        )
    )
    styles.add(ParagraphStyle(name="Small", parent=styles["Normal"], fontSize=8, leading=10))
    styles.add(ParagraphStyle(name="Section", parent=styles["Heading2"], fontSize=15, leading=18, spaceBefore=10, spaceAfter=6))
    styles.add(ParagraphStyle(name="ResultTitle", parent=styles["Heading2"], fontSize=16, leading=19, spaceBefore=8, spaceAfter=6))
    return styles


def append_job_pdf(elements: list, job: SearchJob, results: list[SearchResult], styles: dict[str, ParagraphStyle]) -> None:
    elements.append(Paragraph("Suchjob", styles["Section"]))
    rows = [
        ("Job-ID", job.id),
        ("Status", job.status),
        ("Modus", job.mode),
        ("Mock-Modus", "ja" if job.profile and job.profile.mock_mode else "nein"),
        ("Erstellt", format_datetime(job.created_at)),
        ("Abgeschlossen", format_datetime(job.completed_at) if job.completed_at else "nicht abgeschlossen"),
        ("Treffer", str(len(results))),
    ]
    if job.error_message:
        rows.append(("Fehler", job.error_message))
    append_key_value_table(elements, rows, styles)
    if job.warnings:
        elements.append(Paragraph("Hinweise", styles["Section"]))
        for warning in job.warnings:
            elements.append(Paragraph(pdf_escape(f"- {warning}"), styles["Small"]))


def append_profile_pdf(elements: list, job: SearchJob, styles: dict[str, ParagraphStyle]) -> None:
    fields = job.profile.fields if job.profile else []
    elements.append(Paragraph("Suchprofil", styles["Section"]))
    if not fields:
        elements.append(Paragraph("Keine Suchfelder gespeichert.", styles["Normal"]))
        return
    rows = [("Abschnitt", "Feld", "Eingabe")]
    rows.extend((field.section, field.field_name, field.original_value) for field in fields)
    table = Table(
        [[Paragraph(pdf_escape(str(cell)), styles["Small"]) for cell in row] for row in rows],
        colWidths=[34 * mm, 40 * mm, 100 * mm],
        repeatRows=1,
    )
    table.setStyle(report_table_style(header=True))
    elements.append(table)


def append_queries_pdf(elements: list, queries: Iterable[SearchQuery], styles: dict[str, ParagraphStyle]) -> None:
    query_list = sorted(list(queries), key=lambda item: item.created_at)
    if not query_list:
        return
    elements.append(Paragraph("Abfragen", styles["Section"]))
    for query in query_list:
        elements.append(Paragraph(pdf_escape(query.phase), styles["Heading3"]))
        elements.append(Paragraph(pdf_escape(query.query_text), styles["Small"]))


def append_result_pdf(
    elements: list, result: SearchResult, index: int, styles: dict[str, ParagraphStyle], max_images: int
) -> None:
    item = serialize_result(result)
    title = item.suspected_person_name or item.title or item.naid
    elements.append(Paragraph(pdf_escape(f"{index}. {title}"), styles["ResultTitle"]))
    rows = [
        ("Trefferwahrscheinlichkeit", f"{round(item.match_score)} %"),
        ("Kategorie", item.category),
        ("Quellenart", item.source_category_label or "nicht klassifiziert"),
        ("Datenquelle", item.data_source),
        ("NAID", item.naid),
        ("Titel", item.title or "nicht ermittelt"),
        ("Record Group", item.record_group or "nicht ermittelt"),
        ("Serie", item.series or "nicht ermittelt"),
        ("Original-URL", item.original_url or "nicht ermittelt"),
        ("Textquelle", item.transcript_source or item.text_origin),
    ]
    append_key_value_table(elements, rows, styles)

    if item.media_pages:
        elements.append(Paragraph("Medienseiten und Trefferstellen", styles["Section"]))
        media_rows = [("Seite", "Typ", "Trefferstellen", "Quelle")]
        for page in item.media_pages:
            media_rows.append(
                (
                    page.label,
                    page.media_type,
                    ", ".join(page.match_terms) if page.match_terms else "-",
                    page.original_url or page.media_url or "-",
                )
            )
        table = Table(
            [[Paragraph(pdf_escape(str(cell)), styles["Small"]) for cell in row] for row in media_rows],
            colWidths=[45 * mm, 20 * mm, 45 * mm, 64 * mm],
            repeatRows=1,
        )
        table.setStyle(report_table_style(header=True))
        elements.append(table)
        append_result_images(elements, result, styles, max_images=max_images)

    if item.evidences:
        elements.append(Paragraph("Evidenz", styles["Section"]))
        for evidence in item.evidences:
            detail = f": {evidence.detail}" if evidence.detail else ""
            elements.append(Paragraph(pdf_escape(f"- {evidence.kind} | {evidence.label}{detail} ({evidence.score_delta:+.1f})"), styles["Small"]))

    if item.transcript_text:
        elements.append(Paragraph("Transkript", styles["Section"]))
        excerpt = item.transcript_text.strip()
        if len(excerpt) > 5000:
            excerpt = excerpt[:5000].rstrip() + "\n[...]"
        elements.append(Preformatted(excerpt, styles["Small"]))


def append_result_images(elements: list, result: SearchResult, styles: dict[str, ParagraphStyle], max_images: int) -> None:
    added = 0
    for page in result_pages(result):
        image_path = display_image_path_for_page(page)
        if image_path is None:
            continue
        elements.append(Spacer(1, 6))
        elements.append(Paragraph(pdf_escape(build_page_caption(page)), styles["Small"]))
        try:
            image = Image(str(image_path))
            image.drawWidth, image.drawHeight = scale_image(image.drawWidth, image.drawHeight, max_width=165 * mm, max_height=120 * mm)
            elements.append(image)
            added += 1
        except Exception:
            elements.append(Paragraph(pdf_escape(f"Bild konnte im PDF nicht eingebettet werden: {image_path.name}"), styles["Small"]))
        if added >= max_images:
            break


def append_key_value_table(elements: list, rows: list[tuple[str, str]], styles: dict[str, ParagraphStyle]) -> None:
    table = Table(
        [[Paragraph(pdf_escape(label), styles["Small"]), Paragraph(pdf_escape(value), styles["Small"])] for label, value in rows],
        colWidths=[44 * mm, 130 * mm],
    )
    table.setStyle(report_table_style())
    elements.append(table)


def report_table_style(header: bool = False) -> TableStyle:
    commands = [
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cad2cf")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fbfcfc")),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    if header:
        commands.extend(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dce6e2")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#202426")),
            ]
        )
    return TableStyle(commands)


def append_pdf_attribution(elements: list, styles: dict[str, ParagraphStyle]) -> None:
    elements.append(Spacer(1, 10))
    elements.append(Paragraph("Attribution und Grenzen", styles["Section"]))
    elements.append(
        Paragraph(
            "NARATrace ist ein unabhaengiges, inoffizielles Forschungswerkzeug. Archivische Metadaten, Rechtehinweise und Zitierweisen muessen fuer wissenschaftliche Nutzung am Originaldatensatz geprueft werden.",
            styles["Small"],
        )
    )


def scale_image(width: float, height: float, max_width: float, max_height: float) -> tuple[float, float]:
    if width <= 0 or height <= 0:
        return max_width, max_height
    factor = min(max_width / width, max_height / height, 1.0)
    return width * factor, height * factor


def pdf_escape(value: str) -> str:
    return html.escape(str(value)).replace("\n", "<br/>")


def write_result_media_to_zip(archive: zipfile.ZipFile, result: SearchResult, slug: str) -> dict[int, list[str]]:
    entries: dict[int, list[str]] = {}
    used_names: set[str] = set()
    for page in result_pages(result):
        page_entries: list[str] = []
        for media_path in local_media_paths_for_page(page):
            name = safe_name(media_path.name)
            arcname = f"media/{slug}/page-{page.page_number:03d}-{name}"
            counter = 2
            while arcname in used_names:
                arcname = f"media/{slug}/page-{page.page_number:03d}-{counter}-{name}"
                counter += 1
            used_names.add(arcname)
            archive.write(media_path, arcname)
            page_entries.append(f"../{arcname}")
        entries[page.id] = page_entries
    return entries


def build_zip_index_html(job: SearchJob, results: list[SearchResult], result_pages_list: list[tuple[SearchResult, str]]) -> str:
    title = job.title or f"Suchjob {job.id}"
    rows = []
    for index, (result, path) in enumerate(result_pages_list, start=1):
        item = serialize_result(result)
        rows.append(
            f"""
            <article class="result-card">
              <a href="{html_attr(path)}">
                <strong>{html_escape(str(index))}. {html_escape(item.suspected_person_name or item.title or item.naid)}</strong>
                <span>{html_escape(item.source_category_label or 'Sonstige Quellen')} · {html_escape(item.category)} · {round(item.match_score)} % · NAID {html_escape(item.naid)}</span>
                <small>{html_escape(item.title or "")}</small>
              </a>
            </article>
            """
        )
    return html_document(
        f"NARATrace Suchverlauf: {title}",
        f"""
        <h1>NARATrace Suchverlauf: {html_escape(title)}</h1>
        <p class="muted">Erstellt: {html_escape(format_datetime(datetime.now(timezone.utc)))}</p>
        <p class="warning">Automatische Treffer sind Forschungshinweise und keine gesicherten Identifizierungen.</p>
        <section class="meta">
          <p><strong>Job-ID:</strong> {html_escape(job.id)}</p>
          <p><strong>Status:</strong> {html_escape(job.status)}</p>
          <p><strong>Treffer:</strong> {len(results)}</p>
        </section>
        <section class="result-list">
          {''.join(rows) if rows else '<p>Keine Treffer gespeichert.</p>'}
        </section>
        """,
    )


def build_result_html(result: SearchResult, index: int, media_entries: dict[int, list[str]]) -> str:
    item = serialize_result(result)
    media_sections = []
    for page in item.media_pages:
        local_entries = media_entries.get(page.page_id, [])
        embedded = []
        for entry in local_entries:
            lower = entry.casefold()
            if lower.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")):
                embedded.append(f'<img src="{html_attr(entry)}" alt="{html_attr(page.label)}" />')
            elif lower.endswith((".mp4", ".webm", ".ogg", ".ogv")):
                embedded.append(f'<video src="{html_attr(entry)}" controls></video>')
            else:
                embedded.append(f'<a href="{html_attr(entry)}">{html_escape(Path(entry).name)}</a>')
        source_link = page.original_url or page.media_url or ""
        media_sections.append(
            f"""
            <article class="media-card">
              <h3>{html_escape(page.label)}</h3>
              <p><strong>Typ:</strong> {html_escape(page.media_type)}</p>
              <p><strong>Trefferstellen:</strong> {html_escape(', '.join(page.match_terms) if page.match_terms else '-')}</p>
              {''.join(f'<p class="snippet">{html_escape(snippet)}</p>' for snippet in page.match_snippets)}
              <div class="media-grid">{''.join(embedded) if embedded else '<p>Kein lokales Medium im Archivpaket vorhanden.</p>'}</div>
              {f'<p><a href="{html_attr(source_link)}">Originalquelle öffnen</a></p>' if source_link else ''}
            </article>
            """
        )
    evidence_html = "".join(
        f"<li>{html_escape(evidence.kind)} | {html_escape(evidence.label)}{html_escape(': ' + evidence.detail if evidence.detail else '')} ({evidence.score_delta:+.1f})</li>"
        for evidence in item.evidences
    )
    transcript = item.transcript_text or ""
    return html_document(
        f"{index}. {item.suspected_person_name or item.title or item.naid}",
        f"""
        <p><a href="../index.html">Zur Trefferliste</a></p>
        <h1>{html_escape(str(index))}. {html_escape(item.suspected_person_name or item.title or item.naid)}</h1>
        <section class="meta">
          <p><strong>Trefferwahrscheinlichkeit:</strong> {round(item.match_score)} %</p>
          <p><strong>Kategorie:</strong> {html_escape(item.category)}</p>
          <p><strong>Quellenart:</strong> {html_escape(item.source_category_label or 'nicht klassifiziert')}</p>
          <p><strong>Datenquelle:</strong> {html_escape(item.data_source)}</p>
          <p><strong>NAID:</strong> {html_escape(item.naid)}</p>
          <p><strong>Titel:</strong> {html_escape(item.title or 'nicht ermittelt')}</p>
          <p><strong>Record Group:</strong> {html_escape(item.record_group or 'nicht ermittelt')}</p>
          <p><strong>Serie:</strong> {html_escape(item.series or 'nicht ermittelt')}</p>
        </section>
        <h2>Medien und Trefferstellen</h2>
        {''.join(media_sections) if media_sections else '<p>Keine Medienseiten gespeichert.</p>'}
        <h2>Evidenz</h2>
        <ul>{evidence_html or '<li>keine Evidenzdetails gespeichert</li>'}</ul>
        <h2>Transkript</h2>
        <pre>{html_escape(transcript.strip() or 'kein Transkript gespeichert')}</pre>
        """,
    )


def build_zip_readme(job: SearchJob) -> str:
    return "\n".join(
        [
            f"NARATrace Suchverlauf: {job.title or job.id}",
            "",
            "Oeffne index.html im Browser. Die Trefferliste verlinkt auf einzelne HTML-Seiten pro Treffer.",
            "Lokal gecachte Originalmedien liegen unter media/.",
            "Wenn ein NARA-Medium nicht lokal geladen wurde, enthaelt die HTML-Seite den Original-Link.",
            "",
            "Automatische Treffer sind Forschungshinweise und keine gesicherten Identifizierungen.",
        ]
    )


def html_document(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html_escape(title)}</title>
  <style>
    body {{ margin: 0; padding: 32px; color: #202426; background: #eef1ef; font-family: Arial, sans-serif; }}
    a {{ color: #285f5a; font-weight: 700; }}
    h1 {{ margin-top: 0; }}
    .muted {{ color: #5f6868; }}
    .warning {{ border: 1px solid #b08a3c; border-radius: 8px; padding: 10px; background: #fff6dc; color: #5d4515; }}
    .meta, .result-card, .media-card {{ border: 1px solid #cad2cf; border-radius: 8px; padding: 14px; background: #fff; }}
    .result-list, .media-grid {{ display: grid; gap: 14px; }}
    .result-card a {{ display: grid; gap: 6px; text-decoration: none; color: inherit; }}
    .result-card span, .result-card small, .snippet {{ color: #5f6868; }}
    .media-card {{ margin: 0 0 16px; }}
    .media-grid img, .media-grid video {{ max-width: min(100%, 980px); max-height: 80vh; border: 1px solid #cad2cf; background: #101414; }}
    pre {{ white-space: pre-wrap; border: 1px solid #cad2cf; border-radius: 8px; padding: 14px; background: #fff; }}
  </style>
</head>
<body>
{body}
</body>
</html>
"""


def result_pages(result: SearchResult) -> list[CandidatePage]:
    pages: list[CandidatePage] = []
    for digital_object in result.candidate_record.digital_objects:
        pages.extend(digital_object.pages)
    pages.sort(key=lambda page: (page.page_number, page.id))
    return pages


def display_image_path_for_page(page: CandidatePage) -> Path | None:
    if not page.local_path:
        return None
    path = Path(page.local_path)
    if not path.exists() or not path.is_file() or is_browser_video_file(path):
        return None
    try:
        display_path = ensure_display_image(path)
    except Exception:
        return None
    return display_path if display_path.exists() and display_path.is_file() else None


def local_media_paths_for_page(page: CandidatePage) -> list[Path]:
    if not page.local_path:
        return []
    path = Path(page.local_path)
    if not path.exists() or not path.is_file():
        return []
    candidates = [path]
    candidates.extend(original_sibling_paths(path))
    seen: set[Path] = set()
    result: list[Path] = []
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen or not candidate.exists() or not candidate.is_file():
            continue
        seen.add(resolved)
        result.append(candidate)
    return result


def original_sibling_paths(path: Path) -> list[Path]:
    name = path.name
    if name.endswith(".display.jpg"):
        base = name[: -len(".display.jpg")]
        return [candidate for candidate in path.parent.glob(f"{base}.*") if candidate.name != name]
    if name.endswith(".page-1.png"):
        base = name[: -len(".page-1.png")]
        return [candidate for candidate in path.parent.glob(f"{base}.*") if candidate.name != name]
    return []


def build_page_caption(page: CandidatePage) -> str:
    file_name = page.digital_object.file_name if page.digital_object else None
    return f"{file_name or 'Originalmedium'}, Seite/Objekt {page.page_number}"


def html_escape(value: str) -> str:
    return html.escape(str(value), quote=False)


def html_attr(value: str) -> str:
    return html.escape(str(value), quote=True)


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
                f"- Quellenart: {item.source_category_label or 'nicht klassifiziert'}",
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
