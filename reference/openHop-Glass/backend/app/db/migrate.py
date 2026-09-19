from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine

_MIGRATION_VERSION_PREFIX_ALIASES: dict[str, str] = {
    "0011_alert_actions": "0011_alert_actions_",
}


def _migration_dir() -> Path:
    return Path(__file__).parent / "migrations"


def _split_statements(script: str) -> list[str]:
    return [statement.strip() for statement in script.split(";") if statement.strip()]


def _normalize_applied_versions(applied: set[str]) -> set[str]:
    normalized = set(applied)
    for current_version, legacy_prefix in _MIGRATION_VERSION_PREFIX_ALIASES.items():
        if any(version.startswith(legacy_prefix) for version in applied):
            normalized.add(current_version)
    return normalized


def apply_migrations(engine: Engine) -> None:
    migrations_path = _migration_dir()
    sql_files = sorted(migrations_path.glob("*.sql"))

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TIMESTAMP NOT NULL
                )
                """
            )
        )
        versions_result = conn.execute(
            text("SELECT version FROM schema_migrations ORDER BY version"),
        )
        applied = {row[0] for row in versions_result}
        normalized_applied = _normalize_applied_versions(applied)

        for sql_file in sql_files:
            version = sql_file.stem
            if version in normalized_applied:
                continue

            script = sql_file.read_text(encoding="utf-8")
            for statement in _split_statements(script):
                conn.execute(text(statement))
            insert_migration = (
                "INSERT INTO schema_migrations (version, applied_at) "
                "VALUES (:version, CURRENT_TIMESTAMP)"
            )

            conn.execute(
                text(insert_migration),
                {"version": version},
            )

