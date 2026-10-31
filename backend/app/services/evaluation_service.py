"""Evaluate a stored version against its execution's committed suite and persist the result.

This is the ONLY producer of evaluation records in the running application. It takes a version id
and settings; it accepts no scores. Everything stored is measured by `evaluation.engine`, and every
evaluation carries a full provenance record (PRD FR-3).
"""
from sqlalchemy.orm import Session

from app.config import Settings
from app.database import utcnow
from app.errors import (
    CodeHashMismatchError,
    ConflictError,
    EvaluationExecutionDisabledError,
    EvaluationSuiteUnavailableError,
    NotFoundError,
)
from app.evaluation import policy
from app.evaluation.engine import evaluate_source
from app.evaluation.execution import RunLimits
from app.evaluation.provenance import config_hash, environment, evaluator_config
from app.evaluation.suites import get_suite
from app.hashing import code_sha256
from app.lifecycle import TERMINAL_STATUSES, ExecutionStatus
from app.models import Evaluation, Execution
from app.schemas.evaluation import EvaluationInput, OperationalMetricsInput, TestFailureDetail, TestOutcome
from app.services import version_service


def limits_from(settings: Settings) -> RunLimits:
    return RunLimits(per_run_timeout=settings.evaluation_timeout_seconds,
                     total_timeout=settings.evaluation_total_timeout_seconds)


def evaluate_version(session: Session, version_id: str, settings: Settings, *, suite=None) -> Evaluation:
    """`suite` exists so tests can inject a small suite; production uses the execution's committed suite."""
    version = version_service.get_version(session, version_id)
    execution = session.get(Execution, version.execution_id)
    if execution is None:
        raise NotFoundError("execution", version.execution_id)
    if ExecutionStatus(execution.status) in TERMINAL_STATUSES:
        raise ConflictError(f"The execution is {execution.status}; its versions are no longer evaluated.")
    if not settings.evaluation_execution_allowed:
        raise EvaluationExecutionDisabledError(
            "Running candidate code is disabled in this environment. Evaluation executes untrusted code in a "
            "subprocess, which is not a sandbox; set ALLOW_UNSANDBOXED_EVALUATION=true only on a machine you "
            "can afford to lose."
        )

    if suite is None:
        if not execution.suite_id:
            raise EvaluationSuiteUnavailableError("This execution has no committed evaluation suite.")
        from app.services import suite_service  # lazy: avoids an import cycle

        suite = suite_service.evaluation_suite(session, execution.suite_id, settings)  # decrypts an uploaded suite
        if suite is None:
            raise EvaluationSuiteUnavailableError(f"Evaluation suite '{execution.suite_id}' is not available.")
        if suite.suite_hash != execution.suite_hash:
            # The suite changed after the run started: evaluating against it would not be the committed suite.
            raise EvaluationSuiteUnavailableError(
                f"Evaluation suite '{suite.id}' no longer matches the hash committed when this run started."
            )
    if not suite.tests or not suite.hidden_tests:
        # A version with no applicable hidden tests must never look perfect. The database also forbids tests_total = 0.
        raise EvaluationSuiteUnavailableError(f"Evaluation suite '{suite.id}' contains no hidden tests.")

    # Bind the result to the exact bytes that run. If the stored code no longer matches the hash
    # recorded when the version was created, the code was changed after the fact: refuse.
    session.refresh(version)  # hash what is in the database, never a cached copy
    source = version.code
    source_hash = code_sha256(source)
    if source_hash != version.code_sha256:
        raise CodeHashMismatchError(
            f"The stored code of {version.label} no longer matches the SHA-256 recorded when it was created; "
            "it will not be evaluated."
        )

    limits = limits_from(settings)
    outcome = evaluate_source(source, suite, limits)
    config = evaluator_config(limits)
    cfg_hash = config_hash(config)

    data = EvaluationInput(
        tests_passed=outcome.tests_passed,
        tests_total=outcome.tests_total,
        code_sha256=source_hash,
        public_tests_passed=outcome.public_tests_passed,
        public_tests_total=outcome.public_tests_total,
        correctness_score=outcome.correctness_score,
        code_quality_score=outcome.code_quality_score,
        failure_details=[TestFailureDetail(**d) for d in outcome.failure_details],
        suite_id=outcome.suite_id,
        suite_hash=outcome.suite_hash,
        evaluator_version=outcome.evaluator_version,
        evaluator_config_hash=cfg_hash,
        scoring_rule_version=policy.SCORING_RULE_VERSION,
        provenance={
            "suite_id": outcome.suite_id,
            "suite_hash": outcome.suite_hash,
            "public_suite_hash": outcome.public_suite_hash,
            "hidden_suite_hash": outcome.hidden_suite_hash,
            "evaluator_version": outcome.evaluator_version,
            "evaluator_config_hash": cfg_hash,
            "evaluator_config": config,
            "scoring_rule_version": policy.SCORING_RULE_VERSION,
            "scoring_rule_hash": policy.scoring_rule_hash(),
            "delta": policy.DELTA,
            "environment": environment(),
            "execution_id": execution.id,
            "version_id": version.id,
            "code_sha256": source_hash,
            "evaluated_at": utcnow().isoformat(),
            "matches_commitment": {
                "suite": outcome.suite_hash == execution.suite_hash,
                "evaluator_config": cfg_hash == execution.evaluator_config_hash,
                "scoring_rule": policy.SCORING_RULE_VERSION == execution.scoring_rule_version,
            },
        },
        test_results=[TestOutcome(**r) for r in outcome.test_results],
        score_breakdown=outcome.breakdown,
        # Operational data, stored apart from the score. Only wall time exists for a local evaluation.
        operational=OperationalMetricsInput(execution_time_seconds=outcome.elapsed_seconds),
    )
    return version_service.record_evaluation(session, version_id, data)
