from __future__ import annotations

from rapidfuzz import fuzz

from naratrace.matching.name_normalizer import NameNormalizer
from naratrace.nsdap.models import FrameMatch, NsdapFrame


def search_frames(
    frames: list[NsdapFrame], first_name: str | None, last_name: str, limit: int = 100
) -> list[FrameMatch]:
    """Retrieve text-bearing frame candidates; this is not identity ranking."""
    normalizer = NameNormalizer()
    surname_variants = normalizer.variants(last_name)
    first_key = normalizer.normalize(first_name or "")
    matches: list[FrameMatch] = []
    for frame in frames:
        text = frame.extracted_text or ""
        normalized_text = normalizer.normalize(text)
        if not normalized_text:
            continue
        tokens = normalized_text.split()
        matched: list[str] = []
        best = 0.0
        for variant in surname_variants:
            if variant.normalized in normalized_text:
                matched.append(variant.value)
                best = max(best, 72.0 + 24.0 * variant.weight)
            elif variant.source != "doppelname_stamm":
                # Do not run partial_ratio against an entire OCR page: any
                # short accidental character run can otherwise score 100.
                # Compare only word windows with the same name length.
                word_count = len(variant.normalized.split())
                for index in range(0, max(0, len(tokens) - word_count + 1)):
                    window = " ".join(tokens[index : index + word_count])
                    best = max(best, fuzz.ratio(variant.normalized, window) * variant.weight)
        if first_key and first_key in normalized_text and best >= 65:
            best = min(100.0, best + 4.0)
        if best >= 70:
            strategy = "surname_exact_or_normalized" if matched else "surname_fuzzy"
            matches.append(FrameMatch(frame, round(best, 2), tuple(matched), strategy))
    matches.sort(key=lambda match: (-match.retrieval_score, match.frame.frame_number))
    return matches[: max(1, limit)]
