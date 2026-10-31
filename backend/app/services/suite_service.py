"""Create and resolve evaluation suites: the backend-registered ones and user-uploaded ones.

Resolution has two entry points on purpose:
  * `suite_commitment` returns only the id and the three committed hashes. It does NOT decrypt hidden
    tests, so recording an execution's commitment at run start never touches the plaintext.
  * `evaluation_suite` returns the full EvaluationSuite, decrypting an uploaded suite's hidden tests.
    This is called only inside the backend (evaluator and orchestrator) at evaluation time.

A reconstructed uploaded suite is verified against its stored hashes, so a tampered row (or a wrong
decryption key, caught earlier by Fernet) can never be evaluated as if it were the committed suite.
"""
import json
import secrets
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app import sealing
from app.errors import EvaluationSuiteUnavailableError, HiddenSuiteUnavailableError, SuiteUploadRejectedError
from app.evaluation import suite_io
from app.evaluation.policy import check_suite_against_policy
from app.evaluation.suite import EvaluationSuite
from app.evaluation.suites import get_suite
from app.models import UploadedSuite


@dataclass(frozen=True)
class SuiteCommitment:
    id: str
    suite_hash: str
    public_suite_hash: str
    hidden_suite_hash: str


def _new_suite_id() -> str:
    return "u" + secrets.token_hex(16)  # matches the suite-id regex ^[a-z][a-z0-9_.-]{0,63}$


def create_uploaded_suite(session: Session, upload: dict, settings) -> UploadedSuite:
    """Validate a declarative upload, seal its hidden tests, and store it. Raises SuiteUploadRejectedError
    (422) for a bad suite, HiddenSuiteUnavailableError (409) when encryption is not available."""
    if not sealing.encryption_available(settings):
        raise HiddenSuiteUnavailableError(
            "Hidden-suite encryption is not available (no HIDDEN_SUITE_KEY configured), so an uploaded "
            "suite cannot be sealed. Use a registered suite, or configure the key."
        )
    suite_id = _new_suite_id()
    try:
        suite = suite_io.build_suite(suite_id, upload)
        suite.validate()
        check_suite_against_policy(suite)  # >= 1 public, >= 1 hidden, hidden count within the delta rule
    except (suite_io.SuiteUploadError, ValueError) as exc:
        raise SuiteUploadRejectedError(str(exc)) from exc

    hidden_json = json.dumps(suite_io.tests_to_dicts(suite.hidden_tests)).encode("utf-8")
    row = UploadedSuite(
        id=suite_id,
        spec=suite_io.spec_to_dict(suite),
        public_tests=suite_io.tests_to_dicts(suite.public_tests),
        hidden_tests_sealed=sealing.encrypt(settings, hidden_json),
        public_test_count=len(suite.public_tests),
        hidden_test_count=len(suite.hidden_tests),
        suite_hash=suite.suite_hash,
        public_suite_hash=suite.public_suite_hash,
        hidden_suite_hash=suite.hidden_suite_hash,
    )
    session.add(row)
    session.commit()
    return row


def suite_commitment(session: Session, suite_id: str | None) -> SuiteCommitment | None:
    """The id and committed hashes for a registered or uploaded suite, without decrypting anything."""
    registered = get_suite(suite_id)
    if registered is not None:
        return SuiteCommitment(registered.id, registered.suite_hash, registered.public_suite_hash,
                               registered.hidden_suite_hash)
    row = session.get(UploadedSuite, suite_id) if suite_id else None
    if row is None:
        return None
    return SuiteCommitment(row.id, row.suite_hash, row.public_suite_hash, row.hidden_suite_hash)


def evaluation_suite(session: Session, suite_id: str | None, settings) -> EvaluationSuite | None:
    """The full suite, decrypting an uploaded suite's hidden tests. Backend-only; never behind an endpoint.
    Raises EvaluationSuiteUnavailableError if a stored suite no longer matches its committed hashes."""
    registered = get_suite(suite_id)
    if registered is not None:
        return registered
    row = session.get(UploadedSuite, suite_id) if suite_id else None
    if row is None:
        return None
    hidden_dicts = json.loads(sealing.decrypt(settings, row.hidden_tests_sealed).decode("utf-8"))
    suite = suite_io.reconstruct(row.id, row.spec, row.public_tests, hidden_dicts)
    if (suite.suite_hash, suite.public_suite_hash, suite.hidden_suite_hash) != (
            row.suite_hash, row.public_suite_hash, row.hidden_suite_hash):
        raise EvaluationSuiteUnavailableError(
            f"The stored uploaded suite '{row.id}' no longer matches the hashes recorded at upload; it will "
            "not be used."
        )
    return suite
