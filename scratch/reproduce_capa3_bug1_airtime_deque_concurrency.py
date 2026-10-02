"""
Reproduction script for Bug C3-01:
AirtimeTracker.get_stats() deque mutated during iteration under concurrent access.
"""

import os
import sys
import threading
import time

sys.path.insert(0, os.path.abspath("."))
from src.rate_limiter import AirtimeTracker

def main() -> int:
    tracker = AirtimeTracker()
    # Pre-populate records
    for _ in range(50):
        tracker.record_tx(50.0)

    errors: list[str] = []
    stop_event = threading.Event()

    def reader() -> None:
        while not stop_event.is_set():
            try:
                tracker.get_stats()
            except RuntimeError as e:
                errors.append(str(e))
                stop_event.set()
                break

    def writer() -> None:
        while not stop_event.is_set():
            tracker.record_tx(10.0)
            time.sleep(0.0001)

    t1 = threading.Thread(target=reader, daemon=True)
    t2 = threading.Thread(target=writer, daemon=True)

    t1.start()
    t2.start()

    time.sleep(1.0)
    stop_event.set()
    t1.join(timeout=0.5)
    t2.join(timeout=0.5)

    if errors:
        print(f"[REPRODUCED] Bug C3-01: Caught expected RuntimeError: {errors[0]}")
        return 1
    else:
        print("[FAIL] Bug C3-01 could not be reproduced.")
        return 0

if __name__ == "__main__":
    sys.exit(main())
