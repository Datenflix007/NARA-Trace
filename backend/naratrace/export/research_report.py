from __future__ import annotations

from base64 import b64decode, b64encode
from datetime import datetime, timezone
from html import escape
from io import BytesIO
from pathlib import Path
import re
from typing import Iterable

from PIL import Image as PillowImage, UnidentifiedImageError
from reportlab import __file__ as reportlab_file
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image as ReportLabImage
from reportlab.platypus import Paragraph, Preformatted, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from naratrace.database.models import CandidatePage, CandidateRecord, DigitalObject, SearchJob, SearchProfile, SearchQuery, SearchResult
from naratrace.database.session import session_scope
from naratrace.processing.documents import safe_name
from naratrace.processing.jobs import serialize_result


REPORT_IMAGE_MAX_PIXELS = 1_800
REPORT_IMAGE_MAX_WIDTH = 170 * mm
REPORT_IMAGE_MAX_HEIGHT = 205 * mm


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


def build_search_report_html(job_id: str) -> tuple[str, str] | None:
    report = build_search_report_markdown(job_id)
    if report is None:
        return None
    markdown_filename, markdown = report
    return Path(markdown_filename).with_suffix(".html").name, render_report_html(markdown)


def build_search_report_pdf(job_id: str) -> tuple[str, bytes] | None:
    report = build_search_report_markdown(job_id)
    if report is None:
        return None
    markdown_filename, markdown = report
    return Path(markdown_filename).with_suffix(".pdf").name, render_report_pdf(markdown)


def render_report_html(markdown: str) -> str:
    body: list[str] = []
    lines = markdown.splitlines()
    index = 0
    in_code_block = False
    code_lines: list[str] = []
    list_open = False

    def close_list() -> None:
        nonlocal list_open
        if list_open:
            body.append("</ul>")
            list_open = False

    while index < len(lines):
        line = lines[index]
        if line.startswith("```"):
            close_list()
            if in_code_block:
                body.append(f"<pre><code>{escape(chr(10).join(code_lines))}</code></pre>")
                code_lines = []
            in_code_block = not in_code_block
            index += 1
            continue
        if in_code_block:
            code_lines.append(line)
            index += 1
            continue
        embedded_image = markdown_image(line)
        if embedded_image:
            close_list()
            alt, data_uri = embedded_image
            body.append(f"<figure><img src=\"{data_uri}\" alt=\"{escape(alt, quote=True)}\"><figcaption>{inline_html(alt)}</figcaption></figure>")
            index += 1
            continue
        if line.startswith("| ") and index + 1 < len(lines) and lines[index + 1].startswith("| ---"):
            close_list()
            headers = markdown_table_cells(line)
            index += 2
            rows: list[list[str]] = []
            while index < len(lines) and lines[index].startswith("|"):
                rows.append(markdown_table_cells(lines[index]))
                index += 1
            header_html = "".join(f"<th>{inline_html(cell)}</th>" for cell in headers)
            row_html = "".join(
                "<tr>" + "".join(f"<td>{inline_html(cell)}</td>" for cell in row) + "</tr>" for row in rows
            )
            body.append(f"<div class=\"table-wrap\"><table><thead><tr>{header_html}</tr></thead><tbody>{row_html}</tbody></table></div>")
            continue
        if not line.strip():
            close_list()
            index += 1
            continue
        if line.startswith("#### "):
            close_list()
            body.append(f"<h4>{inline_html(line[5:])}</h4>")
        elif line.startswith("### "):
            close_list()
            body.append(f"<h3>{inline_html(line[4:])}</h3>")
        elif line.startswith("## "):
            close_list()
            body.append(f"<h2>{inline_html(line[3:])}</h2>")
        elif line.startswith("# "):
            close_list()
            body.append(f"<h1>{inline_html(line[2:])}</h1>")
        elif line.startswith("> "):
            close_list()
            body.append(f"<blockquote>{inline_html(line[2:])}</blockquote>")
        elif line.startswith("- "):
            if not list_open:
                body.append("<ul>")
                list_open = True
            body.append(f"<li>{inline_html(line[2:])}</li>")
        else:
            close_list()
            body.append(f"<p>{inline_html(line)}</p>")
        index += 1
    close_list()

    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="de">',
            "<head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
            "<title>NARATrace Recherchebericht</title>",
            "<style>body{max-width:980px;margin:0 auto;padding:36px;font:16px/1.55 system-ui,sans-serif;color:#172321;background:#fff}h1{font-size:2rem;border-bottom:3px solid #285f5a;padding-bottom:.45rem}h2{margin-top:2.6rem;color:#174540}h3{margin-top:1.8rem}blockquote{margin:1.2rem 0;padding:.8rem 1rem;border-left:4px solid #b58900;background:#fff8df}code,pre{font-family:ui-monospace,Consolas,monospace}pre{padding:1rem;overflow:auto;background:#f2f5f4;border:1px solid #d5dfdc}table{border-collapse:collapse;width:100%}th,td{padding:.55rem;border:1px solid #cbd6d2;text-align:left;vertical-align:top}th{background:#e5f0ed;color:#174540}.table-wrap{overflow-x:auto}figure{margin:1rem 0;padding:12px;border:1px solid #cbd6d2;background:#f6f8f7}figure img{display:block;max-width:100%;height:auto;margin:auto}figcaption{margin-top:.6rem;font-size:.9rem;font-weight:700;color:#285f5a}a{color:#174f8d}@media print{body{padding:0}a{color:inherit;text-decoration:none}}</style>",
            "</head><body>",
            *body,
            "</body></html>",
        ]
    )


def render_report_pdf(markdown: str) -> bytes:
    regular_font, bold_font = register_report_fonts()
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("ReportTitle", parent=styles["Title"], fontName=bold_font, fontSize=19, leading=24, textColor=colors.HexColor("#174540")))
    styles.add(ParagraphStyle("ReportHeading2", parent=styles["Heading2"], fontName=bold_font, fontSize=14, leading=18, spaceBefore=16, textColor=colors.HexColor("#174540")))
    styles.add(ParagraphStyle("ReportHeading3", parent=styles["Heading3"], fontName=bold_font, fontSize=11, leading=14, spaceBefore=10, textColor=colors.HexColor("#285f5a")))
    styles.add(ParagraphStyle("ReportBody", parent=styles["BodyText"], fontName=regular_font, fontSize=9, leading=13, spaceAfter=5))
    styles.add(ParagraphStyle("ReportQuote", parent=styles["BodyText"], fontName=regular_font, fontSize=9, leading=13, leftIndent=10, borderColor=colors.HexColor("#b58900"), borderWidth=2, borderPadding=7, backColor=colors.HexColor("#fff8df"), spaceBefore=5, spaceAfter=9))
    styles.add(ParagraphStyle("ReportCell", parent=styles["BodyText"], fontName=regular_font, fontSize=7.5, leading=10))
    styles.add(ParagraphStyle("ReportCellBold", parent=styles["BodyText"], fontName=bold_font, fontSize=7.5, leading=10))
    styles.add(ParagraphStyle("ReportCaption", parent=styles["BodyText"], fontName=bold_font, fontSize=8, leading=11, spaceBefore=4, spaceAfter=8, textColor=colors.HexColor("#285f5a")))

    story: list[object] = []
    lines = markdown.splitlines()
    index = 0
    in_code_block = False
    code_lines: list[str] = []
    while index < len(lines):
        line = lines[index]
        if line.startswith("```"):
            if in_code_block:
                story.append(Preformatted("\n".join(code_lines), ParagraphStyle("ReportCode", fontName="Courier", fontSize=7.5, leading=10, leftIndent=8, rightIndent=8, backColor=colors.HexColor("#f2f5f4"), borderColor=colors.HexColor("#d5dfdc"), borderWidth=0.5, borderPadding=6, spaceAfter=9)))
                code_lines = []
            in_code_block = not in_code_block
            index += 1
            continue
        if in_code_block:
            code_lines.append(line)
            index += 1
            continue
        embedded_image = markdown_image(line)
        if embedded_image:
            alt, data_uri = embedded_image
            image = reportlab_embedded_image(data_uri)
            if image is not None:
                story.extend([image, Paragraph(inline_html(alt), styles["ReportCaption"])])
            index += 1
            continue
        if line.startswith("| ") and index + 1 < len(lines) and lines[index + 1].startswith("| ---"):
            headers = markdown_table_cells(line)
            index += 2
            rows: list[list[str]] = []
            while index < len(lines) and lines[index].startswith("|"):
                rows.append(markdown_table_cells(lines[index]))
                index += 1
            table_data = [
                [Paragraph(inline_html(cell), styles["ReportCellBold"]) for cell in headers],
                *[[Paragraph(inline_html(cell), styles["ReportCell"]) for cell in row] for row in rows],
            ]
            column_width = 170 * mm / max(len(headers), 1)
            table = Table(table_data, colWidths=[column_width] * len(headers), repeatRows=1)
            table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e5f0ed")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#174540")), ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd6d2")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
            story.extend([table, Spacer(1, 8)])
            continue
        if not line.strip():
            index += 1
            continue
        if line.startswith("# "):
            style, content = styles["ReportTitle"], line[2:]
        elif line.startswith("## "):
            style, content = styles["ReportHeading2"], line[3:]
        elif line.startswith("### "):
            style, content = styles["ReportHeading3"], line[4:]
        elif line.startswith("#### "):
            style, content = styles["ReportHeading3"], line[5:]
        elif line.startswith("> "):
            style, content = styles["ReportQuote"], line[2:]
        elif line.startswith("- "):
            style, content = styles["ReportBody"], f"- {line[2:]}"
        else:
            style, content = styles["ReportBody"], line
        story.append(Paragraph(inline_html(content), style))
        index += 1

    output = BytesIO()
    document = SimpleDocTemplate(output, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=18 * mm, title="NARATrace Recherchebericht", author="NARATrace")
    document.build(story, onFirstPage=draw_pdf_footer, onLaterPages=draw_pdf_footer)
    return output.getvalue()


def register_report_fonts() -> tuple[str, str]:
    font_directory = Path(reportlab_file).resolve().parent / "fonts"
    regular_path = font_directory / "Vera.ttf"
    bold_path = font_directory / "VeraBd.ttf"
    if regular_path.exists() and bold_path.exists():
        if "NARATraceVera" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("NARATraceVera", str(regular_path)))
            pdfmetrics.registerFont(TTFont("NARATraceVeraBold", str(bold_path)))
        return "NARATraceVera", "NARATraceVeraBold"
    return "Helvetica", "Helvetica-Bold"


def draw_pdf_footer(canvas, document) -> None:
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#cbd6d2"))
    canvas.line(document.leftMargin, 13 * mm, A4[0] - document.rightMargin, 13 * mm)
    canvas.setFillColor(colors.HexColor("#5f6868"))
    canvas.setFont("Helvetica", 7)
    canvas.drawCentredString(A4[0] / 2, 8 * mm, f"NARATrace Recherchebericht - Seite {document.page}")
    canvas.restoreState()


def markdown_table_cells(line: str) -> list[str]:
    return [cell.strip().replace("\\|", "|") for cell in line.strip().strip("|").split("|")]


def inline_html(value: str) -> str:
    escaped = escape(value.replace("<br>", "\n"))
    return escaped.replace("`", "").replace("\n", "<br/>")


def markdown_image(line: str) -> tuple[str, str] | None:
    match = re.fullmatch(r"!\[([^\]]*)\]\((data:image/jpeg;base64,[A-Za-z0-9+/=]+)\)", line)
    if not match:
        return None
    return match.group(1), match.group(2)


def reportlab_embedded_image(data_uri: str) -> ReportLabImage | None:
    try:
        _, encoded = data_uri.split(",", 1)
        content = b64decode(encoded, validate=True)
        with PillowImage.open(BytesIO(content)) as image:
            width, height = image.size
    except (OSError, ValueError, UnidentifiedImageError):
        return None
    if not width or not height:
        return None
    scale = min(REPORT_IMAGE_MAX_WIDTH / width, REPORT_IMAGE_MAX_HEIGHT / height, 1)
    return ReportLabImage(BytesIO(content), width=width * scale, height=height * scale)


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
                f"- Rangstärke: {round(item.match_score)} / 100",
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
        append_result_images(lines, result)


def append_result_images(lines: list[str], result: SearchResult) -> None:
    """Embed locally materialised card scans, so every report stays self-contained."""
    images = exportable_result_images(result)
    if not images:
        return
    lines.extend(["#### Kartenbilder", ""])
    for label, original_url, data_uri in images:
        lines.extend(
            [
                f"- {label}",
                f"![{label}]({data_uri})",
                f"  Original: {original_url or 'lokale Browseransicht'}",
                "",
            ]
        )


def exportable_result_images(result: SearchResult) -> list[tuple[str, str | None, str]]:
    images: list[tuple[str, str | None, str]] = []
    for digital_object in result.candidate_record.digital_objects:
        for page in sorted(digital_object.pages, key=lambda item: (item.page_number, item.id)):
            if not page.local_path:
                continue
            data_uri = build_embedded_image_data_uri(Path(page.local_path))
            if data_uri is None:
                continue
            label = digital_object.file_name or f"Objekt/Seite {page.page_number}"
            images.append((label, page.original_url or page.image_url, data_uri))
    return images


def build_embedded_image_data_uri(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        with PillowImage.open(path) as image:
            image = image.convert("RGB")
            image.thumbnail((REPORT_IMAGE_MAX_PIXELS, REPORT_IMAGE_MAX_PIXELS))
            output = BytesIO()
            image.save(output, format="JPEG", quality=82, optimize=True)
    except (OSError, UnidentifiedImageError):
        return None
    encoded = b64encode(output.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


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
