from __future__ import annotations

import mimetypes
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from naratrace.api.schemas import LocalDocumentResponse
from naratrace.core.paths import ensure_local_directories
from naratrace.processing.documents import (
    MAX_DOWNLOAD_BYTES,
    MAX_DOWNLOAD_MB,
    ensure_display_image,
    extract_local_ocr,
    infer_suffix,
    is_browser_display_image,
    is_image_file,
    safe_name,
)

SUPPORTED_LOCAL_DOCUMENT_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".gif"}
LOCAL_DOCUMENT_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")


def analyze_local_document_upload(file_name: str | None, content_type: str | None, content: bytes) -> LocalDocumentResponse:
    if not content:
        raise ValueError("Die Datei ist leer.")
    if len(content) > MAX_DOWNLOAD_BYTES:
        raise ValueError(f"Die Datei ist groesser als {MAX_DOWNLOAD_MB} MB.")

    original_name = Path(file_name or "lokales-dokument").name
    suffix = infer_suffix(original_name, content_type).casefold()
    if suffix not in SUPPORTED_LOCAL_DOCUMENT_SUFFIXES:
        raise ValueError("Unterstuetzt werden PDF, PNG, JPEG, TIFF, WebP und GIF.")

    paths = ensure_local_directories()
    document_id = uuid4().hex
    directory = paths.documents_dir / "local" / document_id
    directory.mkdir(parents=True, exist_ok=True)

    stored_name = f"{safe_name(Path(original_name).stem)}{suffix}"
    stored_path = directory / stored_name
    stored_path.write_bytes(content)

    warnings: list[str] = []
    display_path: Path | None = None
    try:
        candidate_display_path = ensure_display_image(stored_path)
        if candidate_display_path.exists() and is_browser_display_image(candidate_display_path):
            display_path = candidate_display_path
        else:
            warnings.append("Fuer diese Datei konnte keine Browser-Vorschau erzeugt werden.")
    except Exception as exc:
        warnings.append(f"Die Vorschau konnte nicht erzeugt werden: {exc}")

    ocr_source = stored_path if is_image_file(stored_path) else display_path
    ocr_text = extract_local_ocr(ocr_source) if ocr_source else None
    ocr_engine = "Tesseract" if ocr_text else None
    if ocr_text:
        ocr_directory = paths.ocr_dir / "local"
        ocr_directory.mkdir(parents=True, exist_ok=True)
        (ocr_directory / f"{document_id}.txt").write_text(ocr_text, encoding="utf-8")
    else:
        warnings.append("OCR konnte keinen Text erkennen oder Tesseract ist nicht verfuegbar.")

    return LocalDocumentResponse(
        id=document_id,
        file_name=original_name,
        content_type=content_type or mimetypes.guess_type(original_name)[0],
        size_bytes=len(content),
        display_image_url=f"/api/local-documents/{document_id}/image" if display_path else None,
        ocr_text=ocr_text,
        ocr_engine=ocr_engine,
        warnings=warnings,
        stored_at=datetime.now(timezone.utc),
    )


def get_local_document_image_path(document_id: str) -> Path | None:
    if not LOCAL_DOCUMENT_ID_PATTERN.fullmatch(document_id):
        return None

    directory = ensure_local_directories().documents_dir / "local" / document_id
    if not directory.exists():
        return None

    candidates = [
        *sorted(directory.glob("*.page-1.png")),
        *sorted(directory.glob("*.display.jpg")),
        *sorted(path for path in directory.iterdir() if path.is_file() and is_browser_display_image(path)),
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None
