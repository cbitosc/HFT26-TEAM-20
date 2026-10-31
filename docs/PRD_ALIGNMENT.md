# AutoEvolve Protocol: PRD Alignment

**Date:** October 30, 2026
**Source:** "AutoEvolve Protocol: Final PRD, Architecture and UI Workflow" (planning phase). Where it conflicts with the earlier `SPEC.md`, the PRD wins.

The PRD says its status labels "reflect team notes, not a repository audit". The table in Section 2 is a repository audit: every "Implemented" item exists in this repository and is covered by `backend/tests/` (439 tests passing at the time of writing).

---

## 1. Decisions on the PRD's open questions

| # | PRD open decision | Decision | Reason |
|---|---|---|---|
| 1 | Two or three scoring dimensions | **Three** (P, C, Q), weights 0.5 / 0.3 / 0.2, unchanged | The audit found C is computed from interface-contract checks and does not reuse pass/fail results, so nothing is double-counted. C is weak (almost always 100 for working code); this is documented in `docs/EVALUATION_ENGINE.md` §4. Changing the formula would also change the database constraints and the score history for no measured gain |
| 2 | Value of delta | **1.0 aggregate point** | Above float noise (1e-9); below every meaningful increment (one hidden test = 5.0, one quality check = 4.0, one contract check = 6.0); an integer, as the existing circuit requires. A complexity-only step (0.4) does not count. Derivation in `docs/EVALUATION_ENGINE.md` §5 |
| 3 | Who authors Agent B's independent suite | Open (Agent B is not built) | |
| 4 | Public or private by default | Private | Nothing is published; there is no publish path yet |
| 5 | Who holds hidden tests in production | Open. For the demo the backend holds them as code | The hidden tests are in the repository, so they are hidden from agents and API clients but not secret |
| – | Dashboard technology | **React web app**, replacing Streamlit | The PRD specifies React (Sections 7 and 10). `AGENTS.md` now names a web dashboard with the same rule: HTTP calls to FastAPI only. `docs/DASHBOARD_SPEC.md` is the older Streamlit design and is kept for its page content |
| – | Hidden-suite source for the demo | Backend-defined split of the merge-intervals suite: 5 public, 10 hidden | User upload of sealed suites requires storage that keeps them from agents and logs. It is not built |
| – | Invalid comparisons | Stored in their own table; the version stays pending | Decisions are final, so a missing evaluation or configuration mismatch must not permanently reject a revision (PRD: "this is not a bad revision") |
| – | Pass-rate source | Hidden tests only; public tests must not regress but do not score | PRD: "The headline number is hidden-suite accuracy, because the gate uses it" |

---

## 2. Requirement status (repository audit)

| PRD item | Status | Where |
|---|---|---|
| FR-1 Loop V1 to V3, stop on acceptance or budget | Implemented (Milestone 07B): orchestrator, `POST /api/executions/{id}/run`. Verified with a scripted fake LLM; no live run recorded yet | `services/orchestrator.py` |
| FR-2 Public and hidden tests; generator has no hidden-test access | Implemented: the Generator's prompt holds public tests and public failures only; the Critic gets hidden counts only; every prompt is scanned in tests | `evaluation/suite.py`, `agents/context.py` |
| FR-3 Provenance on every evaluation | Implemented: suite hashes, evaluator config and hash, scoring-rule version and hash, delta, environment, ids, time. No runner image digest (no container) | `evaluation/provenance.py`, `services/evaluation_service.py` |
| FR-4 Strict gate, atomic with the evidence write | Implemented | `evaluation/gate.py`, `services/acceptance_service.py` |
| FR-5 Four evidence statuses; failed term stored; invalid comparisons separate | Implemented: `evidence_records` (validated, rejected), `invalid_comparisons`, Critic feedback as `unvalidated_proposal` | `models/evidence.py`, `GET /api/executions/{id}/evidence` |
| FR-6 Lesson validator (causal replay) | Not implemented | |
| FR-7 Egress gate | Not implemented | |
| FR-8 Pinata upload, Sepolia registry | Not implemented | |
| FR-9 Narrow ZK proof | Circuit exists as a standalone prototype (development-only setup), not integrated. Integer encoding of scores is defined in `evaluation/policy.py`, not used | `zk/` (unchanged) |
| FR-10 Agent B transfer test | Not implemented | |
| FR-11 Capabilities with audit log | Not implemented | |
| FR-12 Web dashboard | Not implemented (React planned) | |
| Hidden-suite commitment before generation | Implemented in SQLite at execution creation. On-chain: not implemented | `models/execution.py` |
| Container sandbox | Not implemented. The evaluator is a subprocess and is **not a security sandbox**; execution is refused in `production` unless explicitly allowed | `evaluation/execution.py` |
| Runner quorum, challenge window | Not implemented | |

### 2.1 PRD Section 7 ("What we use"): PRD label vs repository status

The PRD's table was written from team notes. This is the same table checked against the repository. Only rows whose real status differs from the PRD label have changed.

| Layer | PRD label | Repository status |
|---|---|---|
| Generator and Critic (Featherless) | In use | **Implemented** in the backend (`app/llm`, `app/agents`, orchestrator); tested with a fake LLM; live smoke script exists, not yet run |
| Evaluator (subprocess test runner) | Implemented per team notes, not audited | **Implemented** and tested (`backend/app/evaluation/`); not a security sandbox |
| Acceptance gate (strict non-regression) | Implemented per team notes, not audited | **Implemented** and tested, including atomicity and concurrency (`evaluation/gate.py`, `services/acceptance_service.py`) |
| Records (SQLite) | Implemented per team notes | **Implemented** (`backend/app/models/`) |
| Provenance hashes (suite, configuration, scoring-rule version) | Planned | **Implemented**: suite, public-suite and hidden-suite hashes, evaluator configuration hash, scoring-rule version and hash, on every evaluation (`evaluation/provenance.py`) |
| Evidence statuses (`validated_improvement`, `rejected_attempt`, `unvalidated_proposal`, `invalid_comparison`) | (PRD Section 5; milestone 2) | **Implemented** (`models/evidence.py`, `GET /api/executions/{id}/evidence`) |
| Hidden-test commitment | Planned (hash on Sepolia) | **Implemented in SQLite**: recorded at execution creation, before any version (`models/execution.py`). The on-chain (Sepolia) copy is still **Planned** |
| Container sandbox | Planned | Planned |
| Runner quorum | Planned (stretch) | Planned |
| Lesson validator | Planned | Planned |
| Egress gate | Planned | Planned |
| Storage (IPFS via Pinata) | Planned | Planned |
| Proof (Circom) | Exists per team notes; binding is future | Standalone prototype exists (`zk/`), development-only setup, not integrated; binding is future |
| Registry (Solidity on Sepolia) | Planned | Planned |
| Retrieval | Planned | Planned |
| Dashboard (React) | Planned | Planned |

---

## 3. PRD milestones

| # | Milestone | State |
|---|---|---|
| 1 | Audit scoring dimensions, gate atomicity and provenance; set delta; freeze the predicate | Done (this document, `docs/EVALUATION_ENGINE.md`) |
| 2 | Provenance hashes and four evidence statuses | Done |
| 3 | Dashboard: New Task, Run, Compare | Not started. The backend now serves what Run and Compare need: hidden/public counts, the gate result with failed terms, the commitment and evidence |
| 4 | Egress gate and lesson validator | Not started |
| 5 | Pinata, Sepolia registry, narrow proof | Not started (circuit prototype only) |
| 6 | Agent B transfer experiment and Memory view | Not started |
| 7 | Capabilities with audit trail | Not started |

---

## 4. Known gaps a reviewer should know about

- `version_service.decide_version` and `version_service.record_evaluation` are internal primitives with no API route. Code that calls them can still bypass the gate. The proof-stage guard does not trust their output: it requires an evidence record and re-checks the evaluations.
- A stored score is not bound to the code it measured by a hash; it references the version id.
- The schema changed (new columns and tables). There is no migration tool, so an existing development database must be deleted and recreated (`python -m app.init_db`).
- The Generator and Critic are wired in (Milestone 07B). The rule that the Generator never sees hidden tests is enforced in prompt construction (`app/agents/context.py`) and checked by scanning every prompt in tests. These are model inputs only; a live model's behaviour has not been measured in this milestone.
