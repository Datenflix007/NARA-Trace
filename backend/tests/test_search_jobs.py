from __future__ import annotations

import httpx
import pytest
from sqlalchemy import select

from naratrace.core.config import reset_settings_cache
from naratrace.core.paths import reset_paths_cache
from naratrace.database.models import SearchField, SearchVariant
from naratrace.database.session import session_scope
from naratrace.main import create_app
from naratrace.nara.client import NaraRecord, NaraSearchItem, NaraSearchResponse


@pytest.mark.asyncio
async def test_create_search_job_without_mock_does_not_invent_results(tmp_path, monkeypatch):
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
            assert job["status"] == "complete"
            assert job["result_count"] == 4
            assert job["mock_mode"] is True

            results_response = await client.get(f"/api/search/{job['id']}/results")
            assert results_response.status_code == 200
            results = results_response.json()
            assert len(results) == 4
            assert {result["data_source"] for result in results} == {"MOCK"}
            assert all(result["naid"].startswith("MOCK-") for result in results)


@pytest.mark.asyncio
async def test_create_search_job_with_api_key_stores_real_nara_candidates(tmp_path, monkeypatch):
    monkeypatch.setenv("NARATRACE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("NARA_API_KEY", "test-key")
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
            assert job["status"] == "complete"
            assert job["result_count"] == 1

            results_response = await client.get(f"/api/search/{job['id']}/results")
            assert results_response.status_code == 200
            results = results_response.json()
            assert results[0]["data_source"] == "NARA"
            assert results[0]["naid"] == "123456"
            assert results[0]["record_group"] == "Record Group 242"
            assert results[0]["match_score"] >= 80
