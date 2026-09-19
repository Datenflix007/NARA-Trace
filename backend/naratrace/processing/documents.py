from __future__ import annotations

import hashlib
import mimetypes
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from PIL import Image, ImageOps, UnidentifiedImageError
import pytesseract

from naratrace import __version__
from naratrace.api.schemas import SearchRequest
from naratrace.core.paths import ensure_local_directories
from naratrace.nara.client import NaraRecord

MAX_DOWNLOAD_BYTES = 125 * 1024 * 1024
MAX_DOWNLOAD_MB = MAX_DOWNLOAD_BYTES // (1024 * 1024)
DOWNLOAD_TIMEOUT_SECONDS = 30.0
OCR_TIMEOUT_SECONDS = 20
BROWSER_DISPLAY_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
BROWSER_VIDEO_SUFFIXES = {".mp4", ".webm", ".ogg", ".ogv"}
MAX_MEDIA_PAGES_PER_RESULT = 6
MAX_OCR_PAGES_PER_RESULT = 1
MAX_DIGITAL_OBJECTS_FOR_INLINE_OCR = 120


@dataclass(frozen=True)
class MaterializedPage:
    object_data: dict[str, Any]
    page_number: int
    image_url: str | None
    local_path: str | None
    nara_text: str | None
    ocr_text: str | None
    ocr_engine: str | None
    warning: str | None = None
    is_relevant: bool = True


async def materialize_best_page(job_id: str, naid: str, record: NaraRecord, payload: SearchRequest) -> MaterializedPage | None:
    choice = choose_relevant_digital_object(record, payload)
    if choice is None:
        return None

    index, digital_object = choice
    return await materialize_digital_object(job_id, naid, index, digital_object)


async def materialize_relevant_pages(job_id: str, naid: str, record: NaraRecord, payload: SearchRequest) -> list[MaterializedPage]:
    choices = choose_relevant_digital_objects(record, payload, limit=MAX_MEDIA_PAGES_PER_RESULT)
    best_choice = choose_relevant_digital_object(record, payload)
    best_index = best_choice[0] if best_choice else (choices[0][0] if choices else None)
    pages: list[MaterializedPage] = []
    ocr_budget = MAX_OCR_PAGES_PER_RESULT
    allow_inline_ocr_for_record = len(record.digitalObjects) <= MAX_DIGITAL_OBJECTS_FOR_INLINE_OCR
    for index, digital_object in choices:
        is_relevant = index == best_index
        nara_text = extract_digital_object_text(digital_object)
        allow_ocr = allow_inline_ocr_for_record and is_relevant and not nara_text and ocr_budget > 0
        if allow_ocr:
            ocr_budget -= 1
        pages.append(
            await materialize_digital_object(
                job_id,
                naid,
                index,
                digital_object,
                is_relevant=is_relevant,
                allow_ocr=allow_ocr,
                allow_download=allow_inline_ocr_for_record,
                known_nara_text=nara_text,
            )
        )
    return pages


async def materialize_digital_object(
    job_id: str,
    naid: str,
    index: int,
    digital_object: dict[str, Any],
    is_relevant: bool = True,
    allow_ocr: bool = True,
    allow_download: bool = True,
    known_nara_text: str | None = None,
) -> MaterializedPage:
    image_url = extract_object_url(digital_object)
    nara_text = known_nara_text if known_nara_text is not None else extract_digital_object_text(digital_object)
    local_path: str | None = None
    ocr_text: str | None = None
    ocr_engine: str | None = None
    warning: str | None = None

    if image_url and is_probable_video_object(digital_object):
        warning = None
    elif image_url and allow_download and should_download_digital_object(image_url, nara_text, allow_ocr):
        try:
            downloaded = await download_digital_object(job_id, naid, index, image_url)
            local_image = ensure_display_image(downloaded)
            local_path = str(local_image)
            if allow_ocr and not nara_text:
                ocr_source = downloaded if is_image_file(downloaded) else local_image
                ocr_text = extract_local_ocr(ocr_source)
                if ocr_text:
                    ocr_engine = "Tesseract"
        except Exception as exc:
            warning = f"Digitalobjekt {image_url} konnte nicht lokal geladen oder per OCR verarbeitet werden: {exc}"

    return MaterializedPage(
        object_data=digital_object,
        page_number=index + 1,
        image_url=image_url,
        local_path=local_path,
        nara_text=nara_text,
        ocr_text=ocr_text,
        ocr_engine=ocr_engine,
        warning=warning,
        is_relevant=is_relevant,
    )


def should_download_digital_object(image_url: str, nara_text: str | None, allow_ocr: bool) -> bool:
    if allow_ocr and not nara_text:
        return True
    return not is_browser_display_url(image_url)


def choose_relevant_digital_object(record: NaraRecord, payload: SearchRequest) -> tuple[int, dict[str, Any]] | None:
    scored = score_digital_objects(record, payload)
    if not scored:
        return None
    scored.sort(reverse=True, key=lambda item: (item[0], -item[1]))
    best_score, index, digital_object = scored[0]
    if best_score <= 0 and not extract_object_url(digital_object) and not extract_digital_object_text(digital_object):
        return None
    return index, digital_object


def choose_relevant_digital_objects(
    record: NaraRecord, payload: SearchRequest, limit: int = MAX_MEDIA_PAGES_PER_RESULT
) -> list[tuple[int, dict[str, Any]]]:
    scored = score_digital_objects(record, payload)
    scored.sort(reverse=True, key=lambda item: (item[0], -item[1]))
    return [(index, data) for _, index, data in scored[:limit]]


def score_digital_objects(record: NaraRecord, payload: SearchRequest) -> list[tuple[float, int, dict[str, Any]]]:
    if not record.digitalObjects:
        return []
    terms = build_matching_terms(payload)
    scored: list[tuple[float, int, dict[str, Any]]] = []
    for index, digital_object in enumerate(record.digitalObjects):
        text = normalize_text(" ".join(extract_digital_object_text_parts(digital_object)))
        score = 0.0
        for term in terms:
            normalized = normalize_text(term)
            if normalized and normalized in text:
                score += 5.0
        if payload.membership_number:
            needle = re.sub(r"\D+", "", payload.membership_number)
            haystack = re.sub(r"\D+", "", text)
            if needle and needle in haystack:
                score += 20.0
        if extract_digital_object_text(digital_object):
            score += 2.0
        if is_probable_image_url(extract_object_url(digital_object)):
            score += 1.0
        if is_probable_video_object(digital_object):
            score += 1.0
        has_content = bool(extract_object_url(digital_object) or extract_digital_object_text(digital_object))
        if has_content:
            scored.append((score, index, digital_object))
    return scored


def build_matching_terms(payload: SearchRequest) -> list[str]:
    values: list[str] = []
    for value in (
        payload.first_name,
        payload.last_name,
        str(payload.birth_year) if payload.birth_year else None,
        payload.birth_date,
        payload.membership_number,
    ):
        if value:
            values.append(value)
    if payload.variants:
        values.extend(line.strip() for line in payload.variants.splitlines() if line.strip())
    if payload.residence_places:
        values.extend(line.strip() for line in payload.residence_places.splitlines() if line.strip())
    return dedupe(values)


def extract_digital_object_text(digital_object: dict[str, Any]) -> str | None:
    parts: list[str] = []
    for key in ("extractedText", "otherExtractedText", "transcription", "transcriptions"):
        value = digital_object.get(key)
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, list):
            parts.extend(str(item) for item in value if item)
    text = "\n".join(part.strip() for part in parts if part and part.strip()).strip()
    return text or None


def extract_digital_object_text_parts(digital_object: dict[str, Any]) -> list[str]:
    parts: list[str] = []
    for key in (
        "extractedText",
        "otherExtractedText",
        "transcription",
        "transcriptions",
        "title",
        "objectDescription",
        "objectDesignator",
        "objectFilename",
        "objectType",
    ):
        value = digital_object.get(key)
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, list):
            parts.extend(str(item) for item in value if item)
    return parts


def extract_object_url(digital_object: dict[str, Any]) -> str | None:
    for key in ("objectUrl", "fileUrl", "contentUrl", "url"):
        value = digital_object.get(key)
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            return value
    return None


async def download_digital_object(job_id: str, naid: str, index: int, url: str) -> Path:
    paths = ensure_local_directories()
    directory = paths.documents_dir / "nara" / safe_name(job_id)
    directory.mkdir(parents=True, exist_ok=True)

    headers = {"User-Agent": f"NARATrace/{__version__} local historical research client"}
    async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT_SECONDS, follow_redirects=True, headers=headers) as client:
        response = await client.get(url)
    if response.status_code >= 400:
        raise RuntimeError(f"HTTP {response.status_code}")
    content_length = response.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_DOWNLOAD_BYTES:
                raise RuntimeError(f"Datei ist groesser als {MAX_DOWNLOAD_MB} MB")
        except ValueError:
            pass
    content = response.content
    if len(content) > MAX_DOWNLOAD_BYTES:
        raise RuntimeError(f"Datei ist groesser als {MAX_DOWNLOAD_MB} MB")

    suffix = infer_suffix(url, response.headers.get("content-type"))
    target = directory / f"{safe_name(naid)}-{index + 1}-{hashlib.sha1(url.encode('utf-8')).hexdigest()[:10]}{suffix}"
    if not target.exists():
        target.write_bytes(content)
    return target


def ensure_display_image(path: Path) -> Path:
    if is_browser_display_image(path):
        return path
    if path.suffix.casefold() == ".pdf":
        return render_pdf_first_page(path)
    if is_image_file(path):
        return convert_image_for_browser(path)
    return path


def is_browser_display_image(path: Path) -> bool:
    return path.suffix.casefold() in BROWSER_DISPLAY_SUFFIXES and is_image_file(path)


def convert_image_for_browser(path: Path) -> Path:
    target = path.with_suffix(".display.jpg")
    if is_browser_display_image(target):
        return target

    with Image.open(path) as image:
        try:
            image.seek(0)
        except EOFError:
            pass
        display = ImageOps.exif_transpose(image)
        if display.mode in {"RGBA", "LA"} or "transparency" in display.info:
            rgba = display.convert("RGBA")
            background = Image.new("RGB", rgba.size, "white")
            background.paste(rgba, mask=rgba.getchannel("A"))
            display = background
        else:
            display = display.convert("RGB")
        display.save(target, format="JPEG", quality=90, optimize=True)

    return target


def render_pdf_first_page(path: Path) -> Path:
    target = path.with_suffix(".page-1.png")
    if target.exists():
        return target
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(path))
    page = pdf[0]
    bitmap = page.render(scale=2)
    image = bitmap.to_pil()
    image.save(target)
    return target


def extract_local_ocr(path: Path) -> str | None:
    if not is_image_file(path):
        return None
    try:
        with Image.open(path) as image:
            processed = ImageOps.autocontrast(ImageOps.grayscale(image))
            try:
                text = pytesseract.image_to_string(processed, lang="deu+eng", timeout=OCR_TIMEOUT_SECONDS)
            except (RuntimeError, pytesseract.TesseractError):
                text = pytesseract.image_to_string(processed, lang="eng", timeout=OCR_TIMEOUT_SECONDS)
    except (pytesseract.TesseractError, pytesseract.TesseractNotFoundError, RuntimeError, OSError, UnidentifiedImageError):
        return None
    cleaned = text.strip()
    return cleaned or None


def is_image_file(path: Path) -> bool:
    try:
        with Image.open(path) as image:
            image.verify()
        return True
    except (OSError, UnidentifiedImageError):
        return False


def is_probable_image_url(url: str | None) -> bool:
    if not url:
        return False
    path = urlparse(url).path.casefold()
    return path.endswith((".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".gif"))


def is_probable_video_object(digital_object: dict[str, Any]) -> bool:
    mime_type = first_string(digital_object, "mimeType", "mime_type", "contentType")
    if mime_type and mime_type.split(";", 1)[0].strip().casefold().startswith("video/"):
        return True
    return is_browser_video_url(extract_object_url(digital_object))


def is_browser_display_url(url: str | None) -> bool:
    if not url:
        return False
    path = urlparse(url).path.casefold()
    return any(path.endswith(suffix) for suffix in BROWSER_DISPLAY_SUFFIXES)


def is_browser_video_url(url: str | None) -> bool:
    if not url:
        return False
    path = urlparse(url).path.casefold()
    return any(path.endswith(suffix) for suffix in BROWSER_VIDEO_SUFFIXES)


def is_browser_video_file(path: Path) -> bool:
    return path.suffix.casefold() in BROWSER_VIDEO_SUFFIXES


def infer_suffix(url: str, content_type: str | None) -> str:
    suffix = Path(urlparse(url).path).suffix
    if suffix and len(suffix) <= 8:
        return suffix
    if content_type:
        guessed = mimetypes.guess_extension(content_type.split(";", 1)[0].strip())
        if guessed:
            return guessed
    return ".bin"


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip())
    return cleaned.strip("-") or "item"


def dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        key = value.strip().casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(value.strip())
    return deduped


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().lower()
    normalized = normalized.replace("ß", "ss")
    normalized = normalized.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
    normalized = re.sub(r"[.,;:]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def first_string(data: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None
