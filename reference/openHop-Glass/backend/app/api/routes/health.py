from datetime import UTC, datetime

from fastapi import APIRouter

from app.config import get_settings

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.app_env,
        "contract_version": settings.contract_version,
        "timestamp": datetime.now(UTC).isoformat(),
    }

