"""
Reproduction script for Capa 5 Bug C5-01:
Race Condition and Windows WinError 32 in ChannelsController._save_channels.

Root Cause:
ChannelsController._save_channels uses a fixed, static temporary filename:
    tmp_path = f"{self.channels_file}.tmp"
When multiple coroutines or threads invoke _save_channels (or _save_channels_async)
concurrently without thread synchronization or unique PID/nanosecond file suffixes,
Windows raises:
    [WinError 32] The process cannot access the file because it is being used by another process
and on POSIX systems, concurrent writes can interleave or truncate the temporary JSON.
"""

import concurrent.futures
import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.web.controllers.channels_controller import ChannelsController


def main() -> None:
    temp_dir = tempfile.mkdtemp(prefix="capa5_race_")
    channels_path = os.path.join(temp_dir, "channels.json")

    try:
        mock_ctx = MagicMock()
        mock_ctx.bridge = MagicMock()
        mock_ctx.broadcast_ws = None
        mock_ctx.log_system_event = MagicMock()

        ctrl = ChannelsController(mock_ctx, channels_file=channels_path)
        ctrl.channels = {0: {"index": 0, "name": "Public", "psk": "", "is_public": True}}

        errors: list[str] = []

        def worker(idx: int) -> None:
            try:
                ctrl.channels[idx] = {
                    "index": idx,
                    "name": f"Channel {idx}",
                    "psk": "secret",
                    "is_public": False,
                }
                ctrl._dirty = True
                ctrl._save_channels(force=True)
            except Exception as e:
                errors.append(f"Worker {idx} failed with {type(e).__name__}: {e}")

        # Run concurrent writes to the same channels controller
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(worker, i) for i in range(1, 15)]
            concurrent.futures.wait(futures)

        print(f"Total concurrent worker errors caught: {len(errors)}")
        for err in errors[:5]:
            print(f"  [ERROR] {err}")

        if errors:
            print("\n>>> BUG C5-01 REPRODUCED: Concurrent writes to fixed temporary path crashed with file locking conflict!")
        else:
            print("\nNo error observed in this iteration.")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
