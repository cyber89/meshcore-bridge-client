from collections.abc import Generator

import pytest
from app.config import get_settings
from app.db.session import reset_db_caches
from app.main import create_app
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch) -> Generator[TestClient, None, None]:
    db_path = tmp_path / "glass-test.db"
    pki_dir = tmp_path / "pki"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_path}")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("MQTT_INGEST_ENABLED", "false")
    monkeypatch.setenv("ALERT_POLICY_MONITOR_ENABLED", "false")
    monkeypatch.setenv("BOOTSTRAP_SEED_ADMIN_ENABLED", "false")
    monkeypatch.setenv("PKI_STATE_DIR", str(pki_dir))
    monkeypatch.setenv(
        "CONFIG_SNAPSHOT_ENCRYPTION_KEYS",
        (
            "primary:MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=,"
            "secondary:MTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTE="
        ),
    )
    monkeypatch.setenv("CONFIG_SNAPSHOT_RETENTION_MAX_PER_REPEATER", "2")
    monkeypatch.setenv("CONFIG_SNAPSHOT_RETENTION_MAX_AGE_DAYS", "365")
    monkeypatch.setenv("CONFIG_SNAPSHOT_MAX_PAYLOAD_BYTES", "2000000")

    get_settings.cache_clear()
    reset_db_caches()

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client

    get_settings.cache_clear()
    reset_db_caches()

