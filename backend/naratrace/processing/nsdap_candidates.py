from __future__ import annotations

import re
from dataclasses import dataclass

from naratrace.api.schemas import SearchRequest
from naratrace.nsdap.frame_search import search_frames
from naratrace.nsdap.manifest import NsdapManifestClient
from naratrace.nsdap.models import FrameMatch, NsdapFrame, NsdapRoll
from naratrace.nsdap.roll_index import RollIndex
from naratrace.nsdap.roll_loader import NsdapRollLoader

MAX_MATERIALIZED_A3340_FRAMES = 3


@dataclass(frozen=True)
class NsdapCandidate:
    roll: NsdapRoll
    frame_match: FrameMatch

    @property
    def frame(self) -> NsdapFrame:
        return self.frame_match.frame


async def retrieve_nsdap_candidates(payload: SearchRequest) -> tuple[list[NsdapCandidate], list[str]]:
    """Retrieve a bounded set of concrete A3340 frames, never a roll PDF."""
    rolls = await NsdapManifestClient().load_rolls()
    selected_rolls = RollIndex(rolls).select_for_name(payload.last_name, collections=("MFKL",))
    if not selected_rolls:
        return [], ["A3340-Rollenindex fand keinen passenden MFKL-Bereich."]

    loader = NsdapRollLoader()
    matches: list[NsdapCandidate] = []
    warnings = ["A3340-Retrieval: " + ", ".join(f"{roll.collection} {roll.box}" for roll in selected_rolls)]
    for roll in selected_rolls:
        frames = await loader.load_frames(roll)
        if payload.membership_number:
            matches.extend(number_matches(roll, frames, payload.membership_number))
        for match in search_frames(frames, payload.first_name, payload.last_name, limit=120):
            matches.append(NsdapCandidate(roll=roll, frame_match=strengthen_with_number(match, payload.membership_number)))

    matches.sort(key=lambda candidate: (-candidate.frame_match.retrieval_score, candidate.roll.box, candidate.frame.frame_number))
    return dedupe_frames(matches)[:MAX_MATERIALIZED_A3340_FRAMES], warnings


def strengthen_with_number(match: FrameMatch, membership_number: str | None) -> FrameMatch:
    digits = re.sub(r"\D+", "", membership_number or "")
    text_digits = re.sub(r"\D+", "", match.frame.extracted_text or "")
    if not digits or digits not in text_digits:
        return match
    return FrameMatch(match.frame, 100.0, match.matched_variants, f"{match.strategy}+membership_number")


def number_matches(roll: NsdapRoll, frames: list[NsdapFrame], membership_number: str) -> list[NsdapCandidate]:
    digits = re.sub(r"\D+", "", membership_number)
    if not digits:
        return []
    return [
        NsdapCandidate(roll, FrameMatch(frame, 100.0, (), "membership_number_exact"))
        for frame in frames
        if digits in re.sub(r"\D+", "", frame.extracted_text or "")
    ]


def dedupe_frames(candidates: list[NsdapCandidate]) -> list[NsdapCandidate]:
    result: list[NsdapCandidate] = []
    seen: set[tuple[str, int]] = set()
    for candidate in candidates:
        key = (candidate.roll.naid, candidate.frame.frame_number)
        if key not in seen:
            seen.add(key)
            result.append(candidate)
    return result
