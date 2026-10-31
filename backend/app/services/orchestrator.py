"""Drives one execution from V1 to a final state with the existing evaluator, gate and lifecycle.

    generating_v1 -> evaluating_v1 (baseline) -> critiquing -> generating_v2 -> evaluating_v2
      accepted                         -> completed
      rejected, max_revisions = 1      -> completed_no_improvement
      rejected, max_revisions = 2      -> critiquing_v2 -> generating_v3 -> evaluating_v3
                                            accepted -> completed, rejected -> completed_no_improvement

Rules:
  * No LLM is involved in any score or decision: evaluation_service measures, acceptance_service decides.
  * Every status change goes through execution_service.transition_execution (with its guards).
  * Starting a run is a compare-and-swap on a "run claimed" marker (`claim_run`): two calls cannot start
    two runs, and the loser gets RUN_ALREADY_STARTED.
  * The run takes a session FACTORY and opens a new short session for every step. It never shares the
    request's session, and no session or database connection is open while waiting on the network.
  * Cancellation is checked between steps; a cancel that lands mid-step makes the next write fail and
    the run stops quietly.
  * Every Generator/Critic call is recorded (`llm_calls`), including failures: role, stage, models,
    prompt SHA-256, error code and exception class. Prompts, replies and the API key are never logged.
  * Budgets per execution: calls and total tokens (settings). Checked before every call, and the token
    total again right after each call. Exceeding either fails the run and keeps the partial record.
  * A restart does not resume anything: an execution claimed by an earlier process is `stalled`.
"""
import logging
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from types import SimpleNamespace

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.agents import critic as critic_agent
from app.agents import generator as generator_agent
from app.agents.context import HiddenCounts, PublicEvidence, hidden_counts, public_evidence
from app.agents.generator import GeneratorOutputError, RevisionContext
from app.config import Settings
from app.database import utcnow
from app.errors import (
    AppError,
    ConflictError,
    EvaluationExecutionDisabledError,
    EvaluationSuiteUnavailableError,
    InvalidTransitionError,
    LLMBudgetExceededError,
    LLMNotConfiguredError,
    NotFoundError,
    RunAlreadyStartedError,
)
from app.lifecycle import TERMINAL_STATUSES, ExecutionStatus as S
from app.llm.client import LLMClient, LLMError, LLMResponse
from app.models import Execution, LLMCall, Task, Version
from app.schemas.critic_feedback import CriticFeedbackInput
from app.services import (
    acceptance_service,
    evaluation_service,
    execution_service,
    suite_service,
    version_service,
)

log = logging.getLogger("app.orchestrator")
SessionFactory = Callable[[], Session]

CALL_BUDGET = "LLM_CALL_BUDGET_EXCEEDED"
TOKEN_BUDGET = "LLM_TOKEN_BUDGET_EXCEEDED"


class _Stopped(Exception):
    """The execution became terminal (normally: cancelled) while the run was in progress."""


class _InvalidComparison(AppError):
    code = "INVALID_COMPARISON"


@dataclass(frozen=True)
class _Evidence:
    public: PublicEvidence
    hidden: HiddenCounts


@dataclass(frozen=True)
class _Best:
    version: Version
    evidence: _Evidence


@contextmanager
def _step(factory: SessionFactory):
    """One short session for one step; always closed."""
    session = factory()
    try:
        yield session
    finally:
        session.close()


# ---- starting --------------------------------------------------------------------------------
def claim_run(session: Session, execution_id: str, instance_id: str) -> None:
    """Compare-and-swap on the run-claimed marker. Exactly one caller can win for an execution.

    UPDATE ... WHERE status = 'queued' AND run_claimed_at IS NULL. The loser gets RunAlreadyStartedError
    (409 RUN_ALREADY_STARTED) if a claim exists, InvalidTransitionError if the execution is not queued."""
    now = utcnow()
    won = session.execute(
        update(Execution)
        .where(Execution.id == execution_id, Execution.status == S.QUEUED.value, Execution.run_claimed_at.is_(None))
        .values(run_claimed_at=now, run_claimed_by=instance_id, updated_at=now)
        .execution_options(synchronize_session=False)
    ).rowcount
    session.commit()
    if won == 1:
        return
    execution = session.get(Execution, execution_id)
    if execution is None:
        raise NotFoundError("execution", execution_id)
    session.refresh(execution)
    if execution.run_claimed_at is not None:
        raise RunAlreadyStartedError("A run was already started for this execution and cannot be started again.")
    raise InvalidTransitionError(f"The execution is '{execution.status}'; only a queued execution can be run.")


def start_run(session: Session, execution_id: str, settings: Settings, instance_id: str) -> Execution:
    """Checks the preconditions, claims the run (compare-and-swap) and moves queued -> generating_v1.
    The API calls this before scheduling the background run, on the request's own session; the
    background run then uses its own sessions. Nothing is claimed if a precondition fails."""
    if not settings.llm_configured:
        raise LLMNotConfiguredError("No Featherless API key is configured, so a run cannot start.")
    if not settings.evaluation_execution_allowed:
        raise EvaluationExecutionDisabledError(
            "Running candidate code is disabled in this environment, so a run cannot start.")
    execution = execution_service.get_execution(session, execution_id)
    if (suite_service.suite_commitment(session, execution.suite_id) is None
            and execution.run_claimed_at is None and execution.status == S.QUEUED.value):
        raise EvaluationSuiteUnavailableError("The execution's committed evaluation suite is not available.")
    claim_run(session, execution_id, instance_id)
    return execution_service.transition_execution(session, execution_id, S.GENERATING_V1)


# ---- helpers (each opens its own session) -----------------------------------------------------
def _status(factory: SessionFactory, execution_id: str) -> Execution:
    with _step(factory) as session:
        execution = session.get(Execution, execution_id)
        session.refresh(execution)
        return execution


def _check(factory: SessionFactory, execution_id: str) -> Execution:
    execution = _status(factory, execution_id)
    if S(execution.status) in TERMINAL_STATUSES:
        raise _Stopped()
    return execution


def _move(factory: SessionFactory, execution_id: str, target: S) -> None:
    _check(factory, execution_id)
    with _step(factory) as session:
        try:
            execution_service.transition_execution(session, execution_id, target)
            return
        except (InvalidTransitionError, ConflictError):
            session.rollback()
    if S(_status(factory, execution_id).status) in TERMINAL_STATUSES:
        raise _Stopped()
    with _step(factory) as session:  # not a cancel: let the real guard error surface
        execution_service.transition_execution(session, execution_id, target)


def _usage(factory: SessionFactory, execution_id: str) -> tuple[int, int]:
    with _step(factory) as session:
        calls, tokens = session.execute(
            select(func.count(LLMCall.id), func.coalesce(func.sum(LLMCall.total_tokens), 0))
            .where(LLMCall.execution_id == execution_id)
        ).one()
        return int(calls), int(tokens)


def _before_call(factory: SessionFactory, execution_id: str, settings: Settings) -> None:
    calls, tokens = _usage(factory, execution_id)
    if calls >= settings.llm_max_calls_per_execution:
        raise LLMBudgetExceededError(
            CALL_BUDGET, f"The execution reached its cap of {settings.llm_max_calls_per_execution} LLM calls.")
    if tokens >= settings.llm_max_total_tokens_per_execution:
        raise LLMBudgetExceededError(
            TOKEN_BUDGET, f"The execution reached its cap of {settings.llm_max_total_tokens_per_execution} tokens.")


def _after_call(factory: SessionFactory, execution_id: str, settings: Settings) -> None:
    _, tokens = _usage(factory, execution_id)
    if tokens > settings.llm_max_total_tokens_per_execution:
        raise LLMBudgetExceededError(
            TOKEN_BUDGET,
            f"The execution used {tokens} tokens, over its cap of {settings.llm_max_total_tokens_per_execution}.")


def _record_call(factory, execution_id, *, role, stage, model, prompt_sha256, response: LLMResponse | None = None,
                 error: Exception | None = None, version_id=None) -> None:
    """One row per call, success or failure. Stores the error code and exception CLASS NAME only."""
    with _step(factory) as session:
        session.add(LLMCall(
            execution_id=execution_id, version_id=version_id, role=role, stage=stage, requested_model=model,
            returned_model=response.returned_model if response else None, prompt_sha256=prompt_sha256,
            outcome="error" if error else "ok", error_code=getattr(error, "code", "LLM_ERROR") if error else None,
            error_class=type(error).__name__ if error else None,
            attempts=getattr(error, "attempts", None) or (response.attempts if response else 1),
            latency_seconds=response.latency_seconds if response else None,
            prompt_tokens=response.prompt_tokens if response else None,
            completion_tokens=response.completion_tokens if response else None,
            total_tokens=response.total_tokens if response else None, created_at=utcnow(),
        ))
        session.commit()


def _generate(factory, llm, settings, execution_id, task, suite, stage: S, revision: RevisionContext | None,
              parent_id: str | None) -> Version:
    _check(factory, execution_id)
    _before_call(factory, execution_id, settings)
    model = settings.featherless_generator_model
    prompt = generator_agent.build_prompt(task, suite, revision)
    phash = generator_agent.prompt_hash(model, generator_agent.SYSTEM, prompt)
    try:  # no session or connection is open here
        response = llm.complete(model=model, system=generator_agent.SYSTEM, user=prompt)
    except LLMError as exc:
        _record_call(factory, execution_id, role="generator", stage=stage.value, model=model, prompt_sha256=phash,
                     error=exc)
        raise
    try:
        code = generator_agent.extract_code(response.text, settings.generator_max_code_chars)
    except GeneratorOutputError as exc:
        _record_call(factory, execution_id, role="generator", stage=stage.value, model=model, prompt_sha256=phash,
                     response=response, error=exc)
        raise
    _check(factory, execution_id)
    with _step(factory) as session:
        try:
            version = version_service.create_version(
                session, execution_id, code, parent_version_id=parent_id,
                generator_model_id=response.returned_model or model, generator_prompt_sha256=phash,
                generation_latency_seconds=response.latency_seconds, generation_prompt_tokens=response.prompt_tokens,
                generation_completion_tokens=response.completion_tokens,
            )
        except ConflictError:
            session.rollback()
            if S(_status(factory, execution_id).status) in TERMINAL_STATUSES:
                raise _Stopped() from None
            raise
    _record_call(factory, execution_id, role="generator", stage=stage.value, model=model, prompt_sha256=phash,
                 response=response, version_id=version.id)
    _after_call(factory, execution_id, settings)
    return version


def _critique(factory, llm, settings, execution_id, stage: S, version: Version, evidence: _Evidence,
              failed_terms: list[dict] | None) -> critic_agent.CriticOutput | None:
    """Returns the validated Critic output, or None (no Critic configured, or output failed the schema)."""
    _check(factory, execution_id)
    model = settings.featherless_critic_model
    if not model:  # no Critic approved: the Generator gets evaluator evidence only (control path)
        return None
    _before_call(factory, execution_id, settings)
    prompt = critic_agent.build_prompt(version.label, version.code, evidence.public, evidence.hidden, failed_terms)
    phash = generator_agent.prompt_hash(model, critic_agent.SYSTEM, prompt)
    try:  # no session or connection is open here
        response = llm.complete(model=model, system=critic_agent.SYSTEM, user=prompt)
    except LLMError as exc:
        _record_call(factory, execution_id, role="critic", stage=stage.value, model=model, prompt_sha256=phash,
                     error=exc, version_id=version.id)
        raise
    output = critic_agent.parse(response.text)
    _check(factory, execution_id)
    with _step(factory) as session:
        version_service.record_critic_feedback(session, version.id, CriticFeedbackInput(
            critic_model_id=(response.returned_model or model)[:200],
            raw_feedback=response.text[:200_000] or "(empty reply)",
            structured_feedback=output.model_dump() if output else None,
            suggested_changes=[output.suggestion] if output else None,
        ))
    _record_call(factory, execution_id, role="critic", stage=stage.value, model=model, prompt_sha256=phash,
                 response=response, version_id=version.id)
    _after_call(factory, execution_id, settings)
    return output


def _evaluate(factory, settings, execution_id, version: Version) -> _Evidence:
    _check(factory, execution_id)
    with _step(factory) as session:
        evaluation = evaluation_service.evaluate_version(session, version.id, settings)
        return _Evidence(public_evidence(evaluation), hidden_counts(evaluation))


def _decide(factory, execution_id, version: Version):
    _check(factory, execution_id)
    with _step(factory) as session:
        return acceptance_service.decide_acceptance(session, version.id)


def _revision(best: _Best, critic_output, rejected_terms=()) -> RevisionContext:
    return RevisionContext(
        base_label=best.version.label, base_code=best.version.code, evidence=best.evidence.public,
        critic_suggestion=critic_output.suggestion if critic_output else None,
        critic_lesson=critic_output.lesson if critic_output else None, rejected_terms=tuple(rejected_terms),
    )


def _fail(factory: SessionFactory, execution_id: str, error_code: str, message: str) -> None:
    try:
        with _step(factory) as session:
            if S(session.get(Execution, execution_id).status) not in TERMINAL_STATUSES:
                execution_service.fail_execution(session, execution_id, error_code, message)
    except (InvalidTransitionError, ConflictError):
        pass  # it became terminal concurrently (for example cancelled): leave it as it is


# ---- the run ---------------------------------------------------------------------------------
def run_execution(factory: SessionFactory, execution_id: str, llm: LLMClient, settings: Settings,
                  instance_id: str) -> Execution:
    """Claims and runs a QUEUED execution to a terminal state. Anything else is refused
    (RunAlreadyStartedError if a run was ever claimed, InvalidTransitionError otherwise)."""
    with _step(factory) as session:
        start_run(session, execution_id, settings, instance_id)
    return continue_run(factory, execution_id, llm, settings, instance_id)


def continue_run(factory: SessionFactory, execution_id: str, llm: LLMClient, settings: Settings,
                 instance_id: str) -> Execution:
    """Runs an execution THIS process has already claimed and moved to generating_v1 (the API calls
    start_run on the request, then this in the background). It will not touch a run claimed by another
    process, and it never resumes a partly finished run."""
    execution = _status(factory, execution_id)
    with _step(factory) as session:
        has_versions = bool(version_service.list_versions(session, execution_id))
    if (execution.status != S.GENERATING_V1.value or execution.run_claimed_by != instance_id or has_versions):
        raise InvalidTransitionError(
            f"The execution is '{execution.status}' and is not a run claimed by this process; "
            "interrupted runs are never resumed automatically.")
    try:
        _drive(factory, execution_id, llm, settings)
    except _Stopped:
        log.info("execution %s stopped: it became terminal during the run", execution_id)
    except LLMError as exc:
        _fail(factory, execution_id, exc.code, exc.message)
    except GeneratorOutputError as exc:
        _fail(factory, execution_id, exc.code, str(exc))
    except AppError as exc:
        _fail(factory, execution_id, exc.code, exc.message)
    except Exception as exc:  # never leave a run half-way without a record of why
        # Log the exception class only: the message could echo prompt or code text.
        log.error("execution %s: unexpected orchestrator error (%s)", execution_id, type(exc).__name__)
        _fail(factory, execution_id, "ORCHESTRATOR_ERROR", "The run stopped because of an unexpected internal error.")
    return _status(factory, execution_id)


def _drive(factory: SessionFactory, eid: str, llm: LLMClient, settings: Settings) -> None:
    with _step(factory) as session:
        execution = session.get(Execution, eid)
        row = session.get(Task, execution.task_id)
        task = SimpleNamespace(title=row.title, description=row.description, requirements=list(row.requirements),
                               language=row.language, starter_code=row.starter_code)
        suite = suite_service.evaluation_suite(session, execution.suite_id, settings)
        max_revisions = execution.max_revisions
    if suite is None:
        raise EvaluationSuiteUnavailableError("The execution's committed evaluation suite is not available.")

    # V1: the baseline
    v1 = _generate(factory, llm, settings, eid, task, suite, S.GENERATING_V1, None, None)
    _move(factory, eid, S.EVALUATING_V1)
    e1 = _evaluate(factory, settings, eid, v1)
    d1 = _decide(factory, eid, v1)
    if not d1.baseline:
        raise AppError(f"V1 could not be established as the baseline ({d1.outcome}).")
    best = _Best(v1, e1)

    # V2
    _move(factory, eid, S.CRITIQUING)
    c1 = _critique(factory, llm, settings, eid, S.CRITIQUING, v1, e1, None)
    _move(factory, eid, S.GENERATING_V2)
    v2 = _generate(factory, llm, settings, eid, task, suite, S.GENERATING_V2, _revision(best, c1), best.version.id)
    _move(factory, eid, S.EVALUATING_V2)
    e2 = _evaluate(factory, settings, eid, v2)
    d2 = _decide(factory, eid, v2)
    if d2.outcome == "validated_improvement":
        _move(factory, eid, S.COMPLETED)  # stop on acceptance
        return
    if d2.outcome == "invalid_comparison":
        raise _InvalidComparison(d2.reason)
    if max_revisions < 2:
        _move(factory, eid, S.COMPLETED_NO_IMPROVEMENT)  # budget exhausted
        return

    # V3, after the rejected V2. The Critic sees V2's failed term ids and their hidden-safe messages;
    # the Generator sees only the term ids.
    _move(factory, eid, S.CRITIQUING_V2)
    failed = [t.as_dict() for t in d2.failed_terms]
    c2 = _critique(factory, llm, settings, eid, S.CRITIQUING_V2, v2, e2, failed)
    _move(factory, eid, S.GENERATING_V3)
    v3 = _generate(factory, llm, settings, eid, task, suite, S.GENERATING_V3,
                   _revision(best, c2, [t["term"] for t in failed]), best.version.id)
    _move(factory, eid, S.EVALUATING_V3)
    _evaluate(factory, settings, eid, v3)
    d3 = _decide(factory, eid, v3)
    if d3.outcome == "validated_improvement":
        _move(factory, eid, S.COMPLETED)
    elif d3.outcome == "invalid_comparison":
        raise _InvalidComparison(d3.reason)
    else:
        _move(factory, eid, S.COMPLETED_NO_IMPROVEMENT)
