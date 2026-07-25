from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from naratrace import __version__


class NaraClientError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class NaraRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    naId: int | str | None = None
    title: str | None = None
    description: str | None = None
    recordGroupNumber: str | int | None = None
    localIdentifier: str | None = None
    levelOfDescription: str | None = None
    digitalObjects: list[dict[str, Any]] = Field(default_factory=list)
    ancestors: list[dict[str, Any]] = Field(default_factory=list)
    useRestriction: dict[str, Any] | str | None = None
    accessRestriction: dict[str, Any] | str | None = None


@dataclass(frozen=True)
class NaraSearchItem:
    record: NaraRecord
    raw: dict[str, Any]


@dataclass(frozen=True)
class NaraSearchResponse:
    items: list[NaraSearchItem]
    total: int | None
    raw: dict[str, Any]


class NaraCatalogClient:
    base_url = "https://catalog.archives.gov/api/v2"

    def __init__(self, api_key: str, timeout_seconds: float = 20.0) -> None:
        self.api_key = api_key
        self.timeout = httpx.Timeout(timeout_seconds, connect=10.0)
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": f"NARATrace/{__version__} local historical research client",
            "x-api-key": api_key,
        }

    async def search_records(self, params: dict[str, Any]) -> NaraSearchResponse:
        response = await self._get("/records/search", params=params)
        return self._parse_search_response(response)

    async def test_key(self) -> None:
        await self.search_records({"q": "constitution", "limit": 1, "abbreviated": "true"})

    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(
                    base_url=self.base_url,
                    headers=self.headers,
                    timeout=self.timeout,
                    follow_redirects=False,
                ) as client:
                    response = await client.get(path, params=clean_params(params))
                return self._handle_response(response)
            except NaraClientError:
                raise
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt < 2:
                    await asyncio.sleep(0.5 * (2**attempt))
        raise NaraClientError(f"NARA Catalog API ist nicht erreichbar: {last_error}")

    def _handle_response(self, response: httpx.Response) -> dict[str, Any]:
        if response.status_code == 429:
            raise NaraClientError("NARA Catalog API meldet Rate-Limit. Bitte später erneut versuchen.", 429)
        if response.status_code in {401, 403}:
            raise NaraClientError("NARA API-Schlüssel wurde abgelehnt. Bitte Schlüssel in den Einstellungen prüfen.", response.status_code)
        if response.status_code >= 500:
            raise NaraClientError("NARA Catalog API meldet einen temporären Serverfehler.", response.status_code)
        if response.status_code >= 400:
            raise NaraClientError(f"NARA Catalog API meldet HTTP {response.status_code}.", response.status_code)

        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type.lower():
            raise NaraClientError(
                "NARA Catalog API lieferte keine JSON-Antwort. Wahrscheinlich fehlt ein gültiger API-Schlüssel."
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise NaraClientError("NARA Catalog API lieferte beschädigtes JSON.") from exc
        if not isinstance(data, dict):
            raise NaraClientError("NARA Catalog API lieferte ein unerwartetes Antwortformat.")
        return data

    def _parse_search_response(self, data: dict[str, Any]) -> NaraSearchResponse:
        hits = extract_hits(data)
        total = extract_total(data)
        items: list[NaraSearchItem] = []
        for hit in hits:
            record_data = extract_record(hit)
            if not record_data:
                continue
            try:
                record = NaraRecord.model_validate(record_data)
            except ValidationError:
                continue
            items.append(NaraSearchItem(record=record, raw=hit if isinstance(hit, dict) else record_data))
        return NaraSearchResponse(items=items, total=total, raw=data)


def clean_params(params: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in params.items() if value not in (None, "", [])}


def extract_hits(data: dict[str, Any]) -> list[Any]:
    for path in (
        ("body", "hits", "hits"),
        ("hits", "hits"),
        ("body", "hits"),
        ("records",),
        ("results",),
    ):
        value: Any = data
        for segment in path:
            if not isinstance(value, dict) or segment not in value:
                value = None
                break
            value = value[segment]
        if isinstance(value, list):
            return value
    return []


def extract_total(data: dict[str, Any]) -> int | None:
    candidates: list[Any] = [
        data.get("total"),
        data.get("totalCount"),
        data.get("count"),
    ]
    body = data.get("body")
    if isinstance(body, dict):
        hits = body.get("hits")
        if isinstance(hits, dict):
            candidates.append(hits.get("total"))
    hits = data.get("hits")
    if isinstance(hits, dict):
        candidates.append(hits.get("total"))
    for candidate in candidates:
        if isinstance(candidate, int):
            return candidate
        if isinstance(candidate, dict) and isinstance(candidate.get("value"), int):
            return candidate["value"]
    return None


def extract_record(hit: Any) -> dict[str, Any] | None:
    if not isinstance(hit, dict):
        return None
    source = hit.get("_source")
    if isinstance(source, dict):
        record = source.get("record")
        if isinstance(record, dict):
            return record
        return source
    record = hit.get("record")
    if isinstance(record, dict):
        return record
    if "naId" in hit or "title" in hit:
        return hit
    return None
