import json

import pytest

from naratrace.api.schemas import SearchRequest
from naratrace.nsdap.frame_search import search_frames
from naratrace.nsdap.manifest import parse_manifest
from naratrace.nsdap.models import NsdapFrame
from naratrace.nsdap.roll_loader import S3_HTTP_BASE, parse_roll_document, roll_json_url
from naratrace.processing.nsdap_candidates import number_matches
from naratrace.processing.nsdap_candidates import retrieve_nsdap_candidates


def test_manifest_parses_official_field_shape_and_preserves_provenance():
    rolls = parse_manifest(
        [
            {
                "id": "593495034",
                "agency": "MFKL",
                "box": "R0014",
                "title": "Schultze, Paul - Schultze, Robert",
                "s3": "s3://nara-nsdap/A3340-MFKL/A3340-MFKL-R0014",
            }
        ]
    )

    assert rolls[0].naid == "593495034"
    assert rolls[0].range_start == "Schultze, Paul"
    assert roll_json_url(rolls[0]).startswith(S3_HTTP_BASE)
    assert roll_json_url(rolls[0]).endswith("A3340-MFKL-R0014/593495034.json")


def test_roll_document_keeps_object_filename_text_and_original_url():
    roll = parse_manifest(
        [
            {
                "id": "593495034",
                "agency": "MFKL",
                "box": "R0014",
                "title": "Schultze, Paul - Schultze, Robert",
                "s3": "s3://nara-nsdap/A3340-MFKL/A3340-MFKL-R0014",
            }
        ]
    )[0]
    document = {
        "_source": {
            "record": {
                "digitalObjects": [
                    {
                        "objectId": "593495044",
                        "objectFilename": "A3340-MFKL-R0014-00010.tif",
                        "objectUrl": "https://example.invalid/A3340-MFKL-R0014-00010.tif",
                        "extractedText": "Name: Schultze Paul",
                    }
                ]
            }
        }
    }

    frames = parse_roll_document(json.dumps(document), roll)

    assert frames[0].frame_number == 1
    assert frames[0].object_filename == "A3340-MFKL-R0014-00010.tif"
    assert frames[0].extracted_text == "Name: Schultze Paul"
    assert frames[0].object_url == "https://example.invalid/A3340-MFKL-R0014-00010.tif"


def test_frame_retrieval_records_strategy_without_claiming_identity():
    roll = parse_manifest(
        [
            {
                "id": "1",
                "agency": "MFKL",
                "box": "R0001",
                "title": "Schultze, A - Schultze, Z",
                "s3": "s3://nara-nsdap/A3340-MFKL/A3340-MFKL-R0001",
            }
        ]
    )[0]
    frames = parse_roll_document(
        {"_source": {"record": {"digitalObjects": [{"objectFilename": "001.tif", "extractedText": "Schultze Paul"}]} }},
        roll,
    )

    matches = search_frames(frames, first_name="Paul", last_name="Schultze-Naumburg")

    assert matches[0].strategy in {"surname_exact_or_normalized", "surname_fuzzy"}
    assert matches[0].retrieval_score >= 70


def test_membership_number_retrieval_finds_the_concrete_card_frame():
    roll = parse_manifest(
        [
            {
                "id": "593492018",
                "agency": "MFKL",
                "box": "R0013",
                "title": "Schultze, H - Schultze, Q",
                "s3": "s3://nara-nsdap/A3340-MFKL/A3340-MFKL-R0013",
            }
        ]
    )[0]
    frames = parse_roll_document(
        {
            "_source": {
                "record": {
                    "digitalObjects": [
                        {
                            "objectFilename": "A3340-MFKL-R0013-02947.tif",
                            "extractedText": "Mitgl. No. 347 541 Aufnahme: 1.11.30",
                        }
                    ]
                }
            }
        },
        roll,
    )

    candidates = number_matches(roll, frames, "347541")

    assert len(candidates) == 1
    assert candidates[0].frame.frame_number == 1
    assert candidates[0].frame_match.strategy == "membership_number_exact"
    assert candidates[0].frame_match.retrieval_score == 100.0


@pytest.mark.asyncio
async def test_retrieval_passes_every_mfkl_and_mfok_roll_to_the_corpus_index(monkeypatch):
    rolls = parse_manifest(
        [
            {"id": "1", "agency": "MFKL", "box": "R0001", "title": "A - B", "s3": "s3://nara-nsdap/MFKL/R0001"},
            {"id": "2", "agency": "MFKL", "box": "R0013", "title": "C - D", "s3": "s3://nara-nsdap/MFKL/R0013"},
            {"id": "3", "agency": "MFOK", "box": "R0001", "title": "E - F", "s3": "s3://nara-nsdap/MFOK/R0001"},
            {"id": "4", "agency": "OTHER", "box": "R0001", "title": "G - H", "s3": "s3://nara-nsdap/OTHER/R0001"},
        ]
    )
    frame = NsdapFrame(
        roll=rolls[0],
        frame_number=7,
        object_id="object-7",
        object_filename="frame-7.tif",
        object_url="https://example.invalid/frame-7.tif",
        extracted_text="Paul Schultze-Naumburg",
        raw={},
    )

    class FakeManifestClient:
        async def load_rolls(self):
            return rolls

    class FakeIndex:
        received_rolls = []

        async def build_all(self, received_rolls):
            self.received_rolls = list(received_rolls)
            return type("Build", (), {"failed_rolls": 0, "warnings": ()})()

        def index_status(self):
            return 3, "1"

        def search_frames(self, received_rolls, *, surname, membership_number):
            assert list(received_rolls) == self.received_rolls
            assert surname == "Schultze-Naumburg"
            return [frame]

        def card_context_frames(self, received_roll, received_frame, *, surname, membership_number):
            assert received_roll == frame.roll
            assert received_frame == frame
            assert surname == "Schultze-Naumburg"
            return [frame]

    fake_index = FakeIndex()
    monkeypatch.setattr("naratrace.processing.nsdap_candidates.NsdapManifestClient", FakeManifestClient)
    monkeypatch.setattr("naratrace.processing.nsdap_candidates.NsdapFrameIndex", lambda: fake_index)

    candidates, warnings = await retrieve_nsdap_candidates(
        SearchRequest(first_name="Paul", last_name="Schultze-Naumburg")
    )

    assert [(roll.collection, roll.box) for roll in fake_index.received_rolls] == [
        ("MFKL", "R0001"),
        ("MFKL", "R0013"),
        ("MFOK", "R0001"),
    ]
    assert candidates[0].frame.frame_number == 7
    assert "Gesamtindex" in " ".join(warnings)
