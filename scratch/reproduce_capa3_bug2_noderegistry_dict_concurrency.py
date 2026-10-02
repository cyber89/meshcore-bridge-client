"""
Reproduction script for Bug C3-02:
NodeRegistry search methods iterate over _nodes_by_key without acquiring _lock,
causing RuntimeError: dictionary changed size during iteration under concurrent access.
"""

import os
import sys
import threading
import time

sys.path.insert(0, os.path.abspath("."))
from src.contact_manager import NodeContactUpdate, NodeRegistry

def main() -> int:
    registry = NodeRegistry()
    # Pre-populate some nodes
    for i in range(50):
        pk = f"aabbcc{i:04d}"
        registry.add_or_update(pk, NodeContactUpdate(name=f"Node_{i}"))

    errors: list[str] = []
    stop_event = threading.Event()

    def reader() -> None:
        while not stop_event.is_set():
            try:
                # get_by_key_or_prefix iterates _nodes_by_key.items() without _lock
                registry.get_by_key_or_prefix("aabb")
                # find_by_name iterates _nodes_by_key.values() without _lock
                registry.find_by_name("NonExistent")
                # list_discovered iterates _nodes_by_key.values() without _lock
                registry.list_discovered()
            except RuntimeError as e:
                errors.append(str(e))
                stop_event.set()
                break

    def writer() -> None:
        cnt = 100
        while not stop_event.is_set():
            pk = f"112233{cnt:04d}"
            registry.add_or_update(pk, NodeContactUpdate(name=f"New_{cnt}"))
            cnt += 1
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
        print(f"[REPRODUCED] Bug C3-02: Caught expected RuntimeError: {errors[0]}")
        return 1
    else:
        print("[FAIL] Bug C3-02 could not be reproduced.")
        return 0

if __name__ == "__main__":
    sys.exit(main())
