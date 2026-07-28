from __future__ import annotations

import asyncio
import mimetypes

from fastapi import APIRouter, HTTPException, Response, status
from fastapi.responses import FileResponse

from naratrace import __version__
from naratrace.api.schemas import (
    ApiKeyTestResponse,
    HealthResponse,
    NaraApiUsageResponse,
    SearchJobResponse,
    SearchRequest,
    SearchResultResponse,
    SettingsResponse,
    SettingsUpdate,
    TranscriptUpdate,
)
from naratrace.core.config import get_settings
from naratrace.core.paths import get_local_paths
from naratrace.core.secrets import (
    delete_nara_api_key,
    get_nara_api_key,
    get_nara_api_key_status,
    set_nara_api_key,
)
from naratrace.nara.client import NaraCatalogClient, NaraClientError
from naratrace.nara.usage import NaraApiUsage, get_nara_api_usage
from naratrace.processing.jobs import (
    create_search_job,
    delete_search_job,
    delete_search_result,
    get_candidate_page_image_path,
    get_search_job,
    get_search_results,
    list_search_jobs,
    run_search_job,
    update_search_result_transcript,
)

api_router = APIRouter(prefix="/api")


@api_router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_settings()
    paths = get_local_paths()
    return HealthResponse(
        status="ok",
        app="NARATrace",
        version=__version__,
        mock_mode=settings.mock_mode,
        bind_host=settings.host,
        bind_port=settings.port,
        data_dir=str(paths.root),
        database_path=str(paths.database_file),
    )


@api_router.get("/settings", response_model=SettingsResponse)
async def read_settings() -> SettingsResponse:
    return build_settings_response()


@api_router.get("/search", response_model=list[SearchJobResponse])
async def read_search_history() -> list[SearchJobResponse]:
    return list_search_jobs()


@api_router.post("/search", response_model=SearchJobResponse, status_code=status.HTTP_201_CREATED)
async def start_search(payload: SearchRequest) -> SearchJobResponse:
    job = await create_search_job(payload)
    asyncio.create_task(run_search_job(job.id, payload))
    return job


@api_router.get("/search/{job_id}", response_model=SearchJobResponse)
async def read_search_job(job_id: str) -> SearchJobResponse:
    job = get_search_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suchjob wurde nicht gefunden.")
    return job


@api_router.delete("/search/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_search_job(job_id: str) -> Response:
    if not delete_search_job(job_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suchjob wurde nicht gefunden.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@api_router.post("/search/{job_id}/cancel", response_model=SearchJobResponse)
async def cancel_search_job(job_id: str) -> SearchJobResponse:
    job = get_search_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suchjob wurde nicht gefunden.")
    return job


@api_router.get("/search/{job_id}/results", response_model=list[SearchResultResponse])
async def read_search_results(job_id: str) -> list[SearchResultResponse]:
    results = get_search_results(job_id)
    if results is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suchjob wurde nicht gefunden.")
    return results


@api_router.delete("/search/{job_id}/results/{result_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_search_result(job_id: str, result_id: int) -> Response:
    if not delete_search_result(job_id, result_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Treffer wurde nicht gefunden.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@api_router.patch("/search/{job_id}/results/{result_id}/transcript", response_model=SearchResultResponse)
async def update_result_transcript(job_id: str, result_id: int, payload: TranscriptUpdate) -> SearchResultResponse:
    result = update_search_result_transcript(job_id, result_id, payload.transcript_text)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Treffer wurde nicht gefunden.")
    return result


@api_router.get("/pages/{page_id}/image")
async def read_page_image(page_id: int) -> FileResponse:
    image_path = get_candidate_page_image_path(page_id)
    if image_path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Originalseite wurde nicht gefunden.")
    return FileResponse(image_path, media_type=mimetypes.guess_type(image_path.name)[0])


@api_router.patch("/settings", response_model=SettingsResponse)
async def update_settings(payload: SettingsUpdate) -> SettingsResponse:
    if payload.nara_api_key is not None:
        try:
            set_nara_api_key(payload.nara_api_key)
        except RuntimeError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc
    return build_settings_response()


@api_router.post("/settings/test-nara-key", response_model=ApiKeyTestResponse)
async def test_nara_key() -> ApiKeyTestResponse:
    api_key, source = get_nara_api_key()
    if not api_key:
        return ApiKeyTestResponse(
            ok=False,
            live_tested=False,
            message="NARA API-Schlüssel ist nicht eingerichtet.",
        )
    try:
        await NaraCatalogClient(api_key=api_key).test_key()
    except NaraClientError as exc:
        return ApiKeyTestResponse(
            ok=False,
            live_tested=True,
            message=str(exc),
            nara_api_usage=build_usage_response(get_nara_api_usage(api_key)),
        )
    return ApiKeyTestResponse(
        ok=True,
        live_tested=True,
        nara_api_usage=build_usage_response(get_nara_api_usage(api_key)),
        message=f"NARA API-Schlüssel ist gültig. Quelle: {source}.",
    )


@api_router.delete("/settings/nara-key", response_model=SettingsResponse)
async def remove_nara_key() -> SettingsResponse:
    try:
        delete_nara_api_key()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    return build_settings_response()


def build_settings_response() -> SettingsResponse:
    settings = get_settings()
    paths = get_local_paths()
    key_status = get_nara_api_key_status()
    api_key, _ = get_nara_api_key()
    return SettingsResponse(
        mock_mode=settings.mock_mode,
        data_dir=str(paths.root),
        cache_dir=str(paths.cache_dir),
        database_path=str(paths.database_file),
        nara_api_key_configured=key_status.configured,
        nara_api_key_source=key_status.source,
        nara_api_usage=build_usage_response(get_nara_api_usage(api_key)),
    )


def build_usage_response(usage: NaraApiUsage) -> NaraApiUsageResponse:
    return NaraApiUsageResponse(
        request_count=usage.request_count,
        request_limit=usage.request_limit,
        percent_used=usage.percent_used,
        period=usage.period,
        reset_at=usage.reset_at,
        counted_locally=usage.counted_locally,
    )
