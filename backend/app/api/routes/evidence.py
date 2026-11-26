"""Evidence bundles: local, hidden-safe, hash-addressed exports of one evidence record.

A client may ask for a bundle to be built (POST, empty body) and read it (GET). It can never send
bundle content, scores or hashes. Nothing is uploaded anywhere."""
import json

from fastapi import APIRouter, Query, Response

from app.api.deps import DbSession
from app.errors import NotFoundError
from app.models import EvidenceRecord
from app.schemas.acceptance import BundleRequest, EvidenceBundleRead
from app.schemas.common import Envelope, ok
from app.services import bundle_service

router = APIRouter(prefix="/evidence", tags=["evidence"])

IncludeCode = Query(default=True, description="Include both versions' source and the diff (false: hashes only)")


def _read(db, bundle) -> EvidenceBundleRead:
    record = db.get(EvidenceRecord, bundle.evidence_record_id)
    check = bundle_service.verify(bundle)
    try:
        parsed = json.loads(bundle.bundle_json)
    except ValueError:
        parsed = {}
    return EvidenceBundleRead(
        id=bundle.id, evidence_record_id=bundle.evidence_record_id, status=record.status,
        include_code=bundle.include_code, bundle_sha256=bundle.bundle_sha256, bundle_json=bundle.bundle_json,
        bundle=parsed, created_at=bundle.created_at, **check,
    )


@router.post("/{record_id}/bundle", status_code=201, response_model=Envelope[EvidenceBundleRead])
def create_bundle(record_id: str, response: Response, db: DbSession, include_code: bool = IncludeCode,
                  body: BundleRequest | None = None):
    """Builds the bundle (201) or returns the existing identical one (200)."""
    bundle, created = bundle_service.build_or_get_bundle(db, record_id, include_code=include_code)
    if not created:
        response.status_code = 200
    return ok(_read(db, bundle))


@router.get("/{record_id}/bundle", response_model=Envelope[EvidenceBundleRead])
def get_bundle(record_id: str, db: DbSession, include_code: bool = IncludeCode):
    record = bundle_service.get_exportable_record(db, record_id)
    bundle = bundle_service.find_bundle(db, record.id, include_code)
    if bundle is None:
        raise NotFoundError("evidence_bundle", record_id)
    return ok(_read(db, bundle))
