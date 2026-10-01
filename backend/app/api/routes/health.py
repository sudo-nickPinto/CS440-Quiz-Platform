from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.errors import APIError

router = APIRouter(tags=["system"])


@router.get("/")
def root() -> dict[str, str]:
    return {"message": "Quiz Platform API"}


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise APIError(
            503,
            "database_unavailable",
            "The API is running, but the database is unavailable.",
        ) from exc
    return {"status": "ok", "components": {"database": "ok"}}
