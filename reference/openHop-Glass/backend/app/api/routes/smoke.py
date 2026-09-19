from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db.models import Repeater, User
from app.db.session import get_db_session

router = APIRouter(prefix="/api/smoke")


@router.get("/db")
def db_smoke(db: Session = Depends(get_db_session)) -> dict:
    db.execute(text("SELECT 1"))
    user_count = db.scalar(select(func.count()).select_from(User)) or 0
    repeater_count = db.scalar(select(func.count()).select_from(Repeater)) or 0
    return {
        "status": "ok",
        "users": user_count,
        "repeaters": repeater_count,
    }
