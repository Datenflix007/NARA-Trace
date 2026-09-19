from __future__ import annotations

from io import BytesIO

import httpx
import pytest
from PIL import Image

from naratrace.api.schemas import SearchRequest
from naratrace.core.config import reset_settings_cache
from naratrace.core.paths import reset_paths_cache
from naratrace.database.init import init_database
from naratrace.database.models import CandidatePage, CandidateRecord, DigitalObject, SearchJob
from naratrace.database.session import dispose_database, session_scope
from naratrace.main import create_app
from naratrace.nara.client import NaraRecord
from naratrace.processing.documents import ensure_display_image, materialize_relevant_pages
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


@pytest.mark.asyncio
async def test_materialize_relevant_pages_skips_download_when_nara_text_has_browser_image(monkeypatch):
    download_calls: list[str] = []

    async def fake_download(*args):
        download_calls.append(args[-1])
        raise AssertionError("Download should not be needed when NARA text and browser image are available.")

    monkeypatch.setattr("naratrace.processing.documents.download_digital_object", fake_download)

    pages = await materialize_relevant_pages(
        "job-fast",
        "123",
        NaraRecord(
            naId=123,
            title="Paul Schultze-Naumburg membership card",
            digitalObjects=[
                {
                    "objectUrl": "https://catalog.archives.gov/media/card.jpg",
                    "extractedText": "Paul Schultze-Naumburg Mitgliedsnummer 347541",
                }
            ],
        ),
        SearchRequest(first_name="Paul", last_name="Schultze-Naumburg", membership_number="347541"),
    )

    assert len(pages) == 1
    assert pages[0].image_url == "https://catalog.archives.gov/media/card.jpg"
    assert pages[0].local_path is None
    assert pages[0].nara_text == "Paul Schultze-Naumburg Mitgliedsnummer 347541"
    assert download_calls == []


@pytest.mark.asyncio
async def test_materialize_relevant_pages_skips_inline_ocr_for_large_rolls(monkeypatch):
    download_calls: list[str] = []

    async def fake_download(*args):
        download_calls.append(args[-1])
        raise AssertionError("Large rolls should not be downloaded for inline OCR during search.")

    monkeypatch.setattr("naratrace.processing.documents.download_digital_object", fake_download)
    digital_objects = [
        {
            "objectUrl": f"https://catalog.archives.gov/OpaAPI/media/{index}/content",
            "objectFilename": f"A3340-MFKL-R0013-{index:04d}.jpg",
            "extractedText": "Paul Schultze-Naumburg" if index == 75 else None,
        }
        for index in range(130)
    ]

    pages = await materialize_relevant_pages(
        "job-large-roll",
        "593492018",
        NaraRecord(
            naId=593492018,
            title="A3340-MFKL: Number R0013",
            digitalObjects=digital_objects,
        ),
        SearchRequest(first_name="Paul", last_name="Schultze-Naumburg", source_categories=["nsdap_membership_cards"]),
    )

    assert pages
    assert any(page.nara_text == "Paul Schultze-Naumburg" for page in pages)
    assert all(page.local_path is None for page in pages)
    assert all(page.ocr_text is None for page in pages)
    assert download_calls == []


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
