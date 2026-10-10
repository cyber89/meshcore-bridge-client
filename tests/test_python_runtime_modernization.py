"""Domain imports stay passive and native CRC preserves the raw wire format."""

import subprocess
import sys
from pathlib import Path

import pytest

from src.protocol_types import compute_crc16_ccitt


def test_domain_import_does_not_load_bridge_configuration() -> None:
    """Importing pure protocol types must not inspect an operational .env."""
    repository = Path(__file__).resolve().parents[1]
    code = """
import importlib.abc
import sys

sys.path.insert(0, sys.argv[1])

class BlockConfiguration(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in {"config", "dotenv"}:
            raise AssertionError("domain import tried to load operational configuration")
        return None

sys.meta_path.insert(0, BlockConfiguration())
import src
from src import FrameHeader
from src.protocol_types import FrameHeader as DirectFrameHeader

assert FrameHeader is DirectFrameHeader
assert src.FrameHeader is DirectFrameHeader
assert "src.bridge_core" not in sys.modules
assert "src.mqtt_client" not in sys.modules
assert "src.web.asgi_server" not in sys.modules
assert set(src.__all__) <= set(dir(src))
try:
    src.missing_export
except AttributeError:
    pass
else:
    raise AssertionError("unknown package export must raise AttributeError")
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", code, str(repository)],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("data,init,expected", [
    (b"123456789", 0xFFFF, 0x29B1),
    (b"123456789", 0x0000, 0x31C3),
    (b"", 0xFFFF, 0xFFFF),
    (b"", 0x0000, 0x0000),
    (b"", -1, -1),
    (b"", 0x10000, 0x10000),
])
def test_crc_known_vectors_and_empty_seed(data: bytes, init: int, expected: int) -> None:
    assert compute_crc16_ccitt(data, init=init) == expected


def reference_crc(data: bytes, init: int, poly: int) -> int:
    """Independent bit-by-bit reference for custom-polynomial compatibility."""
    result = init
    for byte in data:
        for bit in range(7, -1, -1):
            high_bit = bool(result & 0x8000)
            input_bit = bool(byte & (1 << bit))
            result = (result << 1) & 0xFFFF
            if high_bit != input_bit:
                result ^= poly
                result &= 0xFFFF
    return result


@pytest.mark.parametrize("poly", [0x1021, 0x8005, 0x0001])
@pytest.mark.parametrize("init", [0, 0xFFFF, 0x1D0F, -1, 0x10000])
@pytest.mark.parametrize("data", [b"\x00\xaa\x55\x1b", bytes(range(256)), b"payload" * 31])
def test_crc_preserves_seed_and_polynomial(data: bytes, init: int, poly: int) -> None:
    assert compute_crc16_ccitt(data, init=init, poly=poly) == reference_crc(data, init, poly)
