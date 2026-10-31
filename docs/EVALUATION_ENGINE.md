# AutoEvolve Protocol: Evaluation Engine and Acceptance Policy

**Date:** October 30, 2026
**Code:** `backend/app/evaluation/` (engine, suites, policy, gate, provenance), `backend/app/services/evaluation_service.py`, `backend/app/services/acceptance_service.py`
**Status:** implemented and tested in the backend. It is not driven by a pipeline yet: no component generates versions, so evaluations and decisions happen only when the two API triggers (or tests) request them.

This document follows the PRD (Section 5, "Evidence model and acceptance policy") and records the decisions that the PRD left open.

---

## 1. Principle

The agent claims, the evaluator measures, the gate decides. No LLM is involved in any score or decision. A caller can ask the backend to evaluate a version or to apply the policy, but it cannot send a score, a verdict, a delta or a proof status: the request bodies have no fields and anything extra is a 422.

---

## 2. Test suites: public and hidden

A suite is backend-defined data (`app/evaluation/suite.py`), registered in `app/evaluation/suites/`. Test inputs and expected values are plain literals; the child process rebuilds them with `ast.literal_eval`, so suite data is never executed as code.

Each test is `public` or `hidden`.

| | Public | Hidden |
|---|---|---|
| Who may see it | Generator, Critic, API clients | nobody outside the evaluator |
| Enters the score | no | yes: P is the hidden-suite pass rate |
| Must not regress | yes | yes |
| Returned by the API | name, per-test result, failure detail | aggregate count only |

The merge-intervals suite (`python-merge-intervals-v1`) has 5 public and 10 hidden tests. They are the 14 behaviours of the earlier research harness plus one hidden test for duplicate intervals.

A suite can only be registered if it has at least one public and one hidden test, and if one hidden test is worth more than delta (Section 5).

**Limitation.** The suite file is in the repository, so anyone who can read the repository can read the hidden tests. "Hidden" here means hidden from the agents and from API clients, not secret. Who holds hidden suites in production is an open PRD decision. User-uploaded suites (the PRD's New Task form) are not implemented.

---

## 3. Commitment and provenance

**Commitment.** When an execution is created, before any version exists, the backend records the suite id, `suite_hash` (whole suite), `public_suite_hash`, `hidden_suite_hash`, `evaluator_config_hash`, `scoring_rule_version` and `delta`. If the task has no suite, the execution is not created (409 `EVALUATION_SUITE_UNAVAILABLE`). The commitment lives in SQLite. An on-chain commitment on Sepolia is planned, not built.

**Provenance (PRD FR-3).** Every evaluation stores:

- suite id and the three suite hashes
- evaluator version and evaluator configuration with its hash. The configuration covers both time limits (a timeout is a failure, so limits change outcomes), the interpreter version, the interpreter flags, `PYTHONHASHSEED`, and the SHA-256 of each evaluator source file (`_runner.py`, `execution.py`, `engine.py`, `static_quality.py`, `suite.py`)
- scoring-rule version and its hash, and delta
- an environment description: OS, platform, Python version, isolation `subprocess with time limits; NOT a security sandbox`, and `runner_image_digest: null`, because no container exists and none is invented
- execution id, version id, timestamp
- `code_sha256`: the SHA-256 of the UTF-8 bytes of the exact code that ran
- whether the suite, configuration and rule match the execution's commitment

**Code-hash binding.**

- Each version stores `code_sha256`, computed by the backend at creation.
- Before running, the evaluator re-hashes the stored code. If the hash differs from the recorded one, the code was changed after creation and evaluation is refused (409 `CODE_HASH_MISMATCH`).
- The evaluation stores the hash of the code it ran (NOT NULL, 64 lowercase hex characters, enforced by CHECK constraints on both tables).
- The gate refuses to compare an evaluation that does not belong to the code currently stored (precondition `same_code_hash_as_evaluated`). The proof-stage guard re-checks it too.
- Each check reads the code from the database, never from a cached copy.

An evaluation is **complete** when all provenance fields are present and there is exactly one well-formed outcome per configured test, with counts that agree. Timeouts and crashes count as outcomes (they are failures). The gate only compares complete evaluations.

---

## 4. Scoring (rule version 2)

```
S = 0.5 * P + 0.3 * C + 0.2 * Q        (backend/app/scoring.py; unchanged weights, no rounding)
```

| Component | Definition |
|---|---|
| **P**, hidden-suite pass rate | hidden tests passed / hidden tests * 100, measured by running the code |
| **C**, correctness | 100 * (passed of 5 interface-contract checks) / 5: `compiles`, `imports_cleanly`, `entrypoint_defined`, `entrypoint_accepts_expected_arguments`, `smoke_call_returns_expected_type` |
| **Q**, code quality | mean of 5 structural AST checks * 100: `syntax_valid`, `complexity_within_limit` (graded: `max(0, 1 - (worst - limit) / limit)` above the limit of 10), `entrypoint_documented`, `entrypoint_type_annotated`, `no_hazardous_constructs` (bare `except`, `eval`/`exec`/`__import__`, `import *`, mutable defaults). Q is 0 if the source does not parse or has no entry point |

Operational data (wall time, tokens, cost) is stored in a separate table and never enters S.

**Audit of C (PRD open decision 1).** C does not reuse pass/fail results. It is computed from interface checks, so P and C are not double-counted. The three-dimension formula is therefore kept. C is a weak dimension, though: almost any code that defines the entry point scores 100, so C separates "broken module" from "loads" and rarely separates two working revisions. All five research candidates score C = 100.

**Not measured (unsupported, deliberately):** formatting, naming, readability, design, comments, duplication, test coverage, time and space complexity, and any lint score (no linter is installed). A docstring's presence says nothing about its content.

---

## 5. Acceptance policy

**Preconditions.** If any precondition fails, the result is `invalid_comparison`: it is stored in a separate table, nothing is decided, and the version stays `pending`.

| Term | Holds when |
|---|---|
| `same_execution` | the candidate and the current best belong to the same execution |
| `candidate_evaluation_complete` | the candidate's latest evaluation exists and is complete |
| `previous_best_evaluation_complete` | the same, for the current best |
| `same_suite` | both evaluations used the committed suite hash |
| `same_evaluator_configuration` | both used the committed evaluator configuration hash |
| `same_scoring_rule` | both were scored under the committed rule version |
| `same_code_hash_as_evaluated` | for both versions, the evaluation's `code_sha256`, the version's recorded `code_sha256` and the hash of the code stored now are identical |

**Predicate.** If any term fails, the result is `rejected_attempt`. The version is rejected (decisions are final) and **every** failed term is recorded.

| Term | Holds when |
|---|---|
| `no_test_regression` | every test, public or hidden, that passes in the best version still passes |
| `no_dimension_regression:hidden_pass_rate` | P does not drop |
| `no_dimension_regression:correctness` | C does not drop |
| `no_dimension_regression:code_quality` | Q does not drop |
| `aggregate_delta` | S_new >= S_old + delta |

Ties in a dimension are allowed, and any drop rejects even if S rises. Comparisons use the 1e-9 tolerance of the database score constraints.

If every term holds, the result is `validated_improvement`. The version is accepted, an evidence record is written and `best_version_id` moves. These three writes happen in one transaction, each guarded by a compare-and-swap. A concurrent decision on the same execution makes the later one fail with 409 and leaves the candidate `pending`.

**Baseline.** V1 becomes the first best version when it has a complete evaluation that matches the commitment. Nothing is compared, so no evidence record is written.

**Why invalid comparisons decide nothing.** Decisions are final. Recording a rejection because a version was not evaluated yet, or was evaluated under a different configuration, would permanently block a revision that might be good. The PRD's UI rule says the same: a configuration mismatch "is not a bad revision".

### Delta = 1.0 aggregate point (PRD open decision 2)

| Increment | Aggregate points |
|---|---|
| floating-point noise | <= 1e-9 (the tolerance) |
| one complexity step (limit 10) | 0.2 * 20 / 10 = **0.4** |
| one quality check | 0.2 * 20 = 4.0 |
| one hidden test (10 hidden tests) | 0.5 * 100 / 10 = **5.0** |
| one contract check | 0.3 * 20 = 6.0 |

- Delta is far above float noise and below every meaningful increment: one more passing hidden test, quality check or contract check always clears it. Registration enforces the test part: a suite whose single-hidden-test increment is not above delta (50 or more hidden tests) is refused.
- A revision whose only gain is one complexity step (0.4 points) is rejected as "delta not met". This is a deliberate choice.
- Delta is an integer because the existing Circom circuit takes integer scores (0 to 100) and an integer delta (1 to 50). The aggregate is a float, so the proof stage will need an integer encoding. `policy.zk_integer_score(s) = floor(s + 1e-9)` is defined for that purpose. Because S_new >= S_old + 1, floor(S_new) >= floor(S_old) + 1 always holds, so an accepted improvement can never become unprovable under this encoding. A randomized test checks this. No stage uses the encoding yet, and the ZK files are unchanged.

---

## 6. Lifecycle guards

- **`completed` straight from `evaluating_v2` or `evaluating_v3`** (Milestone 07B: completion no longer goes through publishing) requires exactly the same verified improvement as `zk_proof`, below.
- **`critiquing_v2`** (the second critique, before V3) requires `max_revisions = 2` and that no revision was accepted.
- **`zk_proof`** requires all of these: the best version is an accepted revision (not V1); it has a `validated_improvement` evidence record; the policy, re-applied from the persisted evaluations of V1 and the best version against the commitment, still holds. Forged flags (a version marked accepted through internal primitives) and later tampering (a newer, worse evaluation) are both refused.
- **`completed_no_improvement`** requires every permitted revision to be recorded, evaluated and **rejected**. A revision that only produced an `invalid_comparison` is still undecided, so it blocks this state.

---

## 7. Execution of candidate code: limits

**The evaluator runs candidate code in a subprocess. This is NOT a security sandbox.** It provides:

- a fresh interpreter (the real one, not the venv launcher, so a kill really stops it)
- a per-run time limit and a total limit; after a hang, the remaining tests continue in a new process
- closed stdin, with the candidate's stdout and stderr discarded
- results passed through a file, not stdout, so printed text cannot forge a result
- a throwaway working directory with TEMP/TMP pointed into it, removed afterwards
- a minimal environment with `PYTHONHASHSEED=0`
- a freshly executed module for every test
- type-strict comparison, so a custom `__eq__` cannot fake a pass
- sources over 200 KB are not executed

Hostile code can still read files, use the network, spawn processes or damage the machine. Never evaluate untrusted code on a machine that matters. In `production`, code execution is refused unless `ALLOW_UNSANDBOXED_EVALUATION=true` (403 `EVALUATION_EXECUTION_DISABLED`). A container sandbox (pinned image, no network, read-only repository) is planned.

---

## 8. What the scores and decisions do and do not show

- A score shows only what the configured tests and checks measure. A weak suite can approve buggy code. Example: a function that returns `None` passes the hidden `input_not_mutated` test.
- The evaluator is trusted. It is made checkable by provenance hashes and reproducibility. Independent runners (quorum) and a challenge window are planned.
- Critic feedback is advisory (`unvalidated_proposal`). It never enters a score or a decision.
- Every stored score is bound to the SHA-256 of the exact code it measured (§3). The hash shows which bytes were evaluated. It does not show that the evaluator ran honestly. Binding the ZK proof to these hashes and to evaluation commitments is future work.
- Evidence bundles (§10) are integrity-checked by their own hash. Anyone who can rewrite the database could also recompute a hash, so a stored hash protects against accidental or partial edits, not against an attacker who controls the whole store. Publishing the hash (Sepolia, planned) is what would make it tamper-evident to third parties.
- The ZK circuit proves only `score_v2 >= score_v1 + delta` over the integers it is given. It does not prove that the scores came from real runs or that the code is correct.

---

## 9. Results on the research candidates (real engine, this suite)

| Candidate (`backend/tests/fixtures/`) | Hidden | Public | C | Q | S |
|---|---|---|---|---|---|
| `flawed` | 2/10 | 2/5 | 100 | 60 | 52.0 |
| `gen_coder_no_value_check` | 6/10 | 4/5 | 100 | 100 | 80.0 |
| `gen_7b` | 9/10 | 5/5 | 100 | 98 | 94.6 |
| `gen_coder` | 9/10 | 4/5 | 100 | 100 | 95.0 |
| `gen_coder_sorts_in_place` | 9/10 | 5/5 | 100 | 100 | 95.0 |
| `reference_good` | 10/10 | 5/5 | 100 | 98 | 99.6 |

These are measured by the tests in `tests/test_evaluation_engine.py` and `tests/test_acceptance.py`:

- `flawed` -> `gen_7b` -> `reference_good` is accepted at each step.
- `gen_coder` -> `gen_coder_sorts_in_place` fixes the failing public test but breaks a hidden one, so it is rejected with `no_test_regression` and `aggregate_delta`.
- `gen_coder` -> identical code is rejected with `aggregate_delta` only.

---

## 10. Evidence bundles and negative evidence (Milestone 07A)

A bundle (`backend/app/services/bundle_service.py`) is a local, hidden-safe, hash-addressed export of one evidence record. Nothing is uploaded anywhere.

- **Eligible:** `validated_improvement` and `rejected_attempt` only. `invalid_comparison` rows and Critic proposals are refused, because they are not evidence about a revision.
- **Negative evidence:** a rejected attempt exports its exact failed term ids with their hidden-safe messages, for example `no_test_regression: 1 hidden test(s) passed in V1 but fail in V2`. Hidden tests are never named.
- **Contents:**
  - the commitment
  - both versions' code (or hashes only, with `include_code=false`) and their `code_sha256`
  - the four score dimensions
  - public per-test results, and hidden results as counts only
  - status and failed terms
  - a unified diff and a deterministic changelog derived from the stored data
  - both evaluations' provenance
  - the parent bundle hash: the bundle of the decision that made the previous best version the best, or `null` for V1
- **Canonical form:** sorted keys, no whitespace, UTF-8, no NaN or Infinity. The bundle is built only from stored, immutable data, so rebuilding it gives identical bytes and an identical `bundle_sha256`. A test changes every leaf of a bundle one at a time and checks that the hash changes each time.
- **Storage:** `evidence_bundles`, one row per (record, `include_code`). SQLite triggers abort UPDATE and DELETE. If they are bypassed, `GET /api/evidence/{id}/bundle` reports `hash_valid: false`.
- **Code integrity at export:** if either version's stored code no longer hashes to the evaluated `code_sha256`, export is refused (409 `CODE_HASH_MISMATCH`).
- **Hidden-data guard:** after every test in the suite, an autouse fixture (`tests/bundle_scan.py`) scans every bundle that test wrote. It looks for every hidden test id of every registered suite, the synthetic hidden ids used by gate tests, and hidden test descriptions and literal inputs. It checks every field except the candidate source (`code`, `diff`), which is generator output. A separate test plants each kind of leak to confirm the scanner catches it.

---

## 11. The orchestrator and the evaluator (Milestone 07B)

The orchestrator (`backend/app/services/orchestrator.py`) generates versions with the Featherless Generator and asks the Critic for advice. **Neither model takes part in scoring or acceptance.** Every version goes through the same `evaluate_version` and `decide_acceptance` described above.

- **Stop on acceptance:** an accepted V2 completes the run. V3 is attempted only after a rejected V2 when `max_revisions = 2`. If every permitted revision is rejected, the run ends `completed_no_improvement`.
- **Hidden tests stay out of prompts.**
  - The Generator receives public tests and public failures only.
  - The Critic additionally receives the hidden pass count (two numbers) and the gate's failed-term messages, which count hidden tests without naming them.
  - `backend/app/agents/context.py` is the only bridge from suite or evaluation data to a prompt. A test scans every prompt of several full runs for every hidden id, description and literal input or expected value.
- **The Critic's output is advisory.** It is schema-validated, stored as `unvalidated_proposal`, and never read by the gate. A test feeds a Critic reply that says "accept as is" and checks that the decision is unchanged.
- **Observed with the fixtures:** after `gen_coder`, `reference_good` is **rejected**. It passes every test, but its code quality (98, from cyclomatic complexity 11) is below `gen_coder`'s 100, and no dimension may regress. This is the policy working as specified; it also shows how a one-step complexity difference can block an otherwise better version. Whether Q should be allowed to drop when P rises is a policy question for the Project Architect, and the policy is unchanged.
