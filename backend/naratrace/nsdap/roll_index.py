from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

from rapidfuzz.fuzz import ratio

from naratrace.nsdap.models import NsdapRoll


def normalize_roll_key(value: str) -> str:
    """Stable, accent-insensitive sort key for manifest ranges and surname input."""
    value = unicodedata.normalize("NFKD", value).casefold().replace("ß", "ss")
    value = "".join(char for char in value if not unicodedata.combining(char))
    # ``tz``/``z`` is a common spelling/OCR variation in German surnames.
    # Folding it only for roll-range lookup keeps Schultze/Schulze close while
    # the original name and all weighted variants remain available for ranking.
    value = value.replace("tz", "z")
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


class RollIndex:
    """Select a bounded, explainable set of candidate rolls from the manifest."""

    def __init__(self, rolls: Iterable[NsdapRoll]) -> None:
        self._by_collection: dict[str, list[NsdapRoll]] = {}
        for roll in rolls:
            self._by_collection.setdefault(roll.collection, []).append(roll)

    @property
    def collections(self) -> tuple[str, ...]:
        return tuple(self._by_collection)

    def select_for_name(
        self,
        surname: str,
        collections: Iterable[str] = ("MFKL", "MFOK"),
        neighbor_count: int = 1,
    ) -> list[NsdapRoll]:
        """Return primary range hits plus adjacent rolls in each requested collection.

        The manifest order is preserved because it is NARA's published roll
        order. Adjacent rolls protect range boundaries and OCR/name spelling
        uncertainty without expanding to a corpus-wide search.
        """
        key = normalize_roll_key(surname)
        if not key:
            return []
        selected: list[NsdapRoll] = []
        for collection in collections:
            rolls = self._by_collection.get(collection.upper(), [])
            primary_indexes = [index for index, roll in enumerate(rolls) if roll_contains_key(roll, key)]
            if len(primary_indexes) > 1:
                # MFKL contains more than one alphabetic run. Keep the most
                # textually proximate range as primary; neighbor expansion
                # then preserves the boundary without loading every matching
                # surname run.
                primary_indexes = [max(primary_indexes, key=lambda index: roll_proximity(rolls[index], key))]
            if not primary_indexes:
                primary_indexes = nearest_roll_indexes(rolls, key)
            for primary in primary_indexes:
                first = max(0, primary - max(0, neighbor_count))
                last = min(len(rolls), primary + max(0, neighbor_count) + 1)
                selected.extend(rolls[first:last])
        return dedupe_rolls(selected)


def roll_contains_key(roll: NsdapRoll, key: str) -> bool:
    start = normalize_roll_key(roll.range_start or "")
    end = normalize_roll_key(roll.range_end or "")
    if not (start and end):
        return False
    return start <= key <= end


def roll_proximity(roll: NsdapRoll, key: str) -> float:
    return max(ratio(key, normalize_roll_key(roll.range_start or "")), ratio(key, normalize_roll_key(roll.range_end or "")))


def nearest_roll_indexes(rolls: list[NsdapRoll], key: str) -> list[int]:
    bounded = [
        (index, normalize_roll_key(roll.range_start or ""), normalize_roll_key(roll.range_end or ""))
        for index, roll in enumerate(rolls)
        if roll.range_start and roll.range_end
    ]
    if not bounded:
        return []
    for index, start, _ in bounded:
        if key < start:
            return [max(0, index - 1)]
    return [bounded[-1][0]]


def dedupe_rolls(rolls: Iterable[NsdapRoll]) -> list[NsdapRoll]:
    result: list[NsdapRoll] = []
    seen: set[tuple[str, str, str]] = set()
    for roll in rolls:
        identifier = (roll.collection, roll.box, roll.naid)
        if identifier not in seen:
            seen.add(identifier)
            result.append(roll)
    return result
