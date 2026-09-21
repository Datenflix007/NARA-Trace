from __future__ import annotations

import re
from dataclasses import dataclass

from naratrace.api.schemas import SearchRequest
from naratrace.nsdap.frame_search import search_frames
from naratrace.nsdap.frame_index import NsdapFrameIndex, extract_number_terms
from naratrace.nsdap.manifest import NsdapManifestClient
from naratrace.nsdap.models import FrameMatch, NsdapFrame, NsdapRoll

MAX_MATERIALIZED_A3340_FRAMES = 3


@dataclass(frozen=True)
class NsdapCandidate:
    roll: NsdapRoll
    frame_match: FrameMatch
    card_frames: tuple[NsdapFrame, ...] = ()

    @property
    def frame(self) -> NsdapFrame:
        return self.frame_match.frame


async def retrieve_nsdap_candidates(payload: SearchRequest) -> tuple[list[NsdapCandidate], list[str]]:
    """Retrieve concrete A3340 frames from the complete local MFKL/MFOK index."""
    rolls = await NsdapManifestClient().load_rolls()
    selected_rolls = [roll for roll in rolls if roll.collection in {"MFKL", "MFOK"}]
    if not selected_rolls:
        return [], ["A3340-Manifest enthÃ¤lt keine MFKL- oder MFOK-Rollen."]

    frame_index = NsdapFrameIndex()
    build = await frame_index.build_all(selected_rolls)
    indexed_rolls, _ = frame_index.index_status()
    warnings = [
        f"A3340-Korpusindex: {indexed_rolls}/{len(selected_rolls)} MFKL/MFOK-Rollen lokal durchsuchbar.",
        "A3340-Retrieval durchsucht den lokalen Gesamtindex, nicht eine bekannte Rolle oder einen festen R-Bereich.",
    ]
    if build.failed_rolls:
        warnings.append(f"{build.failed_rolls} Roll-JSON-Dateien konnten im aktuellen Lauf nicht indexiert werden.")
        warnings.extend(build.warnings[:8])

    frames = frame_index.search_frames(
        selected_rolls,
        surname=payload.last_name,
        membership_number=payload.membership_number,
    )
    matches: list[NsdapCandidate] = []
    for frame in frames:
        if payload.membership_number and frame_contains_number(frame, payload.membership_number):
            matches.append(NsdapCandidate(frame.roll, FrameMatch(frame, 100.0, (), "membership_number_exact")))
    for match in search_frames(frames, payload.first_name, payload.last_name, limit=600):
        matches.append(NsdapCandidate(roll=match.frame.roll, frame_match=strengthen_with_number(match, payload.membership_number)))

    matches.sort(key=lambda candidate: (-candidate.frame_match.retrieval_score, candidate.roll.box, candidate.frame.frame_number))
    selected = dedupe_frames(matches)[:MAX_MATERIALIZED_A3340_FRAMES]
    return [
        NsdapCandidate(
            roll=candidate.roll,
            frame_match=candidate.frame_match,
            card_frames=tuple(
                frame_index.card_context_frames(
                    candidate.roll,
                    candidate.frame,
                    surname=payload.last_name,
                    membership_number=payload.membership_number,
                )
            ),
        )
        for candidate in selected
    ], warnings


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
        if digits in extract_number_terms(frame.extracted_text or "")
    ]


def frame_contains_number(frame: NsdapFrame, membership_number: str) -> bool:
    digits = re.sub(r"\D+", "", membership_number)
    if not digits:
        return False
    return digits in extract_number_terms(frame.extracted_text or "")


def dedupe_frames(candidates: list[NsdapCandidate]) -> list[NsdapCandidate]:
    result: list[NsdapCandidate] = []
    seen: set[tuple[str, int]] = set()
    for candidate in candidates:
        key = (candidate.roll.naid, candidate.frame.frame_number)
        if key not in seen:
            seen.add(key)
            result.append(candidate)
    return result
