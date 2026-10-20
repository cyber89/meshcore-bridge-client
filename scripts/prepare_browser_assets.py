"""Cache pinned Leaflet fixtures for offline browser QA, checking their SHA-256."""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
ASSETS = {
    "js": "20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=",
    "css": "p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=",
}


def main() -> None:
    destination = ROOT / "tests/artifacts/frontend-ui"
    destination.mkdir(parents=True, exist_ok=True)
    for extension, expected in ASSETS.items():
        url = f"https://unpkg.com/leaflet@1.9.4/dist/leaflet.{extension}"
        with urlopen(url, timeout=30) as response:  # nosec B310: fixed HTTPS vendor URL
            content = response.read()
        actual = base64.b64encode(hashlib.sha256(content).digest()).decode("ascii")
        if actual != expected:
            raise ValueError(f"Leaflet {extension} digest mismatch")
        (destination / f"leaflet-1.9.4.{extension}").write_bytes(content)
    print("Verified pinned Leaflet JS/CSS fixtures")


if __name__ == "__main__":
    main()
