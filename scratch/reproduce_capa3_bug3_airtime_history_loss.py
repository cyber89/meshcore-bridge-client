"""
Reproduction script for Bug C3-03:
AirtimeTracker.load_history() resets cumulative total_airtime_ms and total_packets
because it only tallies records from the sliding 24-hour window, discarding saved totals.
"""

import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.abspath("."))
from src.rate_limiter import AirtimeTracker

def main() -> int:
    with tempfile.TemporaryDirectory() as tmpdir:
        hist_path = os.path.join(tmpdir, "airtime_history.json")
        now = time.time()

        # Step 1: Initialize tracker and record transmissions
        tracker1 = AirtimeTracker(history_file=hist_path)
        tracker1.record_tx(airtime_ms=5000.0, channel_idx=0)
        tracker1.record_tx(airtime_ms=3000.0, channel_idx=0)

        initial_airtime = tracker1.total_airtime_ms
        initial_pkts = tracker1.total_packets
        print(f"[STEP 1] Recorded initial airtime: {initial_airtime} ms, packets: {initial_pkts}")

        # Save to disk
        tracker1.save_history(sync=True)

        with open(hist_path, encoding="utf-8") as f:
            saved_data = json.load(f)

        saved_total_airtime = saved_data.get("total_airtime_ms")
        saved_total_packets = saved_data.get("total_packets")
        print(f"[STEP 2] Saved to JSON: total_airtime_ms={saved_total_airtime}, total_packets={saved_total_packets}")

        # Simulate that some time elapsed and individual records aged past 24 hours
        # In a real system, the bridge could be restarted after being off, or records get pruned
        for rec in saved_data.get("records", []):
            rec["timestamp"] = now - 90000.0  # 25 hours ago

        with open(hist_path, "w", encoding="utf-8") as f:
            json.dump(saved_data, f, indent=2)

        # Step 3: Reload history in a new AirtimeTracker instance
        tracker2 = AirtimeTracker(history_file=hist_path)

        reloaded_airtime = tracker2.total_airtime_ms
        reloaded_pkts = tracker2.total_packets
        print(f"[STEP 3] Reloaded in tracker2: total_airtime_ms={reloaded_airtime}, total_packets={reloaded_pkts}")

        # Verify that cumulative totals were lost despite being saved in the JSON file
        if reloaded_airtime != saved_total_airtime or reloaded_pkts != saved_total_packets:
            print(
                f"[REPRODUCED] Bug C3-03: Cumulative history lost on reload! "
                f"Expected {saved_total_airtime} ms / {saved_total_packets} pkts, "
                f"got {reloaded_airtime} ms / {reloaded_pkts} pkts."
            )
            return 1
        else:
            print("[FAIL] Bug C3-03 could not be reproduced.")
            return 0

if __name__ == "__main__":
    sys.exit(main())
