from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx

from naratrace import __version__
from naratrace.core.paths import ensure_local_directories
from naratrace.nsdap.manifest import NsdapDataError
from naratrace.nsdap.models import NsdapFrame, NsdapRoll

# The Registry of Open Data lists the NSDAP bucket in us-east-2.  The
# region-specific endpoint avoids relying on a legacy global S3 redirect.
S3_HTTP_BASE = "https://nara-nsdap.s3.us-east-2.amazonaws.com"
DEFAULT_RETRY_ATTEMPTS = 4
DEFAULT_RETRY_DELAY_SECONDS = 0.5


class NsdapRollLoader:
    def __init__(
        self,
        timeout_seconds: float = 60.0,
        *,
        reuse_connections: bool = False,
        retry_attempts: int = DEFAULT_RETRY_ATTEMPTS,
        retry_delay_seconds: float = DEFAULT_RETRY_DELAY_SECONDS,
    ) -> None:
        self.timeout = httpx.Timeout(timeout_seconds, connect=10.0)
        self.reuse_connections = reuse_connections
        self.retry_attempts = max(1, retry_attempts)
        self.retry_delay_seconds = max(0.0, retry_delay_seconds)
        self._client: httpx.AsyncClient | None = None

    async def load_frames(self, roll: NsdapRoll, refresh: bool = False) -> list[NsdapFrame]:
        cache_path = get_roll_cache_path(roll)
        if cache_path.exists() and not refresh:
            try:
                return parse_roll_document(cache_path.read_bytes(), roll)
            except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError):
                pass
        url = roll_json_url(roll)
        response = await self._get_response(url, roll)
        try:
            frames = parse_roll_document(response.content, roll)
        except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
            raise NsdapDataError(f"Roll-JSON für {roll.collection} {roll.box} ist beschädigt.") from exc
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(response.content)
        return frames

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _get_response(self, url: str, roll: NsdapRoll) -> httpx.Response:
        last_error: httpx.HTTPError | None = None
        for attempt in range(self.retry_attempts):
            try:
                if self.reuse_connections:
                    client = self._shared_client()
                    response = await client.get(url)
                else:
                    async with self._new_client() as client:
                        response = await client.get(url)
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as exc:
                # A 404 is a real upstream gap (such as a manifest entry whose
                # object has not been published), not a condition a retry can
                # repair. Temporary S3/server responses are retried below.
                if not retryable_status(exc.response.status_code):
                    raise NsdapDataError(
                        f"Roll-JSON für {roll.collection} {roll.box} ist nicht erreichbar: {exc}"
                    ) from exc
                last_error = exc
            except httpx.RequestError as exc:
                last_error = exc

            if attempt < self.retry_attempts - 1:
                await asyncio.sleep(self.retry_delay_seconds * (2**attempt))

        assert last_error is not None
        raise NsdapDataError(
            f"Roll-JSON für {roll.collection} {roll.box} ist nach {self.retry_attempts} Versuchen nicht erreichbar: {last_error}"
        ) from last_error

    def _shared_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = self._new_client()
        return self._client

    def _new_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            headers={"User-Agent": f"NARATrace/{__version__} local historical research client"},
        )


def roll_json_url(roll: NsdapRoll) -> str:
    path = roll.s3_path.removeprefix("s3://nara-nsdap/").strip("/")
    if not path or path.startswith("s3://"):
        raise ValueError("NSDAP-Rollenpfad gehört nicht zum erwarteten öffentlichen NARA-Bucket.")
    return f"{S3_HTTP_BASE}/{path}/{roll.naid}.json"


def retryable_status(status_code: int) -> bool:
    return status_code in {408, 429} or 500 <= status_code <= 599


def get_roll_cache_path(roll: NsdapRoll) -> Path:
    filename = f"{roll.collection}-{roll.box}-{roll.naid}.json"
    return ensure_local_directories().cache_dir / "nsdap" / "rolls" / filename


def parse_roll_document(content: bytes | str | dict[str, Any], roll: NsdapRoll) -> list[NsdapFrame]:
    if isinstance(content, dict):
        data = content
    else:
        decoded = content.decode("utf-8") if isinstance(content, bytes) else content
        data = json.loads(decoded)
    source = data.get("_source") if isinstance(data, dict) else None
    record = source.get("record") if isinstance(source, dict) else None
    objects = record.get("digitalObjects") if isinstance(record, dict) else None
    if not isinstance(objects, list):
        raise ValueError("Roll-JSON enthält keine Liste digitaler Objekte.")
    frames: list[NsdapFrame] = []
    for position, item in enumerate(objects, start=1):
        if not isinstance(item, dict):
            continue
        frames.append(
            NsdapFrame(
                roll=roll,
                frame_number=position,
                object_id=string_value(item.get("objectId")),
                object_filename=string_value(item.get("objectFilename")),
                object_url=string_value(item.get("objectUrl")),
                extracted_text=string_value(item.get("extractedText")),
                raw=item,
            )
        )
    if not frames:
        raise ValueError("Roll-JSON enthält keine verwendbaren digitalen Objekte.")
    return frames


def string_value(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
