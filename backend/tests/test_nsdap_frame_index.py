from __future__ import annotations

import pytest

from naratrace.nsdap.frame_index import NsdapFrameIndex, extract_number_terms
from naratrace.nsdap.models import NsdapFrame, NsdapRoll


def make_roll(naid: str, collection: str, box: str) -> NsdapRoll:
    return NsdapRoll(
        naid=naid,
        collection=collection,
        box=box,
        title=f"{box} title",
        s3_path=f"s3://nara-nsdap/A3340-{collection}/A3340-{collection}-{box}",
        range_start=None,
        range_end=None,
    )


class FakeRollLoader:
    def __init__(self, frames_by_naid: dict[str, list[NsdapFrame]]) -> None:
        self.frames_by_naid = frames_by_naid
        self.calls: list[str] = []

    async def load_frames(self, roll: NsdapRoll, refresh: bool = False) -> list[NsdapFrame]:
        self.calls.append(roll.naid)
        return self.frames_by_naid[roll.naid]


@pytest.mark.asyncio
async def test_frame_index_builds_and_searches_all_mfkl_and_mfok_rolls(tmp_path):
    mfkl_first = make_roll("roll-1", "MFKL", "R0001")
    mfkl_later = make_roll("roll-2", "MFKL", "R0999")
    mfok = make_roll("roll-3", "MFOK", "R0420")
    ignored = make_roll("roll-4", "OTHER", "R9999")
    frames_by_naid = {
        "roll-1": [
            NsdapFrame(mfkl_first, 1, "object-1", "one.tif", "https://example.invalid/one.tif", "Name: Anna Beispiel", {}),
        ],
        "roll-2": [
            NsdapFrame(
                mfkl_later,
                2947,
                "object-2947",
                "target.tif",
                "https://example.invalid/target.tif",
                "Name: Paul Schultze-Naumburg Mitgl. No. 347 541",
                {},
            ),
        ],
        "roll-3": [
            NsdapFrame(mfok, 4, "object-4", "place.tif", "https://example.invalid/place.tif", "Ortsgruppe Naumburg", {}),
        ],
    }
    loader = FakeRollLoader(frames_by_naid)
    index = NsdapFrameIndex(tmp_path / "nsdap-frames.sqlite3")

    result = await index.build_all([mfkl_first, mfkl_later, mfok, ignored], loader=loader, concurrency=2)

    assert result.complete is True
    assert result.indexed_rolls == 3
    assert set(loader.calls) == {"roll-1", "roll-2", "roll-3"}
    assert index.index_status()[0] == 3

    name_hits = index.search_frames([mfkl_first, mfkl_later, mfok, ignored], surname="Schultze-Naumburg", membership_number=None)
    number_hits = index.search_frames([mfkl_first, mfkl_later, mfok, ignored], surname="unauffindbar", membership_number="347541")

    assert [(frame.roll.naid, frame.frame_number) for frame in name_hits] == [("roll-2", 2947)]
    assert [(frame.roll.naid, frame.frame_number) for frame in number_hits] == [("roll-2", 2947)]


@pytest.mark.asyncio
async def test_frame_index_resumes_without_downloading_indexed_rolls_again(tmp_path):
    roll = make_roll("roll-1", "MFKL", "R0001")
    frame = NsdapFrame(roll, 1, "object-1", "one.tif", "https://example.invalid/one.tif", "Name: Anna Beispiel", {})
    loader = FakeRollLoader({roll.naid: [frame]})
    index = NsdapFrameIndex(tmp_path / "nsdap-frames.sqlite3")

    await index.build_all([roll], loader=loader)
    second = await index.build_all([roll], loader=loader)

    assert loader.calls == ["roll-1"]
    assert second.indexed_rolls == 0
    assert second.skipped_rolls == 1


def test_number_term_extraction_keeps_fields_separate():
    assert extract_number_terms("Mitgl. No. 347 541, andere Nr. 12-345") == ["347541", "12345"]
