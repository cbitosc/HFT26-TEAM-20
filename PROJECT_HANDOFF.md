# AutoEvolve Protocol: Complete Project Handoff

**Written:** October 30, 2026
**Purpose:** give a new assistant (or teammate) everything needed to continue development without re-reading the whole history. Every statement below was checked against the repository when this file was written. Where something is a plan rather than code, it says so.

---

## 0. Read this first

- **Workspace:** `C:\Users\ASUS\Desktop\CBIT` (Windows, PowerShell). It is a git repository.
- **Git:** branch `test`, tracking `origin/test` at `https://github.com/cyberloard27/HFT26-TEAM-20` (branch `test`).
  - Commits: `0a451a3` initial commit, then `e4269d9` (a teammate's starter template and README), then `0f172a6` (ours: backend through Milestone 05.1, ZK prototype, research harnesses, docs). That push was made with `git -c user.name=cyberloard27 -c user.email=pj620144@gmail.com`. Git config was not changed and there was no force push.
  - **Everything from Milestone 06 and the PRD alignment is uncommitted** (Section 11 lists the files). The user decides when to commit.
- **Current reference document:** the user's PDF, "AutoEvolve Protocol: Final PRD, Architecture and UI Workflow". Where it conflicts with `SPEC.md`, the PRD wins. `docs/PRD_ALIGNMENT.md` records the decisions on its open questions and audits each PRD requirement against the code.
- **Status in one line:** the backend has a real deterministic evaluator (public and hidden tests), the PRD acceptance policy with typed evidence, and lifecycle guards, with **439 passing tests**. There is no Generator/Critic orchestration, no dashboard, no IPFS/Sepolia, and the ZK circuit is a standalone prototype.

---

## 1. Working rules the user expects

These come from `AGENTS.md` and from how the user has run every milestone.

1. **One prompt = one milestone.** Do the work, run the real tests, write a report, then **stop and wait for the user's approval** before starting the next milestone.
2. **Truthful reporting.** Never claim a test passed unless it was run. Report real numbers. Label anything that is a plan as a plan. Label sample data as `SAMPLE DATA`.
3. **No secrets anywhere.** `FEATHERLESS_API_KEY` exists in the user's shell environment. Never print it, log it, or write it to a file. When scanning for it, print counts only. `.env` is git-ignored, and `backend/.env.example` holds placeholders only.
4. **Do not commit or push unless asked.** If asked, never force-push, and never change git config (use `git -c ...`).
5. **Do not modify ZK files** (`zk/` sources, keys, artifacts) or `docs/ZK_TRUST_MODEL.md` unless a milestone explicitly asks for it.
6. **ZK claims must be narrow.** The proof shows only `score_v2 >= score_v1 + delta` over the integers given. It does not show AI improvement, correctness, or that the scores came from real runs.
7. **Architecture boundaries:** the dashboard talks to FastAPI over HTTP only. The backend owns SQLite, the AI API, IPFS and blockchain. No component bypasses this.
8. **No LLM in scoring or acceptance.** The Critic is advisory. The evaluator measures and the gate decides.
9. **Hidden tests are never revealed** to the Generator, the Critic or API clients. Only aggregate counts may leave the evaluator.
10. **Style of reports:** plain, direct and short, with real numbers, file paths, what was not done, and the risks.

---

## 2. Environment and tools (verified)

| Item | Value |
|---|---|
| OS / shell | Windows, PowerShell |
| Python | 3.12.10; backend venv `backend\.venv` |
| Backend pins (`backend/requirements.txt`) | fastapi 0.162.0, uvicorn 0.54.0, SQLAlchemy 2.1.6, pydantic-settings 2.16.2, pytest 9.2.0, httpx2 2.16.0 |
| SQLite | 3.49.1 (JSON1 available; named CHECK failures report the constraint name) |
| Node | 24.13 |
| ZK | circom 2.2.3 (native Windows binary at `zk/bin/circom.exe`, git-ignored), snarkjs 0.7.6, circomlib 2.0.5 (`zk/package.json`) |
| Not installed | Foundry/solc, Streamlit, any React toolchain, Docker |

**Commands** (run from `C:\Users\ASUS\Desktop\CBIT\backend`):

```powershell
.\.venv\Scripts\python.exe -m pytest                       # full suite (~2 minutes, 439 tests)
.\.venv\Scripts\python.exe -m app.init_db                  # create tables explicitly
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000   # dev server (run manually)
```

ZK (from `zk/`): `node scripts/build.js` (compile and run the development setup), then `node tests/run_tests.js`.

**Tool habits that avoid problems on this machine:**

- Inline Python inside PowerShell breaks easily on quoting. Write a script file to `%TEMP%` and run it.
- Do not create a script and run it in the same parallel batch. The run sometimes starts before the file exists ("file not found").
- `Set-Content -Encoding UTF8` writes a BOM. Use `[IO.File]::WriteAllText(path, text, (New-Object Text.UTF8Encoding $false))`.
- A venv's `python.exe` on Windows is a launcher that starts a child process. Use `sys._base_executable` when you need to kill a child reliably (the evaluator already does this).

---

## 3. Repository layout

```
CBIT/
├── README.md                 teammate template (top) + AutoEvolve README (from "# AutoEvolve Protocol"); status table
├── SPEC.md                   original technical spec; banner says the PRD supersedes it in part
├── AGENTS.md                 workspace rules (truthfulness, secrets, ZK claim limits); dashboard = React
├── PROJECT_HANDOFF.md        this file
├── FEATHERLESS_CRITIC_VALIDATION_REPORT.md   research report (Prompt 03.3)
├── .gitignore                .env, node_modules, zk/bin, zk/build, .venv, __pycache__, backend/data, *.db
├── docs/
│   ├── API_CONTRACT.md       real API contract (every route, field, error code)
│   ├── ARCHITECTURE.md       design; section 10 describes what is actually implemented
│   ├── EVALUATION_ENGINE.md  evaluator, scoring, acceptance policy, delta derivation, limits
│   ├── PRD_ALIGNMENT.md      PRD decisions + requirement-by-requirement repository audit
│   ├── ZK_TRUST_MODEL.md     circuit, constraints, setup, executed test results (do not edit)
│   ├── IMPLEMENTATION_PLAN.md, DASHBOARD_SPEC.md (marked superseded: React per the PRD)
│   ├── AUDIT_REPORT.md, CROSS_AGENT_EXPERIMENT.md   historical records
├── backend/                  FastAPI + SQLite application (Section 5)
├── zk/                       Circom circuit prototype (Section 7)
└── eval/                     Featherless research harnesses and results (Section 8)
```

---

## 4. History: what each milestone did

| Prompt | What was done |
|---|---|
| 01 | Inspected the (empty) workspace and toolchain. No code |
| 02 | Wrote `SPEC.md`, `AGENTS.md`, `README.md`, and docs: `ARCHITECTURE`, `IMPLEMENTATION_PLAN`, `ZK_TRUST_MODEL`, `API_CONTRACT`, `DASHBOARD_SPEC` |
| 02.1 | Audit: removed unconstrained hash inputs from the circuit design, fixed contract issues, added `CROSS_AGENT_EXPERIMENT.md` and `AUDIT_REPORT.md` |
| 02.2–02.4 | Corrected the circuit spec to `score_v2 >= score_v1 + delta` with range checks (`Num2Bits`, `LessEqThan(8)`). Docs only |
| 03 / 03.1 | Featherless feasibility: listed the available models and ran basic calls (those first measurements were later found to be flawed/estimated) |
| 04 | Implemented the ZK circuit in `zk/`: 82 constraints, development-only Groth16 setup, 10 test cases plus a tampering test, all behaving as expected |
| 03.2 | `eval/featherless_compare.py`: Qwen2.5-7B-Instruct vs Qwen2.5-Coder-7B. Without evaluator evidence, the Critics missed the real defect in 0 of 8 reviews. Chose 7B as the provisional Generator |
| 03.3 | `eval/critic_validation.py` + `FEATHERLESS_CRITIC_VALIDATION_REPORT.md`: evidence helps the Critic; 32B is better but not reliable; recommended an evaluator-led loop |
| 05 | Backend foundation: FastAPI + SQLite, validated lifecycle, response envelope, 186 tests, mutation check, docs |
| 05.1 | Hardening: `completed_no_improvement` state, `max_revisions`, database CHECK constraints for score consistency (tolerance 1e-9), docs reconciled. 313 tests |
| push | Pushed to GitHub branch `test` (commit `0f172a6`) |
| 06 | Deterministic evaluation engine + strict revision acceptance gate + lifecycle guards + 2 API triggers. Uncommitted |
| PRD | Aligned with the new PRD: public/hidden suites, commitment at run start, full provenance, delta = 1.0, four evidence statuses, invalid comparisons stored, evidence endpoint, hidden-test confidentiality, docs. 439 tests. Uncommitted |

---

## 5. Backend: how it works

### 5.1 Layout (`backend/app/`)

```
main.py            app factory + lifespan (creates tables with create_all)
config.py          Settings (env vars / backend/.env); the only place model IDs live
database.py        engine (foreign keys ON), session factory, UTC datetime type, new_id(), utcnow()
init_db.py         python -m app.init_db
lifecycle.py       ExecutionStatus, allowed transitions, TERMINAL_STATUSES, MIN/MAX/DEFAULT_REVISIONS (1/2/2)
scoring.py         weights 0.5/0.3/0.2, SCORE_TOLERANCE = 1e-9, SQL versions of the formulas
errors.py          domain errors -> HTTP status + stable error code
evaluation/
  suite.py         EvaluationSuite, TestCase (visibility public|hidden), Check kinds, hashes, EVALUATOR_VERSION="1"
  suites/          registry (SUITES, register, get_suite); merge_intervals.py (5 public + 10 hidden)
  _runner.py       child-process script that executes candidate code (stdlib only)
  execution.py     run_candidate(): subprocess management, timeouts, cleanup, RunLimits
  engine.py        evaluate_source() -> EvaluationOutcome (P hidden, public counts, C, Q, breakdown)
  static_quality.py  AST quality checks, cyclomatic complexity
  provenance.py    evaluator_config(), evaluator_config_hash(), environment()
  policy.py        SCORING_RULE_VERSION="2", DELTA=1.0, term ids, suite registration check, zk_integer_score()
  gate.py          pure functions: snapshot(), preconditions(), compare(), FailedTerm, Commitment
  completeness.py  is_complete(evaluation)
models/            task, execution (+commitment), execution_transition, version, evaluation (+provenance),
                   evaluation_operational_metrics, evidence (EvidenceRecord, InvalidComparison),
                   critic_feedback, agent_memory
schemas/           Pydantic request/response models (acceptance.py, evaluation.py, execution.py, task.py, ...)
services/          task_service, execution_service, version_service, evaluation_service, acceptance_service
api/routes/        health, tasks, executions, versions
```

### 5.2 Data model (SQLite, created with `create_all`; no migrations)

| Table | Key facts |
|---|---|
| `tasks` | title, description, requirements (JSON), language, category, `evaluation_suite_id` (must be a registered suite), status |
| `executions` | status (lifecycle), `max_revisions` (1–2, default 2), timestamps, error fields (only when `failed`), `best_version_id`, and the **commitment**: `suite_id`, `suite_hash`, `public_suite_hash`, `hidden_suite_hash`, `evaluator_config_hash`, `scoring_rule_version`, `delta`, `committed_at` (all-or-nothing CHECK; delta > 0) |
| `execution_transitions` | append-only history (`from_status` is NULL for the first row) |
| `versions` | sequence/label (V1, V2, ...), code, parent, `acceptance_status` (`pending`/`accepted`/`rejected`, final), `rejection_reason` (exactly when rejected), `decided_at`, `decision_details` (JSON) |
| `evaluations` | `tests_passed`/`tests_total` = **hidden** counts; `public_tests_passed`/`public_tests_total`; `test_pass_rate`, `correctness_score`, `code_quality_score`, `overall_score`; `failure_details`; `suite_id`, `suite_hash`, `evaluator_version`, `evaluator_config_hash`, `scoring_rule_version`, `provenance` (JSON), `test_results` (JSON, internal, includes hidden ids), `score_breakdown` |
| `evaluation_operational_metrics` | time, tokens, cost (+ `api_cost_source`); never part of the score |
| `evidence_records` | `validated_improvement` or `rejected_attempt`; failed terms; both versions' scores; provenance; one per candidate version |
| `invalid_comparisons` | failed preconditions; stored separately; not evidence |
| `critic_feedback` | advisory; shown in the API as `evidence_status: "unvalidated_proposal"` |
| `agent_memories` | minimal storage table only (no retrieval logic) |

**Database-enforced integrity (CHECK constraints):** pass rate = passed / total * 100 and overall = 0.5P + 0.3C + 0.2Q, each within 1e-9 (wrapped in COALESCE so a NULL result fails). Also enforced: score ranges, `tests_total >= 1`, provenance all-or-nothing, `test_results` length = hidden + public counts, and the commitment being all-or-nothing. A raw SQL write cannot store an inconsistent score.

### 5.3 Lifecycle

```
queued -> generating_v1 -> evaluating_v1 -> critiquing -> generating_v2 -> evaluating_v2
       -> [generating_v3 -> evaluating_v3] -> zk_proof -> ipfs_publish -> blockchain_register -> completed
```

- `failed` and `cancelled` are reachable from every non-terminal state. Terminal states: `completed`, `completed_no_improvement`, `failed`, `cancelled`.
- `completed_no_improvement` is reachable from `evaluating_v2` (only when `max_revisions = 1`) and from `evaluating_v3`. It requires every permitted revision to be recorded, evaluated and **rejected**. Any accepted, undecided or only-invalidly-compared revision blocks it.
- **`zk_proof` guard:** the best version must be an accepted revision (not V1) with a `validated_improvement` evidence record, and the policy, re-applied to the persisted evaluations of V1 and the best version against the commitment, must still hold.
- Every transition is a compare-and-swap UPDATE plus a history row. A racing transition gets 409.
- **No component drives transitions yet**. Only tests and services call `transition_execution`.

### 5.4 Settings (`app/config.py`, env vars or `backend/.env`)

| Variable | Default |
|---|---|
| `APP_ENV` | `development` (`development`/`test`/`production`) |
| `DATABASE_URL` | `sqlite:///<backend>/data/autoevolve.db` (SQLite only) |
| `FEATHERLESS_API_KEY` | unset (SecretStr; never logged) |
| `FEATHERLESS_BASE_URL` | `https://api.featherless.ai/v1` |
| `FEATHERLESS_GENERATOR_MODEL` | `Qwen/Qwen2.5-7B-Instruct` (provisional) |
| `FEATHERLESS_CRITIC_MODEL` | unset (no Critic approved; `Qwen/Qwen2.5-32B-Instruct` is an experimental candidate) |
| `API_TIMEOUT_SECONDS` | 60 |
| `EVALUATION_TIMEOUT_SECONDS` | 10 (per interpreter run; part of the config hash) |
| `EVALUATION_TOTAL_TIMEOUT_SECONDS` | 60 (whole evaluation; part of the config hash) |
| `ALLOW_UNSANDBOXED_EVALUATION` | unset: allowed in dev/test, refused in production |

---

## 6. Evaluation engine and acceptance policy (the core)

Full detail is in `docs/EVALUATION_ENGINE.md`.

### 6.1 Suites

- Suites are backend-defined data. Literals are rebuilt in the child with `ast.literal_eval`, so suite data is never executed as code. Check kinds: `returns` (type-strict equality), `raises`, `unchanged_input`, `all_items_of_type`.
- `python-merge-intervals-v1`:
  - **public (5):** `overlap`, `touching`, `unsorted_input`, `empty`, `typeerror_not_list`
  - **hidden (10):** `contained`, `chain`, `single_point`, `duplicates`, `input_not_mutated`, `returns_tuples`, `typeerror_bad_element`, `valueerror_start_gt_end`, `validation_applies_to_all`, `typeerror_non_int_values`
- Registration requires at least one public test, at least one hidden test, and one hidden test being worth more than delta (so at most 49 hidden tests).
- **Limitation:** the hidden tests are in the repository. They are hidden from agents and the API, but not secret. User-uploaded suites are not built.

### 6.2 Scoring (rule version 2)

`S = 0.5*P + 0.3*C + 0.2*Q`, full double precision, no rounding.

- **P** = hidden-suite pass rate. Public tests never enter S.
- **C** (correctness) = 100 × the share of 5 interface checks that hold: compiles, imports cleanly, entry point defined, accepts the expected argument count, smoke call returns the exact expected type. C is independent of P but weak: almost always 100 for working code.
- **Q** (quality) = mean of 5 AST checks × 100: syntax valid, complexity within limit (graded `max(0, 1-(worst-limit)/limit)`, limit 10), entry point documented, entry point type-annotated, no hazardous constructs (bare except, eval/exec/`__import__`, `import *`, mutable defaults). Q is 0 if the code doesn't parse or has no entry point.
- **Unsupported (documented):** style/formatting/readability, lint score, time/space complexity, coverage.

### 6.3 Commitment and provenance

- Creating an execution records the commitment (suite hashes, evaluator config hash, rule version, delta). If the task has no suite, the execution is refused with 409 `EVALUATION_SUITE_UNAVAILABLE`.
- The evaluator config covers the evaluator version, both timeouts, the interpreter version, flags `-s -B`, `PYTHONHASHSEED=0`, and the SHA-256 of `_runner.py`, `execution.py`, `engine.py`, `static_quality.py` and `suite.py`. Editing any of those files changes the hash.
- Each evaluation stores the full provenance plus `matches_commitment` flags. The environment entry says "subprocess; NOT a security sandbox", and `runner_image_digest` is null.
- Evaluating is refused (409) if the registered suite no longer matches the committed hash.

### 6.4 Acceptance policy (`acceptance_service.decide_acceptance`)

| Step | Rule | On failure |
|---|---|---|
| Structural | version pending, execution not terminal, V1 not decided twice, baseline exists before revisions, best pointer consistent | 409, nothing stored |
| Baseline (V1, no best yet) | complete evaluation matching the commitment | 409 `EVALUATION_REQUIRED` / `EVALUATION_NOT_COMPARABLE` |
| Preconditions | `same_execution`, `candidate_evaluation_complete`, `previous_best_evaluation_complete`, `same_suite`, `same_evaluator_configuration`, `same_scoring_rule` (all against the commitment) | `invalid_comparison` row; version stays **pending** |
| Predicate | `no_test_regression` (public and hidden), `no_dimension_regression:hidden_pass_rate` / `:correctness` / `:code_quality`, `aggregate_delta` (S_new >= S_old + 1.0, tolerance 1e-9) | `rejected_attempt`: version rejected (final), **all** failed terms recorded, best unchanged |
| All pass | | `validated_improvement`: version accepted, evidence record written, `best_version_id` moves, in **one transaction** with compare-and-swap guards |

- Messages name public tests and only **count** hidden ones ("1 hidden test(s) passed in V1 but fail in V2").
- Concurrency: the loser of a race gets 409 and its candidate stays pending. This is tested with interleaving and with 6 threads.
- **Delta = 1.0, and why:** one hidden test = 5.0 points, one quality check = 4.0, one contract check = 6.0, one complexity step = 0.4 (deliberately not enough), float noise ≤ 1e-9. Delta is an integer because the circuit needs one. `policy.zk_integer_score(s) = floor(s + 1e-9)`, and since S_new ≥ S_old + 1 implies floor(S_new) ≥ floor(S_old) + 1, an accepted gain is always provable under that encoding (tested with random values). No stage uses this encoding yet.

### 6.5 Subprocess execution (NOT a sandbox)

- The real interpreter (`sys._base_executable`) is used, with per-run and total timeouts and a restart after a hang.
- stdin is closed and the candidate's stdout/stderr are discarded. Results come back through a JSONL file, so printed text can't forge them.
- The code runs in a temporary working directory (removed in `finally`, with retries on Windows) with a minimal environment.
- Each test gets a fresh module execution. Equality is type-strict, so a custom `__eq__` can't fake a pass. Sources over 200 KB are not run.
- Hostile code can still read files, use the network or harm the machine. In production, execution is refused unless `ALLOW_UNSANDBOXED_EVALUATION=true`. A container sandbox is planned, not built.

### 6.6 Results on the research candidates (`backend/tests/fixtures/`)

| Fixture | Hidden | Public | C | Q | S |
|---|---|---|---|---|---|
| `flawed` | 2/10 | 2/5 | 100 | 60 | 52.0 |
| `gen_coder_no_value_check` | 6/10 | 4/5 | 100 | 100 | 80.0 |
| `gen_7b` | 9/10 | 5/5 | 100 | 98 | 94.6 |
| `gen_coder` | 9/10 | 4/5 | 100 | 100 | 95.0 |
| `gen_coder_sorts_in_place` | 9/10 | 5/5 | 100 | 100 | 95.0 |
| `reference_good` | 10/10 | 5/5 | 100 | 98 | 99.6 |

- `flawed` → `gen_7b` → `reference_good` is accepted at each step.
- `gen_coder` → `gen_coder_sorts_in_place` is rejected with `no_test_regression` + `aggregate_delta`: it fixes a public test but breaks hidden `input_not_mutated`.
- `gen_coder` → identical code is rejected with `aggregate_delta` only.
- `flawed.py`, `gen_7b.py` and `gen_coder.py` are copies of `eval/candidates/{A_flawed,B_gen_7b,C_gen_coder}.py`. The other three are derived variants.

---

## 7. API (all under `/api`; envelope `{success, data, error}`; details in `docs/API_CONTRACT.md`)

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | 503 if the DB is unreachable; no secrets |
| POST | `/tasks` (201) | unknown fields → 422; `evaluation_suite_id` must be registered |
| GET | `/tasks`, `/tasks/{id}` | paginated list (`limit` ≤ 200, `offset`) |
| POST | `/tasks/{id}/executions` (201) | queued execution + commitment; 409 without a suite; body ignored |
| GET | `/executions` | filters `status`, `task_id` |
| GET | `/executions/{id}` | includes transitions and commitment |
| POST | `/executions/{id}/cancel` | 409 if terminal |
| GET | `/executions/{id}/versions` | |
| GET | `/executions/{id}/evidence` | commitment, scoring rule, evidence records, invalid comparisons, count of unvalidated proposals |
| GET | `/versions/{id}` | includes `decided_at`, `decision_details` |
| GET | `/versions/{id}/evaluations` | hidden tests as counts only; public per-test results and failures; provenance; `complete` |
| POST | `/versions/{id}/evaluate` (201) | runs the evaluator; **body must be empty** (any field → 422) |
| POST | `/versions/{id}/acceptance-decision` | outcome `baseline` / `validated_improvement` / `rejected_attempt` / `invalid_comparison`; **body must be empty** |
| GET | `/versions/{id}/critic-feedback` | each item has `evidence_status: "unvalidated_proposal"` |

- **Error codes:** 404 `TASK_NOT_FOUND` / `EXECUTION_NOT_FOUND` / `VERSION_NOT_FOUND` / `NOT_FOUND`; 405 `METHOD_NOT_ALLOWED`; 403 `EVALUATION_EXECUTION_DISABLED`; 409 `INVALID_TRANSITION`, `CONFLICT`, `EVALUATION_SUITE_UNAVAILABLE`, `EVALUATION_REQUIRED`, `EVALUATION_NOT_COMPARABLE`, `BASELINE_REQUIRED`; 422 `VALIDATION_ERROR`; 500 `INTERNAL_ERROR`; 503 `DATABASE_UNAVAILABLE`.
- **There is no endpoint that accepts scores, verdicts, an improvement claim or a ZK status.** The internal primitives `version_service.record_evaluation` and `decide_version` have no route.

---

## 8. Tests (`backend/tests/`, 439 passing at handoff)

| File | Count | Covers |
|---|---|---|
| `test_acceptance.py` | 75 | pure gate, delta boundary, every failed term, hidden-safe messages, ZK encoding property, validated/rejected/invalid outcomes, structural refusals, real-candidate end-to-end, concurrency (interleave + threads), API (evaluate/decide/evidence, forged bodies → 422, no hidden-name leaks), lifecycle guards |
| `test_evaluation_engine.py` | 46 | pass/partial/fail, syntax error, import error, runtime exception, hangs and timeouts, `os._exit`/`sys.exit`, fake `__eq__`, stdout forgery, oversize source, determinism, public/hidden split, quality checks, complexity, suite hashing and registration rules, provenance, temp-directory cleanup, missing/changed/zero-test suites, production refusal |
| `test_no_improvement.py` | 61 | `completed_no_improvement` rules |
| `test_lifecycle.py` | 53 | transition table and persisted transitions |
| `test_database.py` | 42 | constraints and relationships |
| `test_score_integrity.py` | 39 | raw-SQL score CHECK constraints |
| `test_versions_evaluations.py` | 37 | read endpoints, deterministic/operational separation |
| `test_docs.py` | 30 | docs match the code (routes documented, delta/terms documented, no claims about nonexistent files, etc.) |
| `test_tasks.py` 24, `test_executions.py` 13, `test_startup_health.py` 12, `test_errors.py` 7 | | |

- Each test gets its own app and temporary SQLite file. `backend/.env` and the related env vars are ignored, and no network calls are made.
- Helpers in `tests/helpers.py`:
  - `complete_input(...)` builds a stored evaluation with the real commitment provenance.
  - `grant_improvement(db, eid)` creates V1 + V2 and accepts both through the real service.
  - `advance(db, eid, status)` creates a real improvement before entering `zk_proof`.
  - `consistent_evaluation(...)` builds an ORM row that satisfies the constraints.
- **Mutation check (Milestone 06/PRD):** 13 deliberate rule-breaking edits (delta ignored, test regressions ignored, quality regression ignored, hidden ids named, config hash unchecked, invalid comparison treated as rejection, no evidence record, ZK guard without evidence, hidden results or failures exposed by the API, score using all tests, no commitment, delta registration check removed). All 13 made tests fail. The script is `%TEMP%\mutate06.py`, outside the repo.

---

## 9. ZK prototype (`zk/`, standalone, not called by the backend)

- **Circuit:** `zk/circuits/improvement_proof.circom`, public inputs `score_v1`, `score_v2`, `delta`.
  - Constraints: `0 ≤ score_v1, score_v2 ≤ 100` (`Num2Bits(7)` + `LessEqThan(7)`), `1 ≤ delta ≤ 50` (`Num2Bits(6)`, `LessEqThan(6)`, `GreaterThan(6)`), `target = score_v1 + delta`, `LessEqThan(8)(target, score_v2)`. Equality passes.
  - 82 constraints (59 non-linear, 23 linear).
- **Setup:** Groth16, **development-only single-party** trusted setup (`powersoftau` bn128 2^8). Not production.
- **Executed results:** 10/10 witness cases behaved as expected. Cases 1, 2 and 5 produced proofs that verified `OK!`. Two tampered public-input files were rejected. Failing cases: v2 < v1+δ, v2 < v1, equal at 100 with δ=1, v2=150, δ=0, δ=51, v1=−5.
- **Integration gap:** backend scores are floats. The planned encoding is `floor(score + 1e-9)` with delta = 1 (Section 6.4). The proof is not yet bound to evaluation records or code hashes.
- `zk/bin/` and `zk/build/` are git-ignored; regenerate them with `node scripts/build.js`.

---

## 10. Featherless research (`eval/`, research tooling, not application code)

- `eval/featherless_compare.py` (Prompt 03.2) compared Qwen/Qwen2.5-7B-Instruct with Qwen2.5-Coder-7B. Without evaluator evidence, both Critics missed the real defect in all 8 reviews. 7B was chosen as the provisional Generator.
- `eval/critic_validation.py` and `FEATHERLESS_CRITIC_VALIDATION_REPORT.md` (Prompt 03.3):
  - With evaluator evidence, 3 of 4 reviews of generated code found every real defect.
  - The 7B Critic made false or evaluator-contradicting claims in 2 of 3 responses, and its advice made one revision worse (12/14 → 11/14).
  - The 32B Critic made no false claims but missed one defect while reporting confidence 1.0.
  - All confidences were ≥ 0.95, including the wrong ones, so confidence carries no signal.
  - Revision gains: control 25/28 (no gain), with 7B 25/28, with 32B 27/28. This is a weak signal from 2 candidates with 1 sample each.
- **Recommendation adopted:** an evaluator-led loop. The evaluator is the sole judge; the Critic gets the real failure details and its output is "model opinion". Keep the best verified version, and record "no improvement" instead of inventing one.
- Both Critics recommended in-place sorting for candidate C. That would break `input_not_mutated`, and this is now encoded as the `gen_coder_sorts_in_place` fixture, which the gate rejects.
- Results JSON files are in `eval/results/`. They contain model outputs, not secrets.

---

## 11. Uncommitted changes (Milestone 06 + PRD alignment)

**New files:**

- `backend/app/evaluation/` (`__init__.py`, `suite.py`, `suites/__init__.py`, `suites/merge_intervals.py`, `_runner.py`, `execution.py`, `engine.py`, `static_quality.py`, `completeness.py`, `gate.py`, `policy.py`, `provenance.py`)
- `backend/app/models/evidence.py`, `backend/app/schemas/acceptance.py`
- `backend/app/services/evaluation_service.py`, `backend/app/services/acceptance_service.py`
- `backend/tests/fixtures/` (6 candidate sources), `backend/tests/test_acceptance.py`, `backend/tests/test_evaluation_engine.py`
- `docs/EVALUATION_ENGINE.md`, `docs/PRD_ALIGNMENT.md`, `PROJECT_HANDOFF.md`

**Modified files:**

- Backend app: `config.py`, `errors.py`, `models/{__init__,evaluation,execution,task,version}.py`, `schemas/{critic_feedback,evaluation,execution,task,version}.py`, `services/{execution_service,task_service,version_service}.py`, `api/routes/{executions,tasks,versions}.py`
- Backend other: `.env.example`, `README.md`, `tests/{conftest,helpers,test_docs,test_lifecycle,test_no_improvement,test_versions_evaluations}.py`
- Root and docs: `AGENTS.md` (dashboard = React), `README.md` (status table, endpoints), `SPEC.md` (PRD banner, status), `docs/API_CONTRACT.md`, `docs/ARCHITECTURE.md` (section 10), `docs/DASHBOARD_SPEC.md` (superseded banner)

**Unchanged on purpose:** all of `zk/`, `docs/ZK_TRUST_MODEL.md`, `eval/`.

**Schema changed:** delete any existing `backend/data/autoevolve.db` and recreate it. There is no migration tool.

---

## 12. PRD decisions already made (see `docs/PRD_ALIGNMENT.md`)

| Question | Decision |
|---|---|
| Two or three scoring dimensions | Three (P, C, Q), weights unchanged; C is documented as weak |
| Delta | 1.0 aggregate point |
| Pass-rate source | hidden tests only; public tests must not regress |
| Invalid comparisons | stored separately; the version stays pending |
| Dashboard | React web app (replaces Streamlit) |
| Hidden suite for the demo | backend-defined split, 5 public / 10 hidden |
| Default visibility | private (nothing is published yet) |
| Still open | who authors Agent B's suite; who holds hidden tests in production |

---

## 13. Known gaps and risks (be honest about these)

1. **No orchestrator.** Nothing calls Featherless, generates versions, runs the Critic or drives the lifecycle. The evaluator and gate run only when the API triggers or tests call them.
2. The subprocess evaluator is **not a security sandbox**. A container is planned.
3. Hidden tests live in the repository: hidden, but not secret.
4. `decide_version` and `record_evaluation` are internal bypass paths, with no route. The ZK guard doesn't trust their output.
5. A stored score is not bound to the code by a hash. There is no code hash in the provenance yet.
6. The ZK proof is not integrated or bound to evaluation commitments, and its setup is development-only.
7. There is no on-chain commitment; the commitment exists only in SQLite.
8. There is no migration tool; schema changes require recreating the DB.
9. C rarely separates working revisions, and a do-nothing function passes the hidden `input_not_mutated` test (documented).
10. Not built: egress gate, IPFS/Pinata, Sepolia contracts, lesson validator, Agent B transfer, capabilities, dashboard, user-uploaded suites, runner quorum.

---

## 14. Next steps (PRD milestones; each needs the user's go-ahead)

| PRD milestone | State | Suggested next action |
|---|---|---|
| 1 Audit scoring, gate, provenance; set delta | **Done** | |
| 2 Provenance hashes + four evidence statuses | **Done** | |
| 3 Dashboard: New Task, Run, Compare | Not started | React app calling FastAPI only. Run View: execution tree with public X/5, hidden Y/10, outcome. Compare View: hidden-accuracy headline, public for context, gate result with exact failed terms, code diff. Data comes from `/executions/{id}`, `/versions/{id}/evaluations`, `/acceptance-decision`, `/evidence`. Never show hidden test names. A CORS setting will be needed on the backend |
| (prerequisite) Orchestrator | Not started | Featherless Generator (temperature 0, pinned model) → evaluate → Critic (gets **public** failures only) → revise V2/V3 → gate → lifecycle transitions; stop on acceptance or budget; record "no improvement" honestly |
| 4 Egress gate + lesson validator | Not started | secret/PII scan before any upload; causal replay of the diff |
| 5 Pinata, Sepolia registry, narrow proof | Not started | integer encoding `floor(S + 1e-9)`, delta 1; on-chain commitment of hashes |
| 6 Agent B transfer + Memory view | Not started | control vs treatment on Agent B's own suite; attestations |
| 7 Capabilities with audit trail | Not started | |

When continuing, start each milestone with a short ambiguity report if anything is unclear. Implement only that milestone, run the whole suite, report real results with the 12-point style (files, design, definitions, endpoints, security limits, test results, unresolved issues, exclusions), then stop.
