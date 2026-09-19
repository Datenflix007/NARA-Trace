from __future__ import annotations

import asyncio
import zipfile
from io import BytesIO

import httpx
import pytest
from sqlalchemy import select

from naratrace.api.schemas import SearchRequest
from naratrace.core.config import reset_settings_cache
from naratrace.core.paths import reset_paths_cache
from naratrace.database.models import SearchField, SearchVariant
from naratrace.database.session import session_scope
from naratrace.main import create_app
from naratrace.nara.client import NaraRecord, NaraSearchItem, NaraSearchResponse
from naratrace.processing.documents import MaterializedPage
from naratrace.processing.jobs import (
    build_nara_params,
    build_nara_queries,
    build_nara_query,
    run_nara_candidate_search,
    score_record,
)


def test_nara_query_rewrites_hyphenated_terms_for_boolean_search():
    query = build_nara_query(
        SearchRequest(
            first_name="Paul",
            last_name="Schultze-Naumburg",
            birth_year=1869,
            residence_places="Naumburg\nSaaleck\nWeimar",
            membership_number="347.541",
            max_candidates=100,
        )
    )

    assert "Paul Schultze Naumburg" in query
    assert "Schultze Naumburg" in query
    assert "Schultze-Naumburg" not in query
    assert '"Paul Schultze-Naumburg"' not in query
    assert "347541" in query
    assert " OR " in query
    assert len(query) <= 1024
    assert any(
        "schulzenaumburg" in query_variant.casefold()
        for query_variant in build_nara_queries(SearchRequest(last_name="Schultze-Naumburg"))
    )
    assert any(
        "schultzenauburg" in query_variant.casefold()
        for query_variant in build_nara_queries(SearchRequest(last_name="Schultze-Naumburg"))
    )


def test_nara_query_uses_source_category_filters():
    payload = SearchRequest(last_name="Schultze-Naumburg", source_categories=["nsdap_membership_cards"])

    params = build_nara_params(payload)
    queries = build_nara_queries(payload)

    assert params["typeOfMaterials"] == "Textual Records"
    assert any("NSDAP membership card" in query for query in queries)
    assert len(queries) <= 8
    assert "A3340 MFKL" in queries[0]
    assert "Naumburg" in queries[0]


def test_score_record_penalizes_conflicting_birth_year_context():
    payload = SearchRequest(first_name="John", last_name="Doe", birth_year=1888)
    matching_score, _, matching_evidence = score_record(
        payload,
        NaraRecord(naId=1001, title="John Doe personnel file", description="John Doe, born 1888 in Boston."),
    )
    conflicting_score, _, conflicting_evidence = score_record(
        payload,
        NaraRecord(naId=1002, title="John Doe personnel file", description="John Doe, born 1895 in Boston."),
    )

    assert matching_score > conflicting_score
    assert any(evidence[0] == "negative" and "Geburtsjahr" in evidence[1] for evidence in conflicting_evidence)
    assert any(evidence[0] == "positive" and "Geburtsjahr" in evidence[1] for evidence in matching_evidence)


@pytest.mark.asyncio
async def test_nara_candidate_search_paginates_above_single_request(monkeypatch):
    calls: list[dict] = []

    class FakeNaraCatalogClient:
        def __init__(self, api_key: str):
            self.api_key = api_key

        async def search_records(self, params: dict):
            calls.append(dict(params))
            page = int(params["page"])
            limit = int(params["limit"])
            offset = (page - 1) * 100
            return NaraSearchResponse(
                total=250,
                raw={"page": page},
                items=[
                    NaraSearchItem(
                        record=NaraRecord(naId=offset + index + 1, title=f"Adolf Hitler record {offset + index + 1}"),
                        raw={"page": page, "index": index},
                    )
                    for index in range(limit)
                ],
            )

    monkeypatch.setattr("naratrace.processing.jobs.NaraCatalogClient", FakeNaraCatalogClient)

    response = await run_nara_candidate_search(SearchRequest(last_name="Hitler", max_candidates=250), "test-key")

    assert [call["page"] for call in calls] == [1, 2, 3]
    assert [call["limit"] for call in calls] == [100, 100, 50]
    assert len(response.items) == 250
    assert response.raw["page_count"] == 3


def isolate_nara_key(monkeypatch, tmp_path, api_key: str | None = None) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("naratrace.core.secrets._read_keyring_value", lambda: None)
    if api_key is None:
        monkeypatch.delenv("NARA_API_KEY", raising=False)
    else:
        monkeypatch.setenv("NARA_API_KEY", api_key)
    reset_settings_cache()


async def wait_for_terminal_job(client: httpx.AsyncClient, job_id: str) -> dict:
    job = None
    for _ in range(60):
        response = await client.get(f"/api/search/{job_id}")
        assert response.status_code == 200
        job = response.json()
        if job["status"] in {"complete", "failed", "cancelled"}:
            return job
        await asyncio.sleep(0.05)
    raise AssertionError(f"Suchjob {job_id} wurde nicht fertig. Letzter Status: {job}")


@pytest.mark.asyncio
async def test_create_search_job_without_mock_does_not_invent_results(tmp_path, monkeypatch):
    isolate_nara_key(monkeypatch, tmp_path)
    monkeypatch.setenv("NARATRACE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("NARATRACE_MOCK_MODE", raising=False)
    reset_settings_cache()
    reset_paths_cache()

    app = create_app()
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            create_response = await client.post(
                "/api/search",
                json={
                    "first_name": "Paul",
                    "last_name": "Schultze-Naumburg",
                    "birth_date": "1869-06-10",
                    "birth_year": 1869,
                    "residence_places": "Naumburg\nSaaleck\nWeimar",
                    "membership_number": "347.541",
                    "max_candidates": 25,
                },
            )
            assert create_response.status_code == 201
            job = create_response.json()
            assert job["status"] == "queued"
            job = await wait_for_terminal_job(client, job["id"])
            assert job["status"] == "failed"
            assert job["result_count"] == 0
            assert job["mock_mode"] is False
            assert job["error_message"] == "NARA API-Schlüssel fehlt."
            assert "keine echten NARA-Treffer" in " ".join(job["warnings"])

            results_response = await client.get(f"/api/search/{job['id']}/results")
            assert results_response.status_code == 200
            assert results_response.json() == []

            history_response = await client.get("/api/search")
            assert history_response.status_code == 200
            assert history_response.json()[0]["id"] == job["id"]

            with session_scope() as session:
                fields = session.scalars(select(SearchField).where(SearchField.profile_id.is_not(None))).all()
                field_names = {field.field_name for field in fields}
                assert {"birth_date", "birth_year", "residence_places", "membership_number"}.issubset(field_names)
                number_variants = session.scalars(
                    select(SearchVariant).join(SearchField).where(SearchField.field_name == "membership_number")
                ).all()
                variant_values = {variant.value for variant in number_variants}
                assert {"347541", "347.541", "347 541", "Nr. 347541"}.issubset(variant_values)


@pytest.mark.asyncio
async def test_create_search_job_with_mock_returns_labeled_mock_results(tmp_path, monkeypatch):
    monkeypatch.setenv("NARATRACE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("NARATRACE_MOCK_MODE", "true")
    reset_settings_cache()
    reset_paths_cache()

    app = create_app()
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            create_response = await client.post(
                "/api/search",
                json={"first_name": "Paul", "last_name": "Schultze-Naumburg", "max_candidates": 25},
            )
            assert create_response.status_code == 201
            job = create_response.json()
            assert job["status"] == "queued"
            job = await wait_for_terminal_job(client, job["id"])
            assert job["status"] == "complete"
            assert job["result_count"] == 4
            assert job["mock_mode"] is True

            results_response = await client.get(f"/api/search/{job['id']}/results")
            assert results_response.status_code == 200
            results = results_response.json()
            assert len(results) == 4
            assert results[0]["data_source"] == "LOCAL"
            assert results[0]["naid"] == "LOCAL-PDF-SCHULTZE-NAUMBURG-1931"
            assert "Paul Schultze-Naumburg" in results[0]["title"]
            assert results[0]["birth_date"] == "1869-06-10"
            assert results[0]["birth_place"] == "Almrich"
            evidence_text = " ".join(
                value
                for evidence in results[0]["evidences"]
                for value in [evidence["label"], evidence["detail"] or ""]
            )
            assert "Almrich" in evidence_text
            assert "Naumburg" in evidence_text
            assert "Weimar" in evidence_text
            assert {result["data_source"] for result in results} == {"LOCAL", "MOCK"}


@pytest.mark.asyncio
async def test_create_search_job_with_demo_mode_returns_mock_results_without_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("NARATRACE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("NARA_API_KEY", raising=False)
    monkeypatch.delenv("NARATRACE_MOCK_MODE", raising=False)
    reset_settings_cache()
    reset_paths_cache()

    app = create_app()
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            create_response = await client.post(
                "/api/search",
                json={
                    "first_name": "Paul",
                    "last_name": "Schultze-Naumburg",
                    "membership_number": "347.541",
                    "demo_mode": True,
                },
            )
            assert create_response.status_code == 201
            job = create_response.json()
            assert job["status"] == "queued"
            job = await wait_for_terminal_job(client, job["id"])
            assert job["status"] == "complete"
            assert job["result_count"] == 4
            assert job["mock_mode"] is True
            assert "Demo-Modus" in " ".join(job["warnings"])

            results_response = await client.get(f"/api/search/{job['id']}/results")
            assert results_response.status_code == 200
            results = results_response.json()
            assert results[0]["data_source"] == "LOCAL"
            assert results[0]["record_group"] == "Lokale Demo-Datei"
            assert {result["data_source"] for result in results} == {"LOCAL", "MOCK"}


@pytest.mark.asyncio
async def test_search_job_export_returns_research_markdown(tmp_path, monkeypatch):
    monkeypatch.setenv("NARATRACE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("NARA_API_KEY", raising=False)
    monkeypatch.delenv("NARATRACE_MOCK_MODE", raising=False)
    reset_settings_cache()
    reset_paths_cache()

    app = create_app()
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            create_response = await client.post(
                "/api/search",
                json={
                    "first_name": "Paul",
                    "last_name": "Schultze-Naumburg",
                    "membership_number": "347.541",
                    "demo_mode": True,
                },
            )
            job = await wait_for_terminal_job(client, create_response.json()["id"])

            export_response = await client.get(f"/api/search/{job['id']}/export.md")

            assert export_response.status_code == 200
            assert export_response.headers["content-type"].startswith("text/markdown")
            assert "attachment;" in export_response.headers["content-disposition"]
            report = export_response.text
            pdf_response = await client.get(f"/api/search/{job['id']}/export.pdf")
            assert pdf_response.status_code == 200
            assert pdf_response.headers["content-type"].startswith("application/pdf")
            assert pdf_response.content.startswith(b"%PDF")

            results = (await client.get(f"/api/search/{job['id']}/results")).json()
            result_pdf_response = await client.get(f"/api/search/{job['id']}/results/{results[0]['id']}/export.pdf")
            assert result_pdf_response.status_code == 200
            assert result_pdf_response.headers["content-type"].startswith("application/pdf")
            assert result_pdf_response.content.startswith(b"%PDF")

            zip_response = await client.get(f"/api/search/{job['id']}/export.zip")
            assert zip_response.status_code == 200
            assert zip_response.headers["content-type"].startswith("application/zip")
            with zipfile.ZipFile(BytesIO(zip_response.content)) as archive:
                names = set(archive.namelist())
                assert "index.html" in names
                assert "README.txt" in names
                assert any(name.startswith("results/") and name.endswith(".html") for name in names)
                index_html = archive.read("index.html").decode("utf-8")
                assert "NARATrace Suchverlauf" in index_html
            assert "# NARATrace Recherchebericht: Paul Schultze-Naumburg" in report
            assert "## Suchprofil" in report
            assert "## Treffer" in report
            assert "LOCAL-PDF-SCHULTZE-NAUMBURG-1931" in report
            assert "NARATrace ist ein unabhängiges, inoffizielles Forschungswerkzeug" in report


@pytest.mark.asyncio
async def test_delete_search_result_and_search_job(tmp_path, monkeypatch):
    monkeypatch.setenv("NARATRACE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("NARA_API_KEY", raising=False)
    monkeypatch.delenv("NARATRACE_MOCK_MODE", raising=False)
    reset_settings_cache()
    reset_paths_cache()

    app = create_app()
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            create_response = await client.post(
                "/api/search",
                json={
                    "first_name": "Paul",
                    "last_name": "Schultze-Naumburg",
                    "demo_mode": True,
                },
            )
            job = create_response.json()
            job = await wait_for_terminal_job(client, job["id"])
            results_response = await client.get(f"/api/search/{job['id']}/results")
            results = results_response.json()
            assert len(results) == 4

            delete_result_response = await client.delete(f"/api/search/{job['id']}/results/{results[0]['id']}")
            assert delete_result_response.status_code == 204
            remaining_results = (await client.get(f"/api/search/{job['id']}/results")).json()
            assert len(remaining_results) == 3
            assert all(result["id"] != results[0]["id"] for result in remaining_results)

            delete_job_response = await client.delete(f"/api/search/{job['id']}")
            assert delete_job_response.status_code == 204
            missing_job_response = await client.get(f"/api/search/{job['id']}")
            assert missing_job_response.status_code == 404


@pytest.mark.asyncio
async def test_create_search_job_with_api_key_stores_real_nara_candidates(tmp_path, monkeypatch):
    isolate_nara_key(monkeypatch, tmp_path, api_key="test-key")
    monkeypatch.setenv("NARATRACE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("NARATRACE_MOCK_MODE", raising=False)
    reset_settings_cache()
    reset_paths_cache()

    async def fake_run_nara_candidate_search(payload, api_key):
        return NaraSearchResponse(
            total=1,
            raw={"mocked": True},
            items=[
                NaraSearchItem(
                    record=NaraRecord(
                        naId=123456,
                        title="Paul Schultze-Naumburg membership record",
                        description="Includes 1869, Naumburg and Mitgliedsnummer 347541.",
                        recordGroupNumber="242",
                        digitalObjects=[{"objectUrl": "https://catalog.archives.gov/object/mock", "extractedText": "347541"}],
                    ),
                    raw={"_source": {"record": {"naId": 123456}}},
                )
            ],
        )

    monkeypatch.setattr("naratrace.processing.jobs.run_nara_candidate_search", fake_run_nara_candidate_search)

    async def fake_materialize_relevant_pages(job_id, naid, record, payload):
        return [
            MaterializedPage(
                object_data=record.digitalObjects[0],
                page_number=1,
                image_url="https://catalog.archives.gov/object/mock.jpg",
                local_path=None,
                nara_text="Paul Schultze-Naumburg 1869 Naumburg 347541",
                ocr_text=None,
                ocr_engine=None,
            )
        ]

    monkeypatch.setattr("naratrace.processing.jobs.materialize_relevant_pages", fake_materialize_relevant_pages)

    app = create_app()
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            create_response = await client.post(
                "/api/search",
                json={
                    "first_name": "Paul",
                    "last_name": "Schultze-Naumburg",
                    "birth_year": 1869,
                    "residence_places": "Naumburg",
                    "membership_number": "347.541",
                    "max_candidates": 25,
                },
            )
            assert create_response.status_code == 201
            job = create_response.json()
            assert job["status"] == "queued"
            job = await wait_for_terminal_job(client, job["id"])
            assert job["status"] == "complete"
            assert job["result_count"] == 1

            results_response = await client.get(f"/api/search/{job['id']}/results")
            assert results_response.status_code == 200
            results = results_response.json()
            assert results[0]["data_source"] == "NARA"
            assert results[0]["naid"] == "123456"
            assert results[0]["record_group"] == "Record Group 242"
            assert results[0]["match_score"] >= 80
            assert results[0]["source_page_url"] == "https://catalog.archives.gov/object/mock.jpg"
            assert results[0]["transcript_text"] == "Paul Schultze-Naumburg 1869 Naumburg 347541"
            assert results[0]["transcript_source"] == "NARA Extracted Text"
            assert results[0]["media_pages"][0]["media_type"] == "image"
            assert results[0]["media_pages"][0]["media_url"] == "https://catalog.archives.gov/object/mock.jpg"
            assert results[0]["record_years"] == [1869]
            assert {"Schultze-Naumburg", "347541"}.issubset(set(results[0]["media_pages"][0]["match_terms"]))


@pytest.mark.asyncio
async def test_search_result_groups_multiple_media_pages_and_mp4(tmp_path, monkeypatch):
    isolate_nara_key(monkeypatch, tmp_path, api_key="test-key")
    monkeypatch.setenv("NARATRACE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("NARATRACE_MOCK_MODE", raising=False)
    reset_settings_cache()
    reset_paths_cache()

    async def fake_run_nara_candidate_search(payload, api_key):
        return NaraSearchResponse(
            total=1,
            raw={"mocked": True},
            items=[
                NaraSearchItem(
                    record=NaraRecord(
                        naId=213259758,
                        title="Adolf Hitler digital objects",
                        description="Adolf Hitler with image and moving image material.",
                        digitalObjects=[
                            {
                                "objectUrl": "https://catalog.archives.gov/media/page-1.jpg",
                                "objectFilename": "page-1.jpg",
                                "mimeType": "image/jpeg",
                                "extractedText": "Adolf Hitler",
                            },
                            {
                                "objectUrl": "https://catalog.archives.gov/media/film.mp4",
                                "objectFilename": "film.mp4",
                                "mimeType": "video/mp4",
                            },
                        ],
                    ),
                    raw={"_source": {"record": {"naId": 213259758}}},
                )
            ],
        )

    async def fake_materialize_relevant_pages(job_id, naid, record, payload):
        return [
            MaterializedPage(
                object_data=record.digitalObjects[0],
                page_number=1,
                image_url="https://catalog.archives.gov/media/page-1.jpg",
                local_path=None,
                nara_text="Adolf Hitler",
                ocr_text=None,
                ocr_engine=None,
            ),
            MaterializedPage(
                object_data=record.digitalObjects[1],
                page_number=2,
                image_url="https://catalog.archives.gov/media/film.mp4",
                local_path=None,
                nara_text=None,
                ocr_text=None,
                ocr_engine=None,
            ),
        ]

    monkeypatch.setattr("naratrace.processing.jobs.run_nara_candidate_search", fake_run_nara_candidate_search)
    monkeypatch.setattr("naratrace.processing.jobs.materialize_relevant_pages", fake_materialize_relevant_pages)

    app = create_app()
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            create_response = await client.post("/api/search", json={"first_name": "Adolf", "last_name": "Hitler"})
            assert create_response.status_code == 201
            job = await wait_for_terminal_job(client, create_response.json()["id"])

            results = (await client.get(f"/api/search/{job['id']}/results")).json()
            assert len(results) == 1
            assert results[0]["relevant_pages_count"] == 2
            assert [page["media_type"] for page in results[0]["media_pages"]] == ["image", "video"]
            assert results[0]["media_pages"][1]["media_url"] == "https://catalog.archives.gov/media/film.mp4"
            assert results[0]["media_pages"][1]["mime_type"] == "video/mp4"

            history = (await client.get("/api/search")).json()
            assert history[0]["preview_title"] == "Adolf Hitler"
            assert history[0]["preview_media_type"] == "image"
            assert history[0]["preview_media_url"] == "https://catalog.archives.gov/media/page-1.jpg"


@pytest.mark.asyncio
async def test_search_job_filters_candidates_without_coherent_surname(tmp_path, monkeypatch):
    isolate_nara_key(monkeypatch, tmp_path, api_key="test-key")
    monkeypatch.setenv("NARATRACE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("NARATRACE_MOCK_MODE", raising=False)
    reset_settings_cache()
    reset_paths_cache()

    async def fake_run_nara_candidate_search(payload, api_key):
        return NaraSearchResponse(
            total=2,
            raw={"mocked": True},
            items=[
                NaraSearchItem(
                    record=NaraRecord(
                        naId=111,
                        title="Completely different surname correspondence",
                        description="Adolf Hitler 1869 Naumburg",
                        digitalObjects=[{"objectUrl": "https://catalog.archives.gov/media/different.jpg"}],
                    ),
                    raw={"_source": {"record": {"naId": 111}}},
                ),
                NaraSearchItem(
                    record=NaraRecord(
                        naId=222,
                        title="Paul SchulzeNaumburg NSDAP membership card",
                        description="Karteikarte mit Mitgliedsnummer 347541.",
                        digitalObjects=[{"objectUrl": "https://catalog.archives.gov/media/card.jpg", "extractedText": "SchulzeNaumburg 347541"}],
                    ),
                    raw={"_source": {"record": {"naId": 222}}},
                ),
            ],
        )

    materialized_naids: list[str] = []

    async def fake_materialize_relevant_pages(job_id, naid, record, payload):
        materialized_naids.append(naid)
        return [
            MaterializedPage(
                object_data=record.digitalObjects[0],
                page_number=1,
                image_url=record.digitalObjects[0]["objectUrl"],
                local_path=None,
                nara_text=record.digitalObjects[0].get("extractedText"),
                ocr_text=None,
                ocr_engine=None,
            )
        ]

    monkeypatch.setattr("naratrace.processing.jobs.run_nara_candidate_search", fake_run_nara_candidate_search)
    monkeypatch.setattr("naratrace.processing.jobs.materialize_relevant_pages", fake_materialize_relevant_pages)

    app = create_app()
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            create_response = await client.post(
                "/api/search",
                json={"first_name": "Paul", "last_name": "Schultze-Naumburg", "membership_number": "347541"},
            )
            assert create_response.status_code == 201
            job = await wait_for_terminal_job(client, create_response.json()["id"])

            results = (await client.get(f"/api/search/{job['id']}/results")).json()
            assert job["result_count"] == 1
            assert [result["naid"] for result in results] == ["222"]
            assert materialized_naids == ["222"]


@pytest.mark.asyncio
async def test_search_job_requires_compound_surname_match_without_identifier(tmp_path, monkeypatch):
    isolate_nara_key(monkeypatch, tmp_path, api_key="test-key")
    monkeypatch.setenv("NARATRACE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("NARATRACE_MOCK_MODE", raising=False)
    reset_settings_cache()
    reset_paths_cache()

    async def fake_run_nara_candidate_search(payload, api_key):
        return NaraSearchResponse(
            total=2,
            raw={"mocked": True},
            items=[
                NaraSearchItem(
                    record=NaraRecord(
                        naId=555,
                        title="Paul Schultze correspondence",
                        description="Architectural correspondence mentioning Weimar.",
                        digitalObjects=[{"objectUrl": "https://catalog.archives.gov/media/schultze.jpg", "extractedText": "Paul Schultze"}],
                    ),
                    raw={"_source": {"record": {"naId": 555}}},
                ),
                NaraSearchItem(
                    record=NaraRecord(
                        naId=556,
                        title="Paul Schultze-Naumburg correspondence",
                        description="Architectural correspondence mentioning Weimar.",
                        digitalObjects=[
                            {
                                "objectUrl": "https://catalog.archives.gov/media/schultze-naumburg.jpg",
                                "extractedText": "Paul Schultze-Naumburg",
                            }
                        ],
                    ),
                    raw={"_source": {"record": {"naId": 556}}},
                ),
            ],
        )

    materialized_naids: list[str] = []

    async def fake_materialize_relevant_pages(job_id, naid, record, payload):
        materialized_naids.append(naid)
        return [
            MaterializedPage(
                object_data=record.digitalObjects[0],
                page_number=1,
                image_url=record.digitalObjects[0]["objectUrl"],
                local_path=None,
                nara_text=record.digitalObjects[0].get("extractedText"),
                ocr_text=None,
                ocr_engine=None,
            )
        ]

    monkeypatch.setattr("naratrace.processing.jobs.run_nara_candidate_search", fake_run_nara_candidate_search)
    monkeypatch.setattr("naratrace.processing.jobs.materialize_relevant_pages", fake_materialize_relevant_pages)

    app = create_app()
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            create_response = await client.post(
                "/api/search",
                json={"first_name": "Paul", "last_name": "Schultze-Naumburg"},
            )
            assert create_response.status_code == 201
            job = await wait_for_terminal_job(client, create_response.json()["id"])

            results = (await client.get(f"/api/search/{job['id']}/results")).json()
            assert job["result_count"] == 1
            assert [result["naid"] for result in results] == ["556"]
            assert materialized_naids == ["556"]


@pytest.mark.asyncio
async def test_search_job_ranks_same_page_profile_matches_above_metadata_only_matches(tmp_path, monkeypatch):
    isolate_nara_key(monkeypatch, tmp_path, api_key="test-key")
    monkeypatch.setenv("NARATRACE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("NARATRACE_MOCK_MODE", raising=False)
    reset_settings_cache()
    reset_paths_cache()

    async def fake_run_nara_candidate_search(payload, api_key):
        return NaraSearchResponse(
            total=2,
            raw={"mocked": True},
            items=[
                NaraSearchItem(
                    record=NaraRecord(
                        naId=777,
                        title="Paul Schultze-Naumburg membership index",
                        description="Metadata mentions Mitgliedsnummer 347541 and Naumburg in an 1800 collection note.",
                        digitalObjects=[
                            {
                                "objectUrl": "https://catalog.archives.gov/media/metadata-only.jpg",
                                "extractedText": "Unrelated typed index page",
                            }
                        ],
                    ),
                    raw={"_source": {"record": {"naId": 777}}},
                ),
                NaraSearchItem(
                    record=NaraRecord(
                        naId=778,
                        title="Paul Schultze-Naumburg membership card",
                        description="Metadata mentions Mitgliedsnummer 347541 and Naumburg.",
                        digitalObjects=[
                            {
                                "objectUrl": "https://catalog.archives.gov/media/same-page.jpg",
                                "extractedText": "Paul Schultze-Naumburg 1869 Naumburg Mitgliedsnummer 347541",
                            }
                        ],
                    ),
                    raw={"_source": {"record": {"naId": 778}}},
                ),
            ],
        )

    async def fake_materialize_relevant_pages(job_id, naid, record, payload):
        return [
            MaterializedPage(
                object_data=record.digitalObjects[0],
                page_number=1,
                image_url=record.digitalObjects[0]["objectUrl"],
                local_path=None,
                nara_text=record.digitalObjects[0].get("extractedText"),
                ocr_text=None,
                ocr_engine=None,
            )
        ]

    monkeypatch.setattr("naratrace.processing.jobs.run_nara_candidate_search", fake_run_nara_candidate_search)
    monkeypatch.setattr("naratrace.processing.jobs.materialize_relevant_pages", fake_materialize_relevant_pages)

    app = create_app()
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            create_response = await client.post(
                "/api/search",
                json={
                    "first_name": "Paul",
                    "last_name": "Schultze-Naumburg",
                    "birth_year": 1869,
                    "residence_places": "Naumburg",
                    "membership_number": "347.541",
                },
            )
            assert create_response.status_code == 201
            job = await wait_for_terminal_job(client, create_response.json()["id"])

            results = (await client.get(f"/api/search/{job['id']}/results")).json()
            assert [result["naid"] for result in results] == ["778", "777"]
            assert results[0]["match_score"] > results[1]["match_score"]
            evidence_labels = [evidence["label"] for evidence in results[0]["evidences"]]
            assert any("derselben Originalseite" in label for label in evidence_labels)


@pytest.mark.asyncio
async def test_search_job_caps_original_page_materialization_for_large_candidate_sets(tmp_path, monkeypatch):
    isolate_nara_key(monkeypatch, tmp_path, api_key="test-key")
    monkeypatch.setenv("NARATRACE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("NARATRACE_MOCK_MODE", raising=False)
    reset_settings_cache()
    reset_paths_cache()

    async def fake_run_nara_candidate_search(payload, api_key):
        return NaraSearchResponse(
            total=60,
            raw={"mocked": True},
            items=[
                NaraSearchItem(
                    record=NaraRecord(
                        naId=9000 + index,
                        title=f"Paul Schultze-Naumburg candidate {index}",
                        description="Metadata mentions Naumburg.",
                        digitalObjects=[{"objectUrl": f"https://catalog.archives.gov/media/{index}.jpg"}],
                    ),
                    raw={"_source": {"record": {"naId": 9000 + index}}},
                )
                for index in range(60)
            ],
        )

    materialized_naids: list[str] = []

    async def fake_materialize_relevant_pages(job_id, naid, record, payload):
        materialized_naids.append(naid)
        return []

    monkeypatch.setattr("naratrace.processing.jobs.run_nara_candidate_search", fake_run_nara_candidate_search)
    monkeypatch.setattr("naratrace.processing.jobs.materialize_relevant_pages", fake_materialize_relevant_pages)

    app = create_app()
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            create_response = await client.post(
                "/api/search",
                json={"first_name": "Paul", "last_name": "Schultze-Naumburg", "max_candidates": 60},
            )
            assert create_response.status_code == 201
            job = await wait_for_terminal_job(client, create_response.json()["id"])

            assert job["status"] == "complete"
            assert job["result_count"] == 60
            assert len(materialized_naids) == 50
            assert "Originalseiten und OCR" in " ".join(job["warnings"])


@pytest.mark.asyncio
async def test_search_job_keeps_metadata_fallback_candidates_when_strict_filters_would_drop_all(tmp_path, monkeypatch):
    isolate_nara_key(monkeypatch, tmp_path, api_key="test-key")
    monkeypatch.setenv("NARATRACE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("NARATRACE_MOCK_MODE", raising=False)
    reset_settings_cache()
    reset_paths_cache()

    async def fake_run_nara_candidate_search(payload, api_key):
        return NaraSearchResponse(
            total=1,
            raw={"mocked": True},
            warnings=[
                "NARA lieferte für die Detailabfrage einen temporären Serverfehler; "
                "NARATrace hat automatisch eine kleinere Metadatenabfrage verwendet."
            ],
            items=[
                NaraSearchItem(
                    record=NaraRecord(
                        naId=270566795,
                        title="Number 719 (Serial 719) (1 of 2)",
                        generalRecordsTypes=["Textual Records"],
                        digitalObjects=[
                            {
                                "objectUrl": "https://catalog.archives.gov/media/T77-0719-0001.jpg",
                                "extractedText": "Paul Schultze-Nauburg",
                            }
                        ],
                    ),
                    raw={"_score": 80.5, "_source": {"record": {"naId": 270566795}}},
                )
            ],
        )

    async def fake_materialize_relevant_pages(job_id, naid, record, payload):
        return [
            MaterializedPage(
                object_data=record.digitalObjects[0],
                page_number=1,
                image_url=record.digitalObjects[0]["objectUrl"],
                local_path=None,
                nara_text=record.digitalObjects[0].get("extractedText"),
                ocr_text=None,
                ocr_engine=None,
            )
        ]

    monkeypatch.setattr("naratrace.processing.jobs.run_nara_candidate_search", fake_run_nara_candidate_search)
    monkeypatch.setattr("naratrace.processing.jobs.materialize_relevant_pages", fake_materialize_relevant_pages)

    app = create_app()
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            create_response = await client.post(
                "/api/search",
                json={
                    "first_name": "Paul",
                    "last_name": "Schultze-Naumburg",
                    "source_categories": ["nsdap_membership_cards"],
                    "max_candidates": 50,
                },
            )
            assert create_response.status_code == 201
            job = await wait_for_terminal_job(client, create_response.json()["id"])

            results = (await client.get(f"/api/search/{job['id']}/results")).json()
            assert job["status"] == "complete"
            assert job["result_count"] == 1
            assert results[0]["naid"] == "270566795"
            assert "Metadatenhinweise" in " ".join(job["warnings"])
            assert "keine Kandidaten gefunden" not in " ".join(job["warnings"])


@pytest.mark.asyncio
async def test_search_job_filters_selected_source_categories(tmp_path, monkeypatch):
    isolate_nara_key(monkeypatch, tmp_path, api_key="test-key")
    monkeypatch.setenv("NARATRACE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("NARATRACE_MOCK_MODE", raising=False)
    reset_settings_cache()
    reset_paths_cache()

    async def fake_run_nara_candidate_search(payload, api_key):
        return NaraSearchResponse(
            total=2,
            raw={"mocked": True},
            items=[
                NaraSearchItem(
                    record=NaraRecord(
                        naId=333,
                        title="Paul Schultze-Naumburg portrait photograph",
                        description="Photograph of Paul Schultze-Naumburg",
                        generalRecordsTypes=["Photographs and other Graphic Materials"],
                        digitalObjects=[{"objectUrl": "https://catalog.archives.gov/media/portrait.jpg"}],
                    ),
                    raw={"_source": {"record": {"naId": 333}}},
                ),
                NaraSearchItem(
                    record=NaraRecord(
                        naId=444,
                        title="Paul Schultze-Naumburg NSDAP membership card",
                        description="Nazi Party membership card with number 347541.",
                        generalRecordsTypes=["Textual Records"],
                        digitalObjects=[{"objectUrl": "https://catalog.archives.gov/media/nsdap-card.jpg", "extractedText": "NSDAP membership card Schultze-Naumburg 347541"}],
                    ),
                    raw={"_source": {"record": {"naId": 444}}},
                ),
            ],
        )

    async def fake_materialize_relevant_pages(job_id, naid, record, payload):
        return [
            MaterializedPage(
                object_data=record.digitalObjects[0],
                page_number=1,
                image_url=record.digitalObjects[0]["objectUrl"],
                local_path=None,
                nara_text=record.digitalObjects[0].get("extractedText"),
                ocr_text=None,
                ocr_engine=None,
            )
        ]

    monkeypatch.setattr("naratrace.processing.jobs.run_nara_candidate_search", fake_run_nara_candidate_search)
    monkeypatch.setattr("naratrace.processing.jobs.materialize_relevant_pages", fake_materialize_relevant_pages)

    app = create_app()
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            create_response = await client.post(
                "/api/search",
                json={
                    "last_name": "Schultze-Naumburg",
                    "membership_number": "347541",
                    "source_categories": ["nsdap_membership_cards"],
                },
            )
            assert create_response.status_code == 201
            job = await wait_for_terminal_job(client, create_response.json()["id"])

            results = (await client.get(f"/api/search/{job['id']}/results")).json()
            assert job["result_count"] == 2
            assert [result["naid"] for result in results] == ["444", "333"]
            assert results[0]["source_category"] == "nsdap_membership_cards"
            assert results[0]["source_category_label"] == "NSDAP-Karteikarten"
            assert "Metadatenhinweise" in " ".join(job["warnings"])


@pytest.mark.asyncio
async def test_search_job_commits_candidates_while_materialization_continues(tmp_path, monkeypatch):
    isolate_nara_key(monkeypatch, tmp_path, api_key="test-key")
    monkeypatch.setenv("NARATRACE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("NARATRACE_MOCK_MODE", raising=False)
    reset_settings_cache()
    reset_paths_cache()

    async def fake_run_nara_candidate_search(payload, api_key):
        return NaraSearchResponse(
            total=2,
            raw={"mocked": True},
            items=[
                NaraSearchItem(
                    record=NaraRecord(
                        naId=123456,
                        title="Paul Schultze-Naumburg first record",
                        description="Includes Naumburg and Mitgliedsnummer 347541.",
                        recordGroupNumber="242",
                        digitalObjects=[{"objectUrl": "https://catalog.archives.gov/object/first", "extractedText": "347541"}],
                    ),
                    raw={"_source": {"record": {"naId": 123456}}},
                ),
                NaraSearchItem(
                    record=NaraRecord(
                        naId=654321,
                        title="Paul Schultze-Naumburg second record",
                        description="Includes Weimar and 1869.",
                        recordGroupNumber="242",
                        digitalObjects=[{"objectUrl": "https://catalog.archives.gov/object/second", "extractedText": "Weimar 1869"}],
                    ),
                    raw={"_source": {"record": {"naId": 654321}}},
                ),
            ],
        )

    materialize_calls = 0
    second_materialization_started = asyncio.Event()
    release_second_materialization = asyncio.Event()

    async def fake_materialize_relevant_pages(job_id, naid, record, payload):
        nonlocal materialize_calls
        materialize_calls += 1
        if materialize_calls == 2:
            second_materialization_started.set()
            await release_second_materialization.wait()
        return [
            MaterializedPage(
                object_data=record.digitalObjects[0],
                page_number=1,
                image_url=f"https://catalog.archives.gov/object/{naid}.jpg",
                local_path=None,
                nara_text=record.digitalObjects[0]["extractedText"],
                ocr_text=None,
                ocr_engine=None,
            )
        ]

    monkeypatch.setattr("naratrace.processing.jobs.run_nara_candidate_search", fake_run_nara_candidate_search)
    monkeypatch.setattr("naratrace.processing.jobs.materialize_relevant_pages", fake_materialize_relevant_pages)

    app = create_app()
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            create_response = await client.post(
                "/api/search",
                json={
                    "first_name": "Paul",
                    "last_name": "Schultze-Naumburg",
                    "residence_places": "Naumburg, Weimar",
                    "membership_number": "347.541",
                    "max_candidates": 25,
                },
            )
            assert create_response.status_code == 201
            job = create_response.json()

            await asyncio.wait_for(second_materialization_started.wait(), timeout=2)
            running_response = await client.get(f"/api/search/{job['id']}")
            assert running_response.status_code == 200
            running_job = running_response.json()
            assert running_job["status"] == "downloading_pages_ocr"
            assert running_job["result_count"] == 1

            release_second_materialization.set()
            completed_job = await wait_for_terminal_job(client, job["id"])
            assert completed_job["status"] == "complete"
            assert completed_job["result_count"] == 2


@pytest.mark.asyncio
async def test_cancel_search_job_keeps_background_task_cancelled(tmp_path, monkeypatch):
    isolate_nara_key(monkeypatch, tmp_path, api_key="test-key")
    monkeypatch.setenv("NARATRACE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("NARATRACE_MOCK_MODE", raising=False)
    reset_settings_cache()
    reset_paths_cache()

    async def fake_run_nara_candidate_search(payload, api_key):
        return NaraSearchResponse(
            total=1,
            raw={"mocked": True},
            items=[
                NaraSearchItem(
                    record=NaraRecord(
                        naId=123456,
                        title="Paul Schultze-Naumburg cancellable record",
                        description="Includes Naumburg and Mitgliedsnummer 347541.",
                        recordGroupNumber="242",
                        digitalObjects=[{"objectUrl": "https://catalog.archives.gov/object/cancel", "extractedText": "347541"}],
                    ),
                    raw={"_source": {"record": {"naId": 123456}}},
                )
            ],
        )

    materialization_started = asyncio.Event()
    materialization_cancelled = asyncio.Event()
    release_materialization = asyncio.Event()

    async def fake_materialize_relevant_pages(job_id, naid, record, payload):
        materialization_started.set()
        try:
            await release_materialization.wait()
        except asyncio.CancelledError:
            materialization_cancelled.set()
            raise
        return [
            MaterializedPage(
                object_data=record.digitalObjects[0],
                page_number=1,
                image_url="https://catalog.archives.gov/object/cancel.jpg",
                local_path=None,
                nara_text="Paul Schultze-Naumburg 347541",
                ocr_text=None,
                ocr_engine=None,
            )
        ]

    monkeypatch.setattr("naratrace.processing.jobs.run_nara_candidate_search", fake_run_nara_candidate_search)
    monkeypatch.setattr("naratrace.processing.jobs.materialize_relevant_pages", fake_materialize_relevant_pages)

    app = create_app()
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            create_response = await client.post(
                "/api/search",
                json={"first_name": "Paul", "last_name": "Schultze-Naumburg", "max_candidates": 10},
            )
            assert create_response.status_code == 201
            job = create_response.json()

            await asyncio.wait_for(materialization_started.wait(), timeout=2)
            cancel_response = await client.post(f"/api/search/{job['id']}/cancel")
            assert cancel_response.status_code == 200
            cancelled_job = cancel_response.json()
            assert cancelled_job["status"] == "cancelled"

            await asyncio.wait_for(materialization_cancelled.wait(), timeout=2)
            release_materialization.set()
            await asyncio.sleep(0.1)
            final_response = await client.get(f"/api/search/{job['id']}")
            assert final_response.status_code == 200
            final_job = final_response.json()
            assert final_job["status"] == "cancelled"
            assert final_job["result_count"] == 0


@pytest.mark.asyncio
async def test_update_search_result_transcript_persists_manual_correction(tmp_path, monkeypatch):
    isolate_nara_key(monkeypatch, tmp_path, api_key="test-key")
    monkeypatch.setenv("NARATRACE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("NARATRACE_MOCK_MODE", raising=False)
    reset_settings_cache()
    reset_paths_cache()

    async def fake_run_nara_candidate_search(payload, api_key):
        return NaraSearchResponse(
            total=1,
            raw={"mocked": True},
            items=[
                NaraSearchItem(
                    record=NaraRecord(
                        naId=987654,
                        title="Membership card",
                        digitalObjects=[
                            {
                                "objectId": "obj-1",
                                "objectUrl": "https://catalog.archives.gov/object/card.jpg",
                                "objectFilename": "card.jpg",
                                "extractedText": "Raw OCR Schultze Naumburg",
                            }
                        ],
                    ),
                    raw={"_source": {"record": {"naId": 987654}}},
                )
            ],
        )

    async def fake_materialize_relevant_pages(job_id, naid, record, payload):
        return [
            MaterializedPage(
                object_data=record.digitalObjects[0],
                page_number=1,
                image_url="https://catalog.archives.gov/object/card.jpg",
                local_path=None,
                nara_text="Raw OCR Schultze Naumburg",
                ocr_text=None,
                ocr_engine=None,
            )
        ]

    monkeypatch.setattr("naratrace.processing.jobs.run_nara_candidate_search", fake_run_nara_candidate_search)
    monkeypatch.setattr("naratrace.processing.jobs.materialize_relevant_pages", fake_materialize_relevant_pages)

    app = create_app()
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            create_response = await client.post(
                "/api/search",
                json={"first_name": "Paul", "last_name": "Schultze-Naumburg", "max_candidates": 10},
            )
            job = create_response.json()
            job = await wait_for_terminal_job(client, job["id"])
            result = (await client.get(f"/api/search/{job['id']}/results")).json()[0]

            update_response = await client.patch(
                f"/api/search/{job['id']}/results/{result['id']}/transcript",
                json={"transcript_text": "Korrigierte Transkription"},
            )

            assert update_response.status_code == 200
            updated = update_response.json()
            assert updated["transcript_text"] == "Korrigierte Transkription"
            assert updated["transcript_source"] == "manuelle Korrektur"
            assert updated["transcript_edited"] is True

            reloaded = (await client.get(f"/api/search/{job['id']}/results")).json()[0]
            assert reloaded["transcript_text"] == "Korrigierte Transkription"
            assert reloaded["transcript_edited"] is True
