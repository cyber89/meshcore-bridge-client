from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from app.api.routes.adoption import router as adoption_router
from app.api.routes.alert_actions import router as alert_actions_router
from app.api.routes.alerts import router as alerts_router
from app.api.routes.alert_policy import groups_router as node_groups_router
from app.api.routes.alert_policy import router as alert_policy_router
from app.api.routes.audit import router as audit_router
from app.api.routes.auth import router as auth_router
from app.api.routes.bootstrap import router as bootstrap_router
from app.api.routes.commands import router as commands_router
from app.api.routes.config_snapshots import router as config_snapshots_router
from app.api.routes.contracts import router as contracts_router
from app.api.routes.health import router as health_router
from app.api.routes.inform import router as inform_router
from app.api.routes.insights import router as insights_router
from app.api.routes.packets import router as packets_router
from app.api.routes.repeaters import router as repeaters_router
from app.api.routes.smoke import router as smoke_router
from app.api.routes.system_settings import router as system_settings_router
from app.api.routes.telemetry import router as telemetry_router
from app.api.routes.transport_keys import router as transport_keys_router
from app.api.routes.users import router as users_router
from app.config import get_settings
from app.db.migrate import apply_migrations
from app.db.session import get_engine, get_session_factory
from app.services.alert_actions import get_notification_provider_registry
from app.services.alert_action_dispatcher import AlertActionDispatcherService
from app.services.alert_policy_monitor import AlertPolicyMonitorService
from app.services.bootstrap_seed import seed_default_admin_if_needed
from app.services.mqtt_ingest import MqttIngestService
from app.services.pki import PkiService
from app.services.system_settings import get_effective_managed_mqtt_settings
from app.services.telemetry_stream import get_mqtt_telemetry_broadcaster


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    apply_migrations(get_engine())
    session_factory = get_session_factory()
    seed_default_admin_if_needed(settings, session_factory)
    managed_mqtt_host = ""
    with session_factory() as db:
        managed_mqtt_settings, _, _ = get_effective_managed_mqtt_settings(db)
        managed_mqtt_host = str(managed_mqtt_settings.get("mqtt_broker_host", "")).strip()
    pki_service = PkiService(settings)
    pki_service.ensure_ca()
    pki_service.ensure_mqtt_broker_server_certificate(
        extra_san_hosts=[managed_mqtt_host] if managed_mqtt_host else None
    )
    pki_service.ensure_backend_mqtt_client_certificate()
    mqtt_ingest = MqttIngestService(
        settings,
        session_factory,
        broadcaster=get_mqtt_telemetry_broadcaster(),
    )
    provider_registry = get_notification_provider_registry()
    action_dispatcher = AlertActionDispatcherService(
        settings,
        session_factory,
        provider_registry,
    )
    alert_monitor = AlertPolicyMonitorService(settings, session_factory)
    await mqtt_ingest.start()
    await action_dispatcher.start()
    await alert_monitor.start()
    try:
        yield
    finally:
        await alert_monitor.stop()
        await action_dispatcher.stop()
        await mqtt_ingest.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version = "1.0.4",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )
    app.state.notification_provider_registry = get_notification_provider_registry()

    app.include_router(health_router, tags=["health"])
    app.include_router(inform_router, tags=["inform"])
    app.include_router(contracts_router, prefix="/api/contracts", tags=["contracts"])
    app.include_router(bootstrap_router, tags=["bootstrap"])
    app.include_router(auth_router, tags=["auth"])
    app.include_router(repeaters_router, tags=["repeaters"])
    app.include_router(adoption_router, tags=["adoption"])
    app.include_router(commands_router, tags=["commands"])
    app.include_router(config_snapshots_router, tags=["config-snapshots"])
    app.include_router(system_settings_router, tags=["system-settings"])
    app.include_router(packets_router, tags=["packets"])
    app.include_router(insights_router, tags=["insights"])
    app.include_router(alerts_router, tags=["alerts"])
    app.include_router(alert_actions_router, tags=["alert-actions"])
    app.include_router(alert_policy_router, tags=["alert-policies"])
    app.include_router(node_groups_router, tags=["node-groups"])
    app.include_router(transport_keys_router, tags=["transport-keys"])
    app.include_router(audit_router, tags=["audit"])
    app.include_router(users_router, tags=["users"])
    app.include_router(smoke_router, tags=["smoke"])
    app.include_router(telemetry_router, tags=["telemetry"])

    return app


app = create_app()


def run() -> None:
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_env == "development",
        log_level=settings.app_log_level.lower(),
    )


if __name__ == "__main__":
    run()

