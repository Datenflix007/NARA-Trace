from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class NsdapRoll:
    """One entry from NARA's official ``docs/nsdap.json`` manifest."""

    naid: str
    collection: str
    box: str
    title: str
    s3_path: str
    range_start: str | None
    range_end: str | None

    @classmethod
    def from_manifest_entry(cls, entry: dict[str, Any]) -> "NsdapRoll":
        naid = str(entry.get("id") or "").strip()
        collection = str(entry.get("agency") or "").strip().upper()
        box = str(entry.get("box") or "").strip().upper()
        title = str(entry.get("title") or "").strip()
        s3_path = str(entry.get("s3") or "").strip()
        if not all((naid, collection, box, title, s3_path)):
            raise ValueError("NSDAP-Manifest enthält eine unvollständige Rollenbeschreibung.")
        start, end = split_roll_range(title)
        return cls(
            naid=naid,
            collection=collection,
            box=box,
            title=title,
            s3_path=s3_path,
            range_start=start,
            range_end=end,
        )


@dataclass(frozen=True)
class NsdapFrame:
    """A frame in a roll JSON, retaining the exact official object metadata."""

    roll: NsdapRoll
    frame_number: int
    object_id: str | None
    object_filename: str | None
    object_url: str | None
    extracted_text: str | None
    raw: dict[str, Any]


@dataclass(frozen=True)
class FrameMatch:
    frame: NsdapFrame
    retrieval_score: float
    matched_variants: tuple[str, ...]
    strategy: str


def split_roll_range(title: str) -> tuple[str | None, str | None]:
    """Split a manifest title such as ``Schulze, Max - Schulze, Paul``."""
    if " - " not in title:
        return None, None
    start, end = (part.strip() for part in title.split(" - ", 1))
    return start or None, end or None
