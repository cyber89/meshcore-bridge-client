from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "pyMC_Glass API"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8080
    app_log_level: str = "INFO"

    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/pymc_glass"
    )
    mqtt_broker_host: str = "localhost"
    mqtt_broker_port: int = 1883
    mqtt_broker_username: str | None = None
    mqtt_broker_password: str | None = None
    mqtt_tls_enabled: bool = False
    mqtt_tls_ca_cert: str | None = None
    mqtt_tls_client_cert: str | None = None
    mqtt_tls_client_key: str | None = None
    mqtt_tls_insecure: bool = False
    mqtt_base_topic: str = "glass"
    mqtt_repeater_tls_enabled: bool = False
    mqtt_ingest_enabled: bool = True
    mqtt_ingest_queue_maxsize: int = 2000
    pki_state_dir: str = "/app/data/pki"
    pki_ca_common_name: str = "pyMC_Glass Local CA"
    pki_ca_valid_days: int = 3650
    pki_client_cert_valid_days: int = 90
    pki_renew_before_days: int = 30
    auth_token_ttl_minutes: int = 1440
    auth_token_bytes: int = 48
    auth_password_min_length: int = 12
    bootstrap_seed_admin_enabled: bool = True
    bootstrap_seed_admin_email: str = "admin@pymc.glass"
    bootstrap_seed_admin_password: str = "admin12345678"
    bootstrap_seed_admin_display_name: str = "Admin"
    alert_policy_monitor_enabled: bool = True
    alert_policy_monitor_interval_seconds: int = 60
    alert_action_dispatcher_enabled: bool = True
    alert_action_dispatcher_interval_seconds: int = 10
    alert_action_dispatcher_batch_size: int = 50
    alert_action_dispatcher_max_attempts: int = 5
    alert_action_dispatcher_backoff_seconds: int = 15
    config_snapshot_encryption_keys: str | None = None
    config_snapshot_retention_max_per_repeater: int = 20
    config_snapshot_retention_max_age_days: int = 90
    config_snapshot_max_payload_bytes: int = 2_000_000

    contract_version: str = "v1"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

