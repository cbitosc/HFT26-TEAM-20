# AutoEvolve Backend

FastAPI + SQLite foundation for AutoEvolve Protocol (Milestone 05).

**Implemented:** tasks, executions with a validated lifecycle and status history, versions, evaluations, Critic feedback storage, health check, configuration.

**Not implemented yet:** Featherless/AI calls, Generator/Critic orchestration, the revision engine, evaluation execution, ZK proofs, IPFS, blockchain, the Streamlit dashboard, cross-agent memory retrieval. Creating an execution records a `queued` row and nothing runs it.

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
| `FEATHERLESS_API_KEY` | unset | Optional in this milestone; no AI request is made. Never logged or returned by the API |
| `FEATHERLESS_BASE_URL` | `https://api.featherless.ai/v1` | |
| `FEATHERLESS_GENERATOR_MODEL` | `Qwen/Qwen2.5-7B-Instruct` | Provisional choice, configurable |
| `FEATHERLESS_CRITIC_MODEL` | unset | No Critic model is approved, so there is no default |
| `API_TIMEOUT_SECONDS` | `60` | |

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
  errors.py        domain errors mapped to HTTP statuses
  models/          SQLAlchemy tables
  schemas/         Pydantic request/response and internal input models
  services/        business logic (task, execution, version/evaluation/feedback)
  api/             routes, dependencies, error handlers
tests/             pytest suite
```

## Design notes

- **Clients cannot write results.** There are no endpoints to create versions, evaluations or Critic feedback. Backend components use `services/version_service.py`, which derives the overall score from the components.
- **Lifecycle:** `services/execution_service.py::transition_execution` is the only way a status changes. It rejects illegal transitions and uses a compare-and-swap `UPDATE` so concurrent transitions cannot both succeed.
- **Terminal states:** `completed`, `completed_no_improvement`, `failed`, `cancelled`. `completed_no_improvement` means every permitted revision (`executions.max_revisions`, 1 or 2) was evaluated and rejected; the service refuses to enter it while another revision is permitted, or if any revision was accepted, undecided or unevaluated. It is not a failure and carries no error information.
- **Evaluator-led revisions:** the acceptance rule is not implemented. The data model (`acceptance_status`, `rejection_reason`, `best_version_id`) is ready for it, and `decide_version` only records a decision made elsewhere.
- **Score integrity:** the database rejects an evaluation whose stored pass rate or overall score does not match the approved formula (`app/scoring.py`) to within 1e-9, even for a raw SQL write.
- **Operational data** (time, tokens, cost) is stored in its own table and never feeds the deterministic score.
