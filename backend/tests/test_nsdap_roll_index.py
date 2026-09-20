from naratrace.nsdap.models import NsdapRoll
from naratrace.nsdap.roll_index import RollIndex, normalize_roll_key


def roll(box: str, title: str, collection: str = "MFKL") -> NsdapRoll:
    start, end = title.split(" - ", 1)
    return NsdapRoll(
        naid=f"naid-{collection}-{box}",
        collection=collection,
        box=box,
        title=title,
        s3_path=f"s3://nara-nsdap/A3340-{collection}/A3340-{collection}-{box}",
        range_start=start,
        range_end=end,
    )


def test_select_for_name_uses_range_then_adjacent_rolls():
    index = RollIndex(
        [
            roll("R0012", "Schulz, Erich - Schulze, Max"),
            roll("R0013", "Schulze, Max - Schulze, Paul"),
            roll("R0014", "Schultze, Paul - Schultze, Robert"),
            roll("R0015", "Schultze, Robert - Schulzendorf, Wilhelm"),
        ]
    )

    selected = index.select_for_name("Schultze-Naumburg", collections=("MFKL",))

    assert [item.box for item in selected] == ["R0012", "R0013", "R0014"]


def test_collection_selection_is_separate_and_bounded():
    index = RollIndex(
        [
            roll("R0001", "Meyer, A - Müller, A", "MFKL"),
            roll("R0002", "Müller, A - Müller, Z", "MFKL"),
            roll("R0001", "Meyer, A - Müller, A", "MFOK"),
            roll("R0002", "Müller, A - Müller, Z", "MFOK"),
        ]
    )

    selected = index.select_for_name("Müller", collections=("MFOK",), neighbor_count=0)

    assert [(item.collection, item.box) for item in selected] == [("MFOK", "R0001")]


def test_roll_key_is_accent_and_punctuation_insensitive():
    assert normalize_roll_key("Schultze-Naumburg") == "schulze naumburg"
    assert normalize_roll_key("von Müller") == "von muller"
