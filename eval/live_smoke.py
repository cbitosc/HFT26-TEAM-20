"""Live end-to-end runs against Featherless. NOT run by pytest. Spends real API credit.

Gate: runs only when AUTOEVOLVE_LIVE_SMOKE=1 and FEATHERLESS_API_KEY are both set. Every run uses the real
evaluator and gate on a throwaway SQLite file in a temporary directory, and the configured models
(FEATHERLESS_GENERATOR_MODEL; FEATHERLESS_CRITIC_MODEL is optional: no Critic call is made without it).

Options (environment variables):
  AUTOEVOLVE_SMOKE_STARTER=flawed   seed each task with the `flawed` fixture as starter code, so V1 starts
                                    from code that fails public tests. Unset: no starter code.
  AUTOEVOLVE_SMOKE_REPEATS=N        number of runs, executed one after another. Default 1, maximum 5.

Cost note: every run is a separate execution with its own caps (LLM_MAX_CALLS_PER_EXECUTION, default 6, and
LLM_MAX_TOTAL_TOKENS_PER_EXECUTION, default 40,000), so N runs can spend up to N times that.

Output is counts, statuses and aggregate scores only. It never prints the API key, prompts, replies, code, or
any hidden test id, name or detail (hidden tests appear only as passed/total counts).

    $env:AUTOEVOLVE_LIVE_SMOKE = "1"
    $env:AUTOEVOLVE_SMOKE_STARTER = "flawed"
    $env:AUTOEVOLVE_SMOKE_REPEATS = "3"
    backend\\.venv\\Scripts\\python.exe eval\\live_smoke.py
"""
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

STARTER_FIXTURES = {"flawed": BACKEND / "tests" / "fixtures" / "flawed.py"}
MAX_REPEATS = 5
SUITE_ID = "python-merge-intervals-v1"


def read_options() -> tuple[str | None, int] | None:
    """Returns (starter name or None, repeats), or None after printing why the options are invalid."""
    starter = os.environ.get("AUTOEVOLVE_SMOKE_STARTER", "").strip()
    if starter and starter not in STARTER_FIXTURES:
        print(f"invalid AUTOEVOLVE_SMOKE_STARTER (allowed: {', '.join(sorted(STARTER_FIXTURES))}, or unset)")
        return None
    raw = os.environ.get("AUTOEVOLVE_SMOKE_REPEATS", "").strip() or "1"
    try:
        repeats = int(raw)
    except ValueError:
        print(f"invalid AUTOEVOLVE_SMOKE_REPEATS: must be an integer from 1 to {MAX_REPEATS}")
        return None
    if not 1 <= repeats <= MAX_REPEATS:
        print(f"invalid AUTOEVOLVE_SMOKE_REPEATS={repeats}: must be from 1 to {MAX_REPEATS}")
        return None
    return (starter or None), repeats


def main() -> int:
    if os.environ.get("AUTOEVOLVE_LIVE_SMOKE") != "1":
        print("skipped: set AUTOEVOLVE_LIVE_SMOKE=1 to make real (billed) runs")
        return 0
    if not os.environ.get("FEATHERLESS_API_KEY", "").strip():
        print("skipped: FEATHERLESS_API_KEY is not set")
        return 0
    options = read_options()
    if options is None:
        return 2
    starter_name, repeats = options
    starter_code = STARTER_FIXTURES[starter_name].read_text(encoding="utf-8") if starter_name else None

    from sqlalchemy import select

    from app.config import Settings
    from app.database import create_db_engine, init_db, make_session_factory
    from app.evaluation.engine import evaluate_source
    from app.evaluation.suites import get_suite
    from app.llm.client import make_featherless_client
    from app.models import CriticFeedback, LLMCall, Version
    from app.schemas.task import TaskCreate
    from app.services import evaluation_service, execution_service, orchestrator, task_service, version_service

    with tempfile.TemporaryDirectory(prefix="autoevolve_live_") as tmp:
        settings = Settings(database_url=f"sqlite:///{(Path(tmp) / 'live.db').as_posix()}", app_env="development")
        engine = create_db_engine(settings.database_url)
        init_db(engine)
        factory = make_session_factory(engine)

        print(f"runs: {repeats}, sequential")
        print(f"starter code: {starter_name or 'none'}")
        print(f"generator model requested: {settings.featherless_generator_model}")
        print(f"critic model configured: {'yes' if settings.featherless_critic_model else 'no (control path)'}")
        print(f"per-run caps: {settings.llm_max_calls_per_execution} calls, "
              f"{settings.llm_max_total_tokens_per_execution} tokens")
        if starter_code is not None:
            suite = get_suite(SUITE_ID)
            outcome = evaluate_source(starter_code, suite, evaluation_service.limits_from(settings))
            print(f"starter code scored locally (no API call): hidden {outcome.tests_passed}/{outcome.tests_total}, "
                  f"public {outcome.public_tests_passed}/{outcome.public_tests_total}")

        runs = []
        for number in range(1, repeats + 1):
            print(f"--- run {number} of {repeats}")
            record = {"status": "crashed", "improved": False, "calls": 0, "tokens": 0, "failed_calls": 0,
                      "first": None, "best": None}
            session = factory()
            try:
                task = task_service.create_task(session, TaskCreate(
                    title="Merge intervals",
                    description="Implement merge_intervals(intervals): merge overlapping or touching (start, end) "
                                "integer intervals and return a new sorted list of tuples.",
                    requirements=["Merge overlapping and touching intervals", "Do not mutate the input",
                                  "Raise TypeError for a non-list or malformed elements",
                                  "Raise ValueError when start > end"],
                    language="python", category="algorithms", evaluation_suite_id=SUITE_ID,
                    starter_code=starter_code))
                execution = execution_service.create_execution(session, task.id, settings=settings)
                started = time.perf_counter()
                result = orchestrator.run_execution(factory, execution.id, make_featherless_client(settings),
                                                    settings, instance_id=uuid.uuid4().hex)
                elapsed = time.perf_counter() - started

                record["status"] = result.status
                print(f"status: {result.status}"
                      + (f" ({result.error_code} at {result.error_stage})" if result.error_code else ""))
                scores = {}
                for v in version_service.list_versions(session, execution.id):
                    evaluations = version_service.list_evaluations(session, v.id)
                    ev = evaluations[-1] if evaluations else None
                    if ev:
                        scores[v.id] = ev.overall_score
                        text = (f"hidden {ev.tests_passed}/{ev.tests_total}, public {ev.public_tests_passed}/"
                                f"{ev.public_tests_total}, S={ev.overall_score:.2f}")
                    else:
                        text = "not evaluated"
                    print(f"{v.label}: {text}, decision {v.acceptance_status}, returned model {v.generator_model_id}")
                    if v.sequence == 1:
                        record["first"] = scores.get(v.id)
                best = session.get(Version, result.best_version_id) if result.best_version_id else None
                if best is not None:
                    record["best"] = scores.get(best.id)
                    # An improvement over V1 means the best version is an accepted revision, not the baseline.
                    record["improved"] = best.sequence >= 2 and best.acceptance_status == "accepted"
                calls = session.scalars(select(LLMCall).where(LLMCall.execution_id == execution.id)).all()
                record["calls"] = len(calls)
                record["failed_calls"] = sum(c.outcome == "error" for c in calls)
                record["tokens"] = sum(c.total_tokens or 0 for c in calls)
                feedback = session.scalars(
                    select(CriticFeedback).join(Version, CriticFeedback.version_id == Version.id)
                    .where(Version.execution_id == execution.id)).all()
                print(f"llm calls: {record['calls']} ({record['failed_calls']} failed), "
                      f"tokens {record['tokens']}, critic feedback rows {len(feedback)}")
                print(f"improved over V1: {'yes' if record['improved'] else 'no'}; wall time {elapsed:.1f}s")
            except Exception as exc:  # report the class only: a message could echo prompt or code text
                print(f"run crashed: {type(exc).__name__}")
            finally:
                session.close()
            runs.append(record)

        engine.dispose()

    print("=== summary")
    count = lambda name: sum(1 for r in runs if r["status"] == name)  # noqa: E731
    improved = sum(r["improved"] for r in runs)
    print(f"runs: {len(runs)}")
    print(f"ended with an accepted improvement over V1: {improved} of {len(runs)}")
    print(f"completed: {count('completed')}, completed_no_improvement: {count('completed_no_improvement')}, "
          f"failed: {count('failed')}, cancelled: {count('cancelled')}, crashed: {count('crashed')}")
    gains = [r["best"] - r["first"] for r in runs if r["improved"] and r["first"] is not None and r["best"] is not None]
    if gains:
        print(f"score gain over V1 in the {len(gains)} improved run(s): min {min(gains):.2f}, max {max(gains):.2f}")
    print(f"total llm calls: {sum(r['calls'] for r in runs)} ({sum(r['failed_calls'] for r in runs)} failed), "
          f"total tokens {sum(r['tokens'] for r in runs)}")
    return 1 if count("crashed") else 0


if __name__ == "__main__":
    sys.exit(main())
