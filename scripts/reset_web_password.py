"""Recover existing station credentials using hidden input in a local terminal.

Usage: python scripts/reset_web_password.py [--username USER] [--project-dir DIR]
       python scripts/reset_web_password.py --db-path /absolute/station.sqlite3
"""

from __future__ import annotations

import argparse
import getpass
import os
import stat
import sys
import warnings
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.web.auth_store import AuthStore, validate_credentials


def _reject_symlinks(path: Path) -> None:
    for component in (path, *path.parents):
        if component.is_symlink():
            raise ValueError("Symbolic links are not allowed for credential recovery")


def resolve_database_path(project_dir: Path, explicit_path: Path | None) -> Path:
    """Select the target installation without importing a different config.py."""
    project_dir = Path(os.path.abspath(project_dir))
    _reject_symlinks(project_dir)
    if explicit_path is not None:
        path = Path(os.path.abspath(explicit_path))
    else:
        if not project_dir.is_dir():
            raise ValueError("Project directory does not exist")
        env_path = project_dir / ".env"
        _reject_symlinks(env_path)
        from dotenv.main import DotEnv
        values = DotEnv(env_path, override=False).dict() if env_path.is_file() else {}
        data_dir = os.environ.get("DATA_DIR") or values.get("DATA_DIR") or "data"
        database_path = os.environ.get("DATABASE_PATH") or values.get("DATABASE_PATH") or str(Path(data_dir) / "meshcore.sqlite3")
        path = Path(database_path)
        if not path.is_absolute():
            path = project_dir / path
        path = Path(os.path.abspath(path))
    for candidate in (path, Path(f"{path}-wal"), Path(f"{path}-shm")):
        _reject_symlinks(candidate)
    if not path.is_file():
        raise ValueError("An existing station database is required")
    if os.name == "posix":
        effective_uid = int(getattr(os, "geteuid", lambda: -1)())
        if path.stat().st_uid != effective_uid and effective_uid != 0:
            raise PermissionError("Run as the station database owner or administrator")
        if path.parent.stat().st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise PermissionError("The database directory must not be writable by other users")
    return path


def _read_hidden_password() -> str:
    if not sys.stdin.isatty():
        raise ValueError("Credential recovery requires an interactive local terminal")
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        password = getpass.getpass("New password (8-64 chars): ")
        confirmation = getpass.getpass("Confirm new password: ")
    if password != confirmation:
        raise ValueError("Passwords do not match")
    return password


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path, default=PROJECT_ROOT, help="Target installation directory")
    parser.add_argument("--db-path", type=Path, help="Existing station SQLite database")
    parser.add_argument("--username", help="New username (default: keep current)")
    if any(argument == "--password" or argument.startswith("--password=") for argument in sys.argv[1:]):
        parser.error("Passwords are accepted only through hidden interactive input")
    args = parser.parse_args()
    try:
        if not sys.stdin.isatty():
            raise ValueError("Credential recovery requires an interactive local terminal")
        db_path = resolve_database_path(args.project_dir, args.db_path)
        identity = (db_path.stat().st_dev, db_path.stat().st_ino)
        store = AuthStore(db_path)
        account = store._account()
        generation = int(account["generation"])
        current_username = str(account["username"])
        username = args.username or input(f"Username [{current_username}]: ").strip() or current_username
        password = _read_hidden_password()
        validate_credentials(username, password)
        # Recheck local path authority after the interactive prompt, too.
        if resolve_database_path(args.project_dir, db_path) != db_path:
            raise ValueError("Database path changed during recovery")
        if (db_path.stat().st_dev, db_path.stat().st_ino) != identity:
            raise ValueError("Database file changed during recovery")
        store.recover_credentials(username, password, expected_generation=generation)
    except KeyboardInterrupt:
        print("\nCredential recovery cancelled.", file=sys.stderr)
        return 130
    except Exception as error:
        print(f"Credential recovery failed ({type(error).__name__}). Check local access and account state.", file=sys.stderr)
        return 1
    print("Credentials updated. Existing browser sessions and generated API tokens were revoked.")
    print("Sign in normally with the new credentials. BRIDGE_API_KEY is managed separately.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
