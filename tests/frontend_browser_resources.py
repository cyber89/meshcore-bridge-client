"""Exact remote tile routes replaced by neutral images in offline browser QA."""

from __future__ import annotations

import re
from collections import Counter

_REMOTE_TILE = re.compile(
    r"https://(?:tile\.openstreetmap\.org/\d+/\d+/\d+\.png|"
    r"server\.arcgisonline\.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/\d+/\d+/\d+)"
)


def is_expected_remote_map_tile(url: str) -> bool:
    """Only the application's two remote map providers have virtual tile fixtures."""
    return _REMOTE_TILE.fullmatch(url) is not None


def unexpected_request_failures(
    failures: list[tuple[str, str, str]], observed_aborts: list[dict[str, str]],
) -> list[str]:
    """Match one failed request to one observed application signal cancellation."""
    cancellations = Counter((abort["url"], abort["method"]) for abort in observed_aborts)
    unexpected = []
    for error, url, method in failures:
        key = (url, method)
        if error == "net::ERR_ABORTED" and cancellations[key] > 0:
            cancellations[key] -= 1
        else:
            unexpected.append(f"{error} {url}")
    return unexpected
