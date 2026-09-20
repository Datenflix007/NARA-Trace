from __future__ import annotations

import asyncio
import re
import sqlite3
from collections.abc import Awaitable, Callable, Iterable
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from naratrace.core.paths import ensure_local_directories
from naratrace.matching.name_normalizer import NameNormalizer
from naratrace.nsdap.models import NsdapFrame, NsdapRoll
from naratrace.nsdap.roll_loader import NsdapRollLoader

INDEX_FILE_NAME = "nsdap-frames.sqlite3"
INDEX_VERSION = "1"


@dataclass(frozen=True)
class NsdapIndexBuildResult:
    indexed_rolls: int
    skipped_rolls: int
    failed_rolls: int
    total_rolls: int
    warnings: tuple[str, ...]

    @property
    def complete(self) -> bool:
        return self.indexed_rolls + self.skipped_rolls == self.total_rolls and self.failed_rolls == 0


ProgressCallback = Callable[[int, int], Awaitable[None] | None]


class NsdapFrameIndex:
    """Persistent FTS5 index over every locally retrieved A3340 roll frame.

    The index stores NARA Extracted Text and frame provenance, never original
    images. A first corpus build reads every MFKL and MFOK roll JSON once;
    subsequent person searches query SQLite FTS5 instead of narrowing a search
    to a known roll or downloading the corpus again.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or get_frame_index_path()

    async def build_all(
        self,
        rolls: Iterable[NsdapRoll],
        *,
        loader: NsdapRollLoader | None = None,
        refresh: bool = False,
        concurrency: int = 8,
        on_progress: ProgressCallback | None = None,
    ) -> NsdapIndexBuildResult:
        """Index all supplied rolls with bounded network concurrency.

        A failed roll is recorded as a warning and does not make the completed
        part of the corpus disappear. Calling this again resumes missing rolls.
        """
        selected_rolls = [roll for roll in rolls if roll.collection in {"MFKL", "MFOK"}]
        self._ensure_schema()
        if refresh or self._stored_version() != INDEX_VERSION:
            self._reset_index()
            known_rolls: set[str] = set()
        else:
            known_rolls = self._indexed_roll_naids()
        pending = [roll for roll in selected_rolls if roll.naid not in known_rolls]
        if not pending:
            return NsdapIndexBuildResult(0, len(selected_rolls), 0, len(selected_rolls), ())

        active_loader = loader or NsdapRollLoader()
        semaphore = asyncio.Semaphore(max(1, concurrency))
        completed = 0
        indexed = 0
        failed = 0
        warnings: list[str] = []
        lock = asyncio.Lock()

        async def index_one(roll: NsdapRoll) -> None:
            nonlocal completed, indexed, failed
            try:
                async with semaphore:
                    frames = await active_loader.load_frames(roll, refresh=refresh)
                self._replace_roll(roll, frames)
                outcome_warning: str | None = None
                outcome_indexed = True
            except Exception as exc:  # individual archival files must not abort a corpus build
                outcome_warning = f"{roll.collection} {roll.box}: {exc}"
                outcome_indexed = False
            async with lock:
                completed += 1
                if outcome_indexed:
                    indexed += 1
                else:
                    failed += 1
                    warnings.append(outcome_warning or f"{roll.collection} {roll.box}: unbekannter Indexfehler")
                if on_progress is not None:
                    maybe_awaitable = on_progress(completed, len(pending))
                    if maybe_awaitable is not None:
                        await maybe_awaitable

        await asyncio.gather(*(index_one(roll) for roll in pending))
        return NsdapIndexBuildResult(indexed, len(selected_rolls) - len(pending), failed, len(selected_rolls), tuple(warnings))

    def search_frames(self, rolls: Iterable[NsdapRoll], *, surname: str, membership_number: str | None, limit: int = 600) -> list[NsdapFrame]:
        """Return corpus-wide FTS candidates; scoring happens in frame_search."""
        roll_by_naid = {roll.naid: roll for roll in rolls}
        queries = build_fts_queries(surname, membership_number)
        if not queries:
            return []
        self._ensure_schema()
        rows: dict[str, sqlite3.Row] = {}
        with self._connection() as connection:
            for query in queries:
                for row in connection.execute(
                    "SELECT frame_key, roll_naid, frame_number, object_id, object_filename, object_url, extracted_text "
                    "FROM nsdap_frames_fts WHERE nsdap_frames_fts MATCH ? LIMIT ?",
                    (query, max(1, limit)),
                ):
                    rows[str(row["frame_key"])] = row
        frames: list[NsdapFrame] = []
        for row in rows.values():
            roll = roll_by_naid.get(str(row["roll_naid"]))
            if roll is None:
                continue
            frames.append(
                NsdapFrame(
                    roll=roll,
                    frame_number=int(row["frame_number"]),
                    object_id=optional_string(row["object_id"]),
                    object_filename=optional_string(row["object_filename"]),
                    object_url=optional_string(row["object_url"]),
                    extracted_text=optional_string(row["extracted_text"]),
                    raw={
                        "objectId": optional_string(row["object_id"]),
                        "objectFilename": optional_string(row["object_filename"]),
                        "objectUrl": optional_string(row["object_url"]),
                        "extractedText": optional_string(row["extracted_text"]),
                    },
                )
            )
        return frames

    def index_status(self) -> tuple[int, str | None]:
        self._ensure_schema()
        with self._connection() as connection:
            count = int(connection.execute("SELECT COUNT(*) FROM nsdap_indexed_rolls").fetchone()[0])
            version_row = connection.execute("SELECT value FROM nsdap_index_metadata WHERE key = 'version'").fetchone()
        return count, str(version_row[0]) if version_row else None

    def _stored_version(self) -> str | None:
        with self._connection() as connection:
            row = connection.execute("SELECT value FROM nsdap_index_metadata WHERE key = 'version'").fetchone()
        return str(row[0]) if row else None

    def _reset_index(self) -> None:
        with self._connection() as connection:
            connection.execute("DELETE FROM nsdap_frames_fts")
            connection.execute("DELETE FROM nsdap_indexed_rolls")
            connection.execute(
                "INSERT INTO nsdap_index_metadata (key, value) VALUES ('version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (INDEX_VERSION,),
            )
            connection.commit()

    def _indexed_roll_naids(self) -> set[str]:
        with self._connection() as connection:
            return {str(row[0]) for row in connection.execute("SELECT roll_naid FROM nsdap_indexed_rolls")}

    def _replace_roll(self, roll: NsdapRoll, frames: list[NsdapFrame]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connection() as connection:
            connection.execute("DELETE FROM nsdap_frames_fts WHERE roll_naid = ?", (roll.naid,))
            connection.execute("DELETE FROM nsdap_indexed_rolls WHERE roll_naid = ?", (roll.naid,))
            connection.executemany(
                "INSERT INTO nsdap_frames_fts "
                "(frame_key, roll_naid, collection, box, frame_number, object_id, object_filename, object_url, extracted_text, normalized_text, number_terms) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        frame_key(roll.naid, frame.frame_number),
                        roll.naid,
                        roll.collection,
                        roll.box,
                        frame.frame_number,
                        frame.object_id or "",
                        frame.object_filename or "",
                        frame.object_url or "",
                        frame.extracted_text or "",
                        NameNormalizer().normalize(frame.extracted_text or ""),
                        " ".join(extract_number_terms(frame.extracted_text or "")),
                    )
                    for frame in frames
                ],
            )
            connection.execute(
                "INSERT INTO nsdap_indexed_rolls (roll_naid, collection, box, indexed_at) VALUES (?, ?, ?, ?)",
                (roll.naid, roll.collection, roll.box, now),
            )
            connection.commit()

    def _ensure_schema(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS nsdap_index_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS nsdap_indexed_rolls ("
                "roll_naid TEXT PRIMARY KEY, collection TEXT NOT NULL, box TEXT NOT NULL, indexed_at TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS nsdap_frames_fts USING fts5("
                "frame_key UNINDEXED, roll_naid UNINDEXED, collection UNINDEXED, box UNINDEXED, frame_number UNINDEXED, "
                "object_id UNINDEXED, object_filename UNINDEXED, object_url UNINDEXED, extracted_text UNINDEXED, "
                "normalized_text, number_terms)"
            )
            connection.execute("INSERT OR IGNORE INTO nsdap_index_metadata (key, value) VALUES ('version', ?)", (INDEX_VERSION,))
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            yield connection
        finally:
            connection.close()


def get_frame_index_path() -> Path:
    return ensure_local_directories().cache_dir / "nsdap" / INDEX_FILE_NAME


def build_fts_queries(surname: str, membership_number: str | None) -> list[str]:
    queries: list[str] = []
    digits = re.sub(r"\D+", "", membership_number or "")
    if len(digits) >= 4:
        queries.append(f"number_terms:{digits}")
    variants = NameNormalizer().variants(surname)
    seen: set[str] = set()
    for variant in variants:
        terms = re.findall(r"[a-z0-9]+", variant.normalized)
        if not terms:
            continue
        query = " AND ".join(f'normalized_text:{term}' for term in terms)
        if query not in seen:
            seen.add(query)
            queries.append(query)
    return queries


def extract_number_terms(text: str) -> list[str]:
    """Extract number-like fields without concatenating unrelated OCR tokens."""
    values: list[str] = []
    for raw in re.findall(r"(?<!\d)(?:\d[ .-]?){4,}\d(?!\d)", text):
        digits = re.sub(r"\D+", "", raw)
        if len(digits) >= 4 and digits not in values:
            values.append(digits)
    return values


def frame_key(roll_naid: str, frame_number: int) -> str:
    return f"{roll_naid}:{frame_number}"


def optional_string(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None
