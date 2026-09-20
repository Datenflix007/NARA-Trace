from __future__ import annotations

from io import BytesIO

import httpx
import pytest
from PIL import Image

from naratrace.core.config import reset_settings_cache
from naratrace.core.paths import reset_paths_cache
from naratrace.database.init import init_database
from naratrace.database.models import CandidatePage, CandidateRecord, DigitalObject, SearchJob
from naratrace.database.session import dispose_database, session_scope
from naratrace.main import create_app
from naratrace.processing.documents import OcrHitRegion, canonical_nara_media_url, ensure_display_image, extract_ocr_hit_regions
from naratrace.processing.jobs import build_source_page_url, get_candidate_page_image_path, get_candidate_page_media_path


def create_tiff(path) -> None:
    Image.new("RGB", (48, 64), "white").save(path, format="TIFF")


def create_tiff_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (48, 64), "white").save(buffer, format="TIFF")
    return buffer.getvalue()


def test_ensure_display_image_converts_tiff_to_browser_jpeg(tmp_path):
    tiff_path = tmp_path / "original-page.tif"
    create_tiff(tiff_path)

    display_path = ensure_display_image(tiff_path)

    assert display_path == tmp_path / "original-page.display.jpg"
    assert display_path.exists()
    with Image.open(display_path) as image:
        assert image.format == "JPEG"
        assert image.size == (48, 64)


def test_canonical_nara_media_url_uses_public_catalog_endpoint_for_legacy_s3():
    legacy_url = "https://s3.amazonaws.com/NARAprodstorage/lz/dc-metro/rg-242/A3340-MFKL-R0013-02947.tif"

    assert canonical_nara_media_url(legacy_url) == (
        "https://catalog.archives.gov/medialz/dc-metro/rg-242/A3340-MFKL-R0013-02947.tif"
    )


def test_extract_ocr_hit_regions_uses_word_boxes_for_names_and_spaced_numbers(tmp_path, monkeypatch):
    image_path = tmp_path / "karte.png"
    Image.new("RGB", (200, 100), "white").save(image_path)
    monkeypatch.setattr(
        "naratrace.processing.documents.pytesseract.image_to_data",
        lambda *args, **kwargs: {
            "text": ["Paul", "Schultze-", "Naumburg", "347", "541"],
            "left": [10, 40, 85, 20, 48],
            "top": [20, 20, 20, 60, 60],
            "width": [25, 40, 50, 20, 20],
            "height": [12, 12, 12, 10, 10],
        },
    )

    regions = extract_ocr_hit_regions(image_path, ["Paul Schultze-Naumburg", "347541", "nicht vorhanden"])

    assert [(region.term, region.occurrence) for region in regions] == [
        ("Paul Schultze-Naumburg", 1),
        ("347541", 1),
    ]
    assert regions[0].x == 5.0
    assert regions[0].y == 20.0
    assert regions[0].width == 62.5
    assert regions[1].x == 10.0
    assert regions[1].width == 24.0


@pytest.mark.asyncio
async def test_page_highlights_endpoint_returns_only_ocr_located_regions(monkeypatch):
    monkeypatch.setattr(
        "naratrace.api.routes.get_candidate_page_hit_regions",
        lambda page_id, terms: [OcrHitRegion(term=terms[0], occurrence=1, x=10, y=20, width=30, height=4)],
    )
    app = create_app()

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/api/pages/42/highlights?terms=Paul&terms=347541")

    assert response.status_code == 200
    assert response.json() == [{"term": "Paul", "occurrence": 1, "x": 10.0, "y": 20.0, "width": 30.0, "height": 4.0}]


def test_candidate_page_image_path_converts_cached_tiff_for_existing_jobs(tmp_path, monkeypatch):
    monkeypatch.setenv("NARATRACE_DATA_DIR", str(tmp_path / "data"))
    reset_settings_cache()
    reset_paths_cache()
    init_database()

    try:
        tiff_path = tmp_path / "cached-page.tif"
        create_tiff(tiff_path)
        with session_scope() as session:
            job = SearchJob(status="complete", mode="quick", title="TIFF-Test")
            session.add(job)
            session.flush()
            record = CandidateRecord(job_id=job.id, naid="TIFF-1", title="TIFF-Test")
            session.add(record)
            session.flush()
            digital_object = DigitalObject(candidate_record_id=record.id, file_name=tiff_path.name)
            session.add(digital_object)
            session.flush()
            page = CandidatePage(
                digital_object_id=digital_object.id,
                page_number=1,
                local_path=str(tiff_path),
                image_url="https://catalog.archives.gov/media/example/cached-page.tif",
                is_relevant=True,
            )
            session.add(page)
            session.flush()
            page_id = page.id

        display_path = get_candidate_page_image_path(page_id)

        assert display_path == tmp_path / "cached-page.display.jpg"
        assert display_path.exists()
    finally:
        dispose_database()
        reset_paths_cache()


@pytest.mark.asyncio
async def test_local_document_upload_generates_preview_and_ocr(tmp_path, monkeypatch):
    monkeypatch.setenv("NARATRACE_DATA_DIR", str(tmp_path / "data"))
    reset_settings_cache()
    reset_paths_cache()
    monkeypatch.setattr(
        "naratrace.processing.local_documents.extract_local_ocr",
        lambda path: "Paul Schultze-Naumburg\nMitgliedsnummer 347541",
    )

    app = create_app()
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(
                "/api/local-documents",
                files={"file": ("karte.tif", create_tiff_bytes(), "image/tiff")},
            )

            assert response.status_code == 201
            payload = response.json()
            assert payload["file_name"] == "karte.tif"
            assert payload["display_image_url"].startswith("/api/local-documents/")
            assert payload["ocr_engine"] == "Tesseract"
            assert "Schultze-Naumburg" in payload["ocr_text"]

            image_response = await client.get(payload["display_image_url"])
            assert image_response.status_code == 200
            assert image_response.headers["content-type"] == "image/jpeg"

    dispose_database()
    reset_paths_cache()


def test_source_page_url_omits_uncached_browser_incompatible_tiff(tmp_path, monkeypatch):
    monkeypatch.setenv("NARATRACE_DATA_DIR", str(tmp_path / "data"))
    reset_settings_cache()
    reset_paths_cache()
    init_database()

    try:
        with session_scope() as session:
            job = SearchJob(status="complete", mode="quick", title="TIFF-Test")
            session.add(job)
            session.flush()
            record = CandidateRecord(job_id=job.id, naid="TIFF-2", title="TIFF-Test")
            session.add(record)
            session.flush()
            digital_object = DigitalObject(candidate_record_id=record.id, file_name="remote-page.tif")
            session.add(digital_object)
            session.flush()
            page = CandidatePage(
                digital_object_id=digital_object.id,
                page_number=1,
                local_path=None,
                image_url="https://catalog.archives.gov/media/example/remote-page.tif",
                is_relevant=True,
            )
            session.add(page)
            session.flush()

            assert build_source_page_url(page) is None
    finally:
        dispose_database()
        reset_paths_cache()


def test_source_page_url_keeps_uncached_browser_image(tmp_path, monkeypatch):
    monkeypatch.setenv("NARATRACE_DATA_DIR", str(tmp_path / "data"))
    reset_settings_cache()
    reset_paths_cache()
    init_database()

    try:
        with session_scope() as session:
            job = SearchJob(status="complete", mode="quick", title="JPG-Test")
            session.add(job)
            session.flush()
            record = CandidateRecord(job_id=job.id, naid="JPG-1", title="JPG-Test")
            session.add(record)
            session.flush()
            digital_object = DigitalObject(candidate_record_id=record.id, file_name="remote-page.jpg")
            session.add(digital_object)
            session.flush()
            page = CandidatePage(
                digital_object_id=digital_object.id,
                page_number=1,
                local_path=None,
                image_url="https://catalog.archives.gov/media/example/remote-page.jpg",
                is_relevant=True,
            )
            session.add(page)
            session.flush()

            assert build_source_page_url(page) == "https://catalog.archives.gov/media/example/remote-page.jpg"
    finally:
        dispose_database()
        reset_paths_cache()


def test_candidate_page_media_path_keeps_cached_mp4(tmp_path, monkeypatch):
    monkeypatch.setenv("NARATRACE_DATA_DIR", str(tmp_path / "data"))
    reset_settings_cache()
    reset_paths_cache()
    init_database()

    try:
        video_path = tmp_path / "film.mp4"
        video_path.write_bytes(b"fake mp4 bytes")
        with session_scope() as session:
            job = SearchJob(status="complete", mode="quick", title="MP4-Test")
            session.add(job)
            session.flush()
            record = CandidateRecord(job_id=job.id, naid="MP4-1", title="MP4-Test")
            session.add(record)
            session.flush()
            digital_object = DigitalObject(candidate_record_id=record.id, file_name=video_path.name, mime_type="video/mp4")
            session.add(digital_object)
            session.flush()
            page = CandidatePage(
                digital_object_id=digital_object.id,
                page_number=1,
                local_path=str(video_path),
                image_url="https://catalog.archives.gov/media/example/film.mp4",
                is_relevant=True,
            )
            session.add(page)
            session.flush()
            page_id = page.id

        assert get_candidate_page_media_path(page_id) == video_path
        assert get_candidate_page_image_path(page_id) is None
    finally:
        dispose_database()
        reset_paths_cache()
