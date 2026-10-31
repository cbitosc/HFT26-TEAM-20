# AutoEvolve Backend

FastAPI + SQLite backend for AutoEvolve Protocol (Milestones 05 and 06, aligned with the PRD).

**Implemented:** tasks, executions with a validated lifecycle, status history and a commitment recorded at creation; versions; the deterministic evaluator (public and hidden tests, run in a subprocess, with full provenance); the acceptance policy with typed evidence and invalid comparisons; the proof-stage and no-improvement guards; Critic feedback storage; health check; configuration. See `../docs/EVALUATION_ENGINE.md`.

**Also implemented (Milestone 07):** code-hash binding and local evidence bundles; the Featherless client, Generator, Critic and orchestrator (`POST /api/executions/{id}/run`). No LLM output is a score or a decision.

**Runs and restarts:** a run is claimed by a compare-and-swap, so two calls cannot start two runs (409 `RUN_ALREADY_STARTED`). Runs live in the server process. **After a restart an unfinished run is not resumed**; it shows `"stalled": true` in the execution GET responses and can be cancelled.

**Not implemented yet:** ZK proofs, IPFS, egress gate, blockchain, lesson validator, Agent B, capabilities, the web dashboard, cross-agent memory retrieval, a container sandbox. Creating an execution records a `queued` row and its commitment; `POST /api/executions/{id}/run` runs it.

**Security:** evaluating a version executes its code in a subprocess with time limits. That is **not a security sandbox**. In `production` it is refused unless `ALLOW_UNSANDBOXED_EVALUATION=true`.

## Requirements

Python 3.12. All commands below are PowerShell, run from this `backend/` directory.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env     # optional; defaults work without it
```

The virtual environment lives in `backend/.venv` and is git-ignored. Nothing is installed globally.

## Configuration

Settings come from environment variables or `backend/.env` (git-ignored). `.env.example` has placeholders only; never put a real key in it.

| Variable | Default | Notes |
|---|---|---|
| `APP_ENV` | `development` | `development`, `test` or `production` |
| `DATABASE_URL` | `sqlite:///<backend>/data/autoevolve.db` | SQLite only. A relative path resolves against the working directory |
| `FEATHERLESS_API_KEY` | unset | Needed only to run the orchestrator (`POST /api/executions/{id}/run` returns 503 without it). Never logged, stored or returned |
| `FEATHERLESS_BASE_URL` | `https://api.featherless.ai/v1` | |
| `FEATHERLESS_GENERATOR_MODEL` | `Qwen/Qwen2.5-7B-Instruct` | Provisional choice, configurable |
| `FEATHERLESS_CRITIC_MODEL` | unset | No Critic model is approved, so there is no default. Unset: the critique steps make no call and the Generator gets evaluator evidence only |
| `API_TIMEOUT_SECONDS` | `60` | |
| `EVALUATION_TIMEOUT_SECONDS` | `10` | Per interpreter run. Part of the evaluator configuration hash, so changing it makes new evaluations incomparable with an execution created under the old value |
| `EVALUATION_TOTAL_TIMEOUT_SECONDS` | `60` | Whole evaluation of one version. Also part of the configuration hash |
| `ALLOW_UNSANDBOXED_EVALUATION` | unset | Unset: allowed in `development`/`test`, refused in `production`. `true`/`false` overrides |
| `LLM_MAX_RETRIES` | `2` | Extra attempts after the first, on timeouts, connection errors, 429 and 5xx |
| `LLM_BACKOFF_SECONDS` | `1.0` | First retry delay; doubles each retry |
| `LLM_MAX_TOKENS` | `2048` | `max_tokens` per completion. Temperature is fixed at 0 in code |
| `GENERATOR_MAX_CODE_CHARS` | `20000` | Longer Generator code is rejected (`GENERATOR_OUTPUT_INVALID`) |
| `HIDDEN_SUITE_KEY` | unset | Fernet key for encrypting uploaded hidden tests. In `production` a missing key means suite uploads are refused; `development`/`test` generate a key file instead |
| `HIDDEN_SUITE_KEY_FILE` | `<backend>/.hidden_suite_key` | Where dev/test writes a generated key (git-ignored). Never printed or logged |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:5173` | Comma-separated browser origin allowlist. No wildcard; credentials off |
| `LLM_MAX_CALLS_PER_EXECUTION` | `6` | Cap on Generator + Critic calls per execution (a normal run makes at most 5). Exceeding it fails the run (`LLM_CALL_BUDGET_EXCEEDED`) |
| `LLM_MAX_TOTAL_TOKENS_PER_EXECUTION` | `40000` | Cap on total tokens per execution, checked before each call and again after it (`LLM_TOKEN_BUDGET_EXCEEDED`) |

## Database initialisation

Tables are created automatically on startup if they are missing, and the database directory is created when needed. To initialise explicitly:

```powershell
.\.venv\Scripts\python.exe -m app.init_db
```

There is no migration tool yet; the schema is created with `create_all`, which does not alter existing tables. For this prototype, delete `data/autoevolve.db` after a schema change.

## Run the server

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

- API: `http://127.0.0.1:8000/api`
- Interactive documentation: `http://127.0.0.1:8000/docs` (also `/redoc` and `/openapi.json`)
- Endpoint reference: `../docs/API_CONTRACT.md`

Quick check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

## Run the tests

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Every test builds its own app on a temporary SQLite file, ignores `backend/.env` and any `FEATHERLESS_*` variables in your shell, and makes no network calls.

## Layout

```
app/
  main.py          app factory, lifespan (creates the database)
  config.py        settings (the one place model IDs are configured)
  database.py      engine (foreign keys on), session factory, UTC datetime type
  init_db.py       `python -m app.init_db` explicit schema creation
  lifecycle.py     execution states and the allowed transitions
  scoring.py       the approved 50/30/20 aggregation of evaluation components
  evaluation/      suites (public/hidden), subprocess runner, engine, static quality checks,
                   provenance, policy (delta, terms), gate (pure acceptance rule)
  errors.py        domain errors mapped to HTTP statuses
  models/          SQLAlchemy tables
  schemas/         Pydantic request/response and internal input models
  services/        business logic (task, execution, version/evaluation/feedback, evaluation, acceptance,
                   bundle, orchestrator)
  llm/             LLMClient interface and the Featherless client (httpx2, temperature 0, retries)
  agents/          Generator and Critic prompts and parsing; context.py is the hidden-safe prompt input
  changelog.py     deterministic revision changelog from the unified diff
  api/             routes, dependencies, error handlers
tests/             pytest suite (fixtures/ holds the real candidate sources used by the engine tests)
```

## Design notes

- **Clients cannot write results.** There are no endpoints that accept versions, scores, verdicts or Critic feedback. `POST /api/versions/{id}/evaluate` and `/acceptance-decision` only trigger the backend evaluator and policy; their bodies must be empty. `services/version_service.py` derives the overall score from the components.
- **Hidden tests** are returned only as counts. Per-test results and failure details are public-only.
- **Lifecycle:** `services/execution_service.py::transition_execution` is the only way a status changes. It rejects illegal transitions and uses a compare-and-swap `UPDATE` so concurrent transitions cannot both succeed.
- **Terminal states:** `completed`, `completed_no_improvement`, `failed`, `cancelled`. `completed_no_improvement` means every permitted revision (`executions.max_revisions`, 1 or 2) was evaluated and rejected; the service refuses to enter it while another revision is permitted, or if any revision was accepted, undecided or unevaluated. It is not a failure and carries no error information.
- **Evaluator-led revisions:** `services/acceptance_service.py` applies the policy (`app/evaluation/policy.py`, `gate.py`): preconditions against the execution's commitment, then no test regression, no dimension regression and S_new >= S_old + 1.0. Outcomes are `baseline`, `validated_improvement`, `rejected_attempt` (evidence records) or `invalid_comparison` (separate table, version stays pending). Decision, evidence and best pointer are written in one transaction. `version_service.decide_version` is a low-level recorder kept for tests; pipeline code must not use it.
- **Proof stage:** `zk_proof` requires a `validated_improvement` evidence record for the best revision and a re-check of the evaluations.
- **Score integrity:** the database rejects an evaluation whose stored pass rate or overall score does not match the approved formula (`app/scoring.py`) to within 1e-9, even for a raw SQL write.
- **Operational data** (time, tokens, cost) is stored in its own table and never feeds the deterministic score.
