"""Read-only. Versions, evaluations and Critic feedback are written only by backend components
(never by API clients), so a client cannot submit a score or a "result"."""
from fastapi import APIRouter

from app.api.deps import DbSession
from app.schemas.common import Envelope, ok
from app.schemas.critic_feedback import CriticFeedbackRead
from app.schemas.evaluation import EvaluationRead
from app.schemas.version import VersionRead
from app.services import version_service

router = APIRouter(prefix="/versions", tags=["versions"])


@router.get("/{version_id}", response_model=Envelope[VersionRead])
def get_version(version_id: str, db: DbSession):
    return ok(VersionRead.model_validate(version_service.get_version(db, version_id)))


@router.get("/{version_id}/evaluations", response_model=Envelope[list[EvaluationRead]])
def list_evaluations(version_id: str, db: DbSession):
    return ok([EvaluationRead.from_model(e) for e in version_service.list_evaluations(db, version_id)])


@router.get("/{version_id}/critic-feedback", response_model=Envelope[list[CriticFeedbackRead]])
def list_critic_feedback(version_id: str, db: DbSession):
    return ok([CriticFeedbackRead.model_validate(f) for f in version_service.list_critic_feedback(db, version_id)])
