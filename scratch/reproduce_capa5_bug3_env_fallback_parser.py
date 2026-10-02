"""
Reproduction script for Capa 5 Bug C5-03:
Fallback .env Parser Malfunctions on Inline Comments and Quoted Values.

Root Cause:
In config.py (lines 18-28), when python-dotenv is unavailable or when the fallback
parser executes:
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("\"'")
                if k and k not in os.environ:
                    os.environ[k] = v

Defects:
1. Inline comments (e.g., `WEB_PORT=8080 # Port for dashboard`) are NOT stripped.
   The value `v` becomes `"8080 # Port for dashboard"`.
   When `_safe_int("WEB_PORT", 8080)` executes, `int("8080 # Port for dashboard")`
   raises ValueError, causing the system to silently fallback to the default value
   or fail validation!
2. Quoted strings with trailing comments (e.g., `BRIDGE_API_KEY="my-secret-token" # Auth`)
   fail the `.strip("\"'")` check because the trailing character is `# Auth`, leaving
   the literal quotation marks and comment inside the secret token!
"""

import os
import tempfile
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import _parse_env_value


def parse_fallback_env(env_lines: list[str]) -> dict[str, str]:
    """Uses _parse_env_value from config.py."""
    parsed = {}
    for line in env_lines:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, raw_v = line.split("=", 1)
            k = k.strip()
            v = _parse_env_value(raw_v)
            if k:
                parsed[k] = v
    return parsed


def main() -> None:
    test_env = [
        "# Sample configuration file",
        "WEB_PORT=9090 # Puerto Web de monitoreo",
        "BRIDGE_API_KEY=\"super-secret-12345\" # Token de seguridad",
        "DUTY_CYCLE_LIMIT_PCT=2.0 # Limite horario LoRa",
    ]

    parsed = parse_fallback_env(test_env)

    print("--- Fallback Parser Outputs ---")
    print(f"Parsed WEB_PORT:              {repr(parsed.get('WEB_PORT'))}")
    print(f"Parsed BRIDGE_API_KEY:         {repr(parsed.get('BRIDGE_API_KEY'))}")
    print(f"Parsed DUTY_CYCLE_LIMIT_PCT:  {repr(parsed.get('DUTY_CYCLE_LIMIT_PCT'))}")

    errors: list[str] = []

    # Check int parsing
    raw_port = parsed.get("WEB_PORT", "")
    try:
        int_port = int(raw_port)
    except ValueError as e:
        errors.append(f"int(WEB_PORT) failed: {e}")

    # Check float parsing
    raw_dc = parsed.get("DUTY_CYCLE_LIMIT_PCT", "")
    try:
        float_dc = float(raw_dc)
    except ValueError as e:
        errors.append(f"float(DUTY_CYCLE_LIMIT_PCT) failed: {e}")

    # Check token string
    raw_token = parsed.get("BRIDGE_API_KEY", "")
    if raw_token != "super-secret-12345":
        errors.append(f"BRIDGE_API_KEY corrupted with quotes and comments: {repr(raw_token)}")

    print("\n--- Errors Encountered ---")
    for err in errors:
        print(f"  [ERROR] {err}")

    if errors:
        print("\n>>> BUG C5-03 REPRODUCED: Fallback .env parser failed to strip inline comments and preserve clean tokens!")
    else:
        print("\nFallback parser parsed all values cleanly.")


if __name__ == "__main__":
    main()
