from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class NameVariant:
    value: str
    normalized: str
    source: str
    weight: float


class NameNormalizer:
    """Generate weighted historical-name variants without discarding the input."""

    def normalize(self, value: str) -> str:
        decomposed = unicodedata.normalize("NFKD", value).casefold().replace("ß", "ss")
        without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
        return re.sub(r"[^a-z0-9]+", " ", without_marks).strip()

    def variants(self, value: str) -> list[NameVariant]:
        original = " ".join(value.strip().split())
        if not original:
            return []
        candidates: list[tuple[str, str, float]] = [(original, "original", 1.0)]
        if "-" in original:
            candidates.extend(
                [
                    (original.replace("-", " "), "bindestrich_zu_leerzeichen", 0.94),
                    (original.replace("-", ""), "bindestrich_entfernt", 0.88),
                    (original.split("-", 1)[0].strip(), "doppelname_stamm", 0.62),
                ]
            )
        candidates.extend(self._umlaut_variants(original))
        candidates.extend(self._nobility_variants(original))
        return self._dedupe(candidates)

    def _umlaut_variants(self, value: str) -> list[tuple[str, str, float]]:
        transliterated = (
            value.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
            .replace("Ä", "Ae").replace("Ö", "Oe").replace("Ü", "Ue").replace("ß", "ss")
        )
        simplified = (
            value.replace("ä", "a").replace("ö", "o").replace("ü", "u")
            .replace("Ä", "A").replace("Ö", "O").replace("Ü", "U").replace("ß", "ss")
        )
        return [(transliterated, "umlaut_transliteration", 0.9), (simplified, "umlaut_vereinfacht", 0.82)]

    def _nobility_variants(self, value: str) -> list[tuple[str, str, float]]:
        if not re.match(r"^von\s+", value, flags=re.IGNORECASE):
            return []
        rest = re.sub(r"^von\s+", "", value, flags=re.IGNORECASE)
        return [(f"v. {rest}", "adelsprädikat_abgekürzt", 0.9), (rest, "adelsprädikat_ohne", 0.68)]

    def _dedupe(self, candidates: list[tuple[str, str, float]]) -> list[NameVariant]:
        variants: list[NameVariant] = []
        seen: set[str] = set()
        for raw, source, weight in candidates:
            cleaned = " ".join(raw.strip().split())
            normalized = self.normalize(cleaned)
            # Keep visibly distinct historical spellings even when the matching
            # key intentionally folds them together (e.g. Müller / Muller).
            display_key = cleaned.casefold()
            if not normalized or display_key in seen:
                continue
            seen.add(display_key)
            variants.append(NameVariant(cleaned, normalized, source, weight))
        return variants
