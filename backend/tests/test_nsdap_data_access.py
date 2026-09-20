import json

from naratrace.nsdap.frame_search import search_frames
from naratrace.nsdap.manifest import parse_manifest
from naratrace.nsdap.roll_loader import parse_roll_document, roll_json_url
from naratrace.processing.nsdap_candidates import number_matches


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
