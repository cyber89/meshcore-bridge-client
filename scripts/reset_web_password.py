"""CLI tool to reset or recover the web dashboard credentials locally.

Usage:
    python scripts/reset_web_password.py [--username USER] [--password PASS] [--project-dir DIR]
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.web.auth_store import AuthStore, validate_credentials


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset or recover MeshCore Bridge web dashboard credentials.")
    parser.add_argument("--project-dir", type=Path, default=PROJECT_ROOT, help="Project root directory")
    parser.add_argument("--db-path", type=Path, default=None, help="Explicit path to station SQLite database")
    parser.add_argument("--username", type=str, default=None, help="New username (default: current or admin)")
    parser.add_argument("--password", type=str, default=None, help="New password (8-64 chars)")
    args = parser.parse_args()

    project_dir = args.project_dir.resolve()
    if args.db_path:
        db_path = args.db_path.resolve()
    else:
        # Load from config or default data/meshcore.sqlite3
        import config
        db_path = Path(config.DATABASE_PATH)
        if not db_path.is_absolute():
            db_path = project_dir / db_path

    if not db_path.exists():
        print(f"Error: Database not found at {db_path}", file=sys.stderr)
        return 1

    store = AuthStore(db_path)
    try:
        current_account = store._account()
        current_username = str(current_account["username"])
    except Exception as exc:
        print(f"Error reading account: {exc}", file=sys.stderr)
        return 1

    username = args.username
    if not username:
        entered_user = input(f"Username [{current_username}]: ").strip()
        username = entered_user or current_username

    password = args.password
    if not password:
        password = getpass.getpass("New password (8-64 chars): ")
        confirmation = getpass.getpass("Confirm new password: ")
        if password != confirmation:
            print("Error: Passwords do not match.", file=sys.stderr)
            return 1

    try:
        validate_credentials(username, password)
    except ValueError as err:
        print(f"Error validating credentials: {err}", file=sys.stderr)
        return 1

    try:
        store.recover_credentials(username, password)
        print(f"\n[OK] Successfully updated credentials for user '{username}'.")
        print("All existing web sessions and API tokens have been revoked.")
        print("You can now sign in at http://localhost:8080 with your new credentials.\n")
        return 0
    except Exception as exc:
        print(f"Error updating credentials: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
