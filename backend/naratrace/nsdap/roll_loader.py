from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from naratrace import __version__
from naratrace.core.paths import ensure_local_directories
from naratrace.nsdap.manifest import NsdapDataError
from naratrace.nsdap.models import NsdapFrame, NsdapRoll

S3_HTTP_BASE = "https://nara-nsdap.s3.amazonaws.com"


class NsdapRollLoader:
    def __init__(self, timeout_seconds: float = 60.0) -> None:
        self.timeout = httpx.Timeout(timeout_seconds, connect=10.0)

    async def load_frames(self, roll: NsdapRoll, refresh: bool = False) -> list[NsdapFrame]:
        cache_path = get_roll_cache_path(roll)
        if cache_path.exists() and not refresh:
            try:
                return parse_roll_document(cache_path.read_bytes(), roll)
            except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError):
                pass
        url = roll_json_url(roll)
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
                headers={"User-Agent": f"NARATrace/{__version__} local historical research client"},
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise NsdapDataError(f"Roll-JSON für {roll.collection} {roll.box} ist nicht erreichbar: {exc}") from exc
        try:
            frames = parse_roll_document(response.content, roll)
        except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
            raise NsdapDataError(f"Roll-JSON für {roll.collection} {roll.box} ist beschädigt.") from exc
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(response.content)
        return frames


def roll_json_url(roll: NsdapRoll) -> str:
    path = roll.s3_path.removeprefix("s3://nara-nsdap/").strip("/")
    if not path or path.startswith("s3://"):
        raise ValueError("NSDAP-Rollenpfad gehört nicht zum erwarteten öffentlichen NARA-Bucket.")
    return f"{S3_HTTP_BASE}/{path}/{roll.naid}.json"


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
