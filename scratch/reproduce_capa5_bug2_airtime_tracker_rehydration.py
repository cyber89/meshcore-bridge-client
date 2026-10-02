"""
Reproduction script for Capa 5 Bug C5-02:
Silent Loss of Custom Configuration and Incomplete Rehydration in AirtimeTracker / ConfigController.

Root Cause:
1. ConfigController.set_local_config updates airtime parameters in memory on
   limiter.airtime_tracker (e.g., duty_cycle_limit_pct, warn_threshold_pct, cutoff_threshold_pct),
   but never triggers disk persistence.
2. Even when AirtimeTracker.save_history(sync=True) writes these 5 parameters into airtime_history.json:
       "duty_cycle_limit_pct": 2.5,
       "warn_threshold_pct": 90.0,
       "cutoff_threshold_pct": 50.0,
       "cutoff_resume_pct": 40.0,
       "cutoff_enabled": False,
   AirtimeTracker.load_history() completely ignores all 5 fields during rehydration!
   Lines 232-273 in src/rate_limiter.py only reload 'records', 'channel_utilization_pct', and 'cutoff_active'.
   Upon bridge reboot or service restart, the customized parameters revert silently to hardcoded defaults.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.rate_limiter import AirtimeTracker


def main() -> None:
    temp_dir = tempfile.mkdtemp(prefix="capa5_airtime_")
    history_file = os.path.join(temp_dir, "airtime_history.json")

    try:
        # Step 1: Initial tracker with default config
        initial_tracker = AirtimeTracker(
            duty_cycle_limit_pct=1.0,
            warn_threshold_pct=80.0,
            cutoff_threshold_pct=35.0,
            cutoff_resume_pct=30.0,
            cutoff_enabled=True,
            history_file=history_file,
        )

        # Step 2: User customizes settings through WebUI /api/node/config (via ConfigController)
        custom_duty_limit = 2.5
        custom_warn_pct = 95.0
        custom_cutoff_thresh = 45.0
        custom_cutoff_resume = 35.0
        custom_cutoff_enabled = False

        initial_tracker.duty_cycle_limit_pct = custom_duty_limit
        initial_tracker.warn_threshold_pct = custom_warn_pct
        initial_tracker.cutoff_threshold_pct = custom_cutoff_thresh
        initial_tracker.cutoff_resume_pct = custom_cutoff_resume
        initial_tracker.cutoff_enabled = custom_cutoff_enabled

        # Force save to disk
        initial_tracker.save_history(sync=True)

        # Verify that save_history indeed wrote the keys into the JSON payload
        with open(history_file, encoding="utf-8") as f:
            disk_data = json.load(f)

        print("--- Disk Verification (airtime_history.json) ---")
        print(f"duty_cycle_limit_pct on disk: {disk_data.get('duty_cycle_limit_pct')}")
        print(f"warn_threshold_pct on disk:   {disk_data.get('warn_threshold_pct')}")
        print(f"cutoff_threshold_pct on disk: {disk_data.get('cutoff_threshold_pct')}")
        print(f"cutoff_resume_pct on disk:    {disk_data.get('cutoff_resume_pct')}")
        print(f"cutoff_enabled on disk:       {disk_data.get('cutoff_enabled')}")

        # Step 3: Simulate bridge service reboot - new instance created with default parameters from config.py
        rebooted_tracker = AirtimeTracker(
            duty_cycle_limit_pct=1.0,  # default from config.py
            warn_threshold_pct=80.0,  # default from config.py
            cutoff_threshold_pct=35.0,  # default from config.py
            cutoff_resume_pct=30.0,  # default from config.py
            cutoff_enabled=True,  # default from config.py
            history_file=history_file,
        )

        print("\n--- Rehydration Verification after Service Restart ---")
        print(f"duty_cycle_limit_pct: expected {custom_duty_limit}, actual {rebooted_tracker.duty_cycle_limit_pct}")
        print(f"warn_threshold_pct:   expected {custom_warn_pct}, actual {rebooted_tracker.warn_threshold_pct}")
        print(f"cutoff_threshold_pct: expected {custom_cutoff_thresh}, actual {rebooted_tracker.cutoff_threshold_pct}")
        print(f"cutoff_resume_pct:    expected {custom_cutoff_resume}, actual {rebooted_tracker.cutoff_resume_pct}")
        print(f"cutoff_enabled:       expected {custom_cutoff_enabled}, actual {rebooted_tracker.cutoff_enabled}")

        failures = []
        if rebooted_tracker.duty_cycle_limit_pct != custom_duty_limit:
            failures.append("duty_cycle_limit_pct not restored")
        if rebooted_tracker.warn_threshold_pct != custom_warn_pct:
            failures.append("warn_threshold_pct not restored")
        if rebooted_tracker.cutoff_threshold_pct != custom_cutoff_thresh:
            failures.append("cutoff_threshold_pct not restored")
        if rebooted_tracker.cutoff_resume_pct != custom_cutoff_resume:
            failures.append("cutoff_resume_pct not restored")
        if rebooted_tracker.cutoff_enabled != custom_cutoff_enabled:
            failures.append("cutoff_enabled not restored")

        if failures:
            print(f"\n>>> BUG C5-02 REPRODUCED: {len(failures)} configuration parameters were silently discarded on reload:")
            for f in failures:
                print(f"  - {f}")
        else:
            print("\nRehydration succeeded (no bug observed).")

    finally:
        if os.path.exists(history_file):
            os.remove(history_file)
        if os.path.exists(temp_dir):
            os.rmdir(temp_dir)


if __name__ == "__main__":
    main()
