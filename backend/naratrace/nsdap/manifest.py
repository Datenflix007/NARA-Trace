from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from naratrace import __version__
from naratrace.core.paths import ensure_local_directories
from naratrace.nsdap.models import NsdapRoll

# GitHub's contents endpoint is more reliable on restricted Windows networks
# than raw.githubusercontent.com. The explicit media type returns the file
# contents, not the API's base64 metadata envelope.
MANIFEST_URL = "https://api.github.com/repos/usnationalarchives/nsdap/contents/docs/nsdap.json"
MANIFEST_CACHE_NAME = "nsdap-manifest.json"


class NsdapDataError(RuntimeError):
    """A source or cache failure for the official NSDAP open dataset."""


class NsdapManifestClient:
    def __init__(self, manifest_url: str = MANIFEST_URL, timeout_seconds: float = 30.0) -> None:
        self.manifest_url = manifest_url
        self.timeout = httpx.Timeout(timeout_seconds, connect=10.0)

    async def load_rolls(self, refresh: bool = False) -> list[NsdapRoll]:
        cache_path = get_manifest_cache_path()
        if cache_path.exists() and not refresh:
            try:
                return parse_manifest(cache_path.read_bytes())
            except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError):
                # A corrupt cache is never treated as a valid empty index.
                pass

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
                headers={
                    "Accept": "application/vnd.github.raw+json",
                    "User-Agent": f"NARATrace/{__version__} local historical research client",
                },
            ) as client:
                response = await client.get(self.manifest_url)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise NsdapDataError(f"Offizielles NSDAP-Manifest ist nicht erreichbar: {exc}") from exc

        try:
            rolls = parse_manifest(response.content)
        except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
            raise NsdapDataError("Offizielles NSDAP-Manifest enthält kein erwartetes JSON.") from exc
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(response.content)
        return rolls


def get_manifest_cache_path() -> Path:
    return ensure_local_directories().cache_dir / "nsdap" / MANIFEST_CACHE_NAME


def parse_manifest(content: bytes | str | list[dict[str, Any]]) -> list[NsdapRoll]:
    if isinstance(content, list):
        data: Any = content
    else:
        decoded = content.decode("utf-8") if isinstance(content, bytes) else content
        data = json.loads(decoded)
    if not isinstance(data, list):
        raise ValueError("NSDAP-Manifest muss eine Liste von Rollen sein.")
    rolls = [NsdapRoll.from_manifest_entry(entry) for entry in data if isinstance(entry, dict)]
    if not rolls:
        raise ValueError("NSDAP-Manifest enthält keine gültigen Rollen.")
    return rolls
