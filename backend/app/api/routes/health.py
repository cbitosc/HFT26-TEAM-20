import logging

from fastapi import APIRouter, Request
from sqlalchemy.exc import SQLAlchemyError

from app import __version__
from app.api.deps import DbSession
from app.api.error_handlers import error_response
from app.database import check_connection, utcnow
from app.schemas.common import Envelope, ok

router = APIRouter(tags=["health"])
logger = logging.getLogger("autoevolve")


@router.get("/health", response_model=Envelope[dict])
def health(request: Request, db: DbSession):
    try:
        check_connection(db)
    except SQLAlchemyError:
        logger.exception("Health check: database unavailable")
        return error_response(503, "DATABASE_UNAVAILABLE", "The database is not reachable.")
    return ok(
        {
            "status": "ok",
            "database": "connected",
            "environment": request.app.state.settings.app_env,
            "version": __version__,
            "timestamp": utcnow(),
        }
    )
