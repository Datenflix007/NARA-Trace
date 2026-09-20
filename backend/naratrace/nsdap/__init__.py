"""Access to NARA's public A3340 NSDAP dataset.

This package deliberately keeps dataset retrieval separate from Catalog API
search and identity ranking.  It exposes rolls and frames with their source
metadata; it does not decide that a frame identifies a person.
"""

from naratrace.nsdap.models import NsdapFrame, NsdapRoll

__all__ = ["NsdapFrame", "NsdapRoll"]
