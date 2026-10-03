"""Exact remote tile routes replaced by neutral images in offline browser QA."""

from __future__ import annotations

import re

_REMOTE_TILE = re.compile(
    r"https://(?:tile\.openstreetmap\.org/\d+/\d+/\d+\.png|"
    r"server\.arcgisonline\.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/\d+/\d+/\d+)"
)


def is_expected_remote_map_tile(url: str) -> bool:
    """Only the application's two remote map providers have virtual tile fixtures."""
    return _REMOTE_TILE.fullmatch(url) is not None
