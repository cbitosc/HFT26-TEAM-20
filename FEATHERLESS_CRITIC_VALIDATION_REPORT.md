# Featherless Critic Validation Report (Prompt 03.3)

**Date:** October 30, 2026
**Run:** `eval/results/critic_validation_run_20261030_235825.json` (12 inference requests, all HTTP 200)
**Status:** Research result. No application code was written. No further model requests will be made until the Project Architect approves.

## Summary

Giving the Critic the evaluator's real failure output changed its behavior a great deal. In Prompt 03.2, without that evidence, both models missed the real defect in all 8 reviews of generated code. In this run, 3 of the 4 reviews of generated code identified every real defect. This comparison is confounded, because the prompt format also changed and I did not run a no-evidence control with the new prompt.

The Critics are still not reliable enough to trust on their own:

- The 7B model made a false or evaluator-contradicting claim in 2 of 3 responses, and its advice made one revision worse (12/14 to 11/14).
- The 32B model made no false claims, but still missed one defect on the multi-defect candidate while reporting confidence 1.0.
- All six responses reported confidence of 0.95 or higher, including the wrong ones. Confidence carries no signal here.
- Schema validity and automated contradiction checks passed on all six responses, while manual review found real errors. Those checks cannot stand in for correctness.

On revisions, the Generator received the evaluator output with and without Critic feedback:

| Revision variant | Net tests passed after revision (2 candidates, baseline 25/28) |
|---|---|
| Control (evaluator output only) | 25/28 (no net gain) |
| With 7B Critic | 25/28 (+1 on one candidate, -1 on the other) |
| With 32B Critic | 27/28 (+1 on each candidate) |

That is a weak positive signal for the 32B Critic, based on 2 candidates and 1 sample each. It is not evidence of a reliable benefit.

## 1. Model availability and pricing

Retrieved from `GET /v1/models/{id}` before any inference request.

| | Qwen/Qwen2.5-7B-Instruct | Qwen/Qwen2.5-32B-Instruct |
|---|---|---|
| Status | active | active |
| Available on current plan | yes | yes |
| Context length | 32,768 | 32,768 |
| Max completion tokens | not reported by API | not reported by API |
| Gated | no | no |
| Price per 1M input tokens | $0.17 | $0.68 |
| Price per 1M output tokens | $0.20 | $1.20 |
| Concurrency cost | 1 | 2 |
| Availability tier at start | warm, hot (live) | warm, **not hot** |

The 32B model was verified and used as specified. No substitution occurred. Reported request cost matched `tokens x listed price` exactly on all 12 requests (maximum difference $0.0000000000).

## 2. Exact candidates tested

The candidates are saved in `eval/candidates/`. B and C were extracted unchanged from the stored Prompt 03.2 `gen_initial` responses. A is the `FLAWED_CODE` constant from `featherless_compare.py`.

| ID | File | Source | Known defects | Evaluator result |
|---|---|---|---|---|
| A | `A_flawed.py` | seeded flaw code | **D1** mutates the input (`intervals.sort()`); **D2** crashes on empty list (`merged = [intervals[0]]`); **D3** touching intervals not merged (`<` should be `<=`); **D4** contained interval shrinks the end (`(last_start, end)` should use `max`); **D5** no validation | 4 of 14 pass |
| B | `B_gen_7b.py` | actual output of Qwen2.5-7B-Instruct | **B1** mutates the input (`intervals.sort(key=...)`) | 13 of 14 pass |
| C | `C_gen_coder.py` | actual output of Qwen2.5-Coder-7B-Instruct | **C1** never sorts; **C2** no integer type check on values | 12 of 14 pass |

The Critic task was the same `merge_intervals` task and the same 14-test hidden suite as Prompt 03.2.

## 3. Evaluator evidence supplied

**The stored Prompt 03.2 files were not sufficient on their own.** They hold the candidate code and failing test names, but no expected values, actual values or tracebacks. I reconstructed that detail by re-executing the stored code against the suite. Safeguards, all passed (`eval/results/critic_validation_evidence.json`):

- The new capture reports the same pass/fail map as the Prompt 03.2 suite for all three candidates.
- Failing tests for B and C match the stored Prompt 03.2 results exactly.
- Failing tests match the ground-truth defect lists for all three candidates.
- A correct reference implementation passes 14/14 under both runners.

The capture does not short-circuit. A failing test therefore shows all its failing sub-checks, where the original boolean test stopped at the first. That adds detail without changing any pass/fail outcome.

Each Critic received, in the same byte-identical prompt (prompt token counts matched: 1467 / 1221 / 1376 for A / B / C):

1. The original task requirements.
2. The candidate code.
3. For each failing test: name, exact call, expected result, actual result, and the traceback line from the code under review when an exception occurred.
4. The names of the passing tests.

Candidate C's evidence, as an example (real execution output):

```
FAILED TEST: unsorted_input
  call:     merge_intervals([(8, 10), (1, 3), (2, 6)])
  expected: returns [(1, 6), (8, 10)]
  actual:   returned [(8, 10)]
FAILED TEST: typeerror_non_int_values
  call:     merge_intervals([(1.5, 2.5)])
  expected: raises TypeError
  actual:   returned [(1.5, 2.5)] without raising
```

The Critic prompt asked for root cause, code location, why observed differs from expected, a specific correction, a confirmed/possible label per issue, no invented defects, and strict JSON with the fields `root_cause`, `evidence`, `identified_issues`, `suggested_changes`, `confidence`, `no_issues`. Temperature was 0 and a single sample was taken per configuration. The architecture document specifies the Critic's input as "generated code, evaluation scores, task requirements", so passing failure details is richer than the spec and would be a change to approve.

## 4. Critic responses and defect-by-defect accuracy

The scoring rubric was written into the harness file header before any request was made. Verdicts are my manual reading of each response (recorded in `critic_validation_judgments.json`). The harness's automated checks, covering schema validity and contradiction flags, were used only as aids.

All six responses parsed as strict JSON with no schema errors, and the automated contradiction check flagged none. Manual review nevertheless found two responses with false claims (A-7B, C-7B) and one response with a missed defect (A-32B).

### Candidate A (five seeded defects)

| Defect | Failing tests | 7B Critic | 32B Critic |
|---|---|---|---|
| D1 mutates input | `input_not_mutated` | **Missed.** Its sorting issue is a false claim (below). | **Found.** Exact line, fix `sorted(list(intervals))` |
| D2 empty-list crash | `empty` | **Found.** Line 3; fix `if not intervals: return []` | **Found.** Line 3; no fix offered |
| D3 touching not merged | `touching`, `chain` | **Found.** Fix `<=` | **Found.** Fix `<=` |
| D4 contained shrinks | `contained` | **Partial.** Blames the `start < last_end` condition; the real defect is the end assignment | **Missed.** It listed `contained` in its own evidence array but no issue explains it |
| D5 no validation | 5 tests | **Partial.** Covers 2 of 5 validation tests; "fix" is to add tests | **Found.** All 5 tests mapped across 3 issues; fix is generic |

Both Critics cited "line 4" for the `if start < last_end` line, which is actually line 6. The quoted code was right.

### Candidate B (one defect)

| Defect | 7B Critic | 32B Critic |
|---|---|---|
| B1 mutates input | **Found.** Exact line `intervals.sort(key=lambda x: x[0])`; fix `sorted(...)` | **Found.** Same location and fix |

### Candidate C (two defects)

| Defect | 7B Critic | 32B Critic |
|---|---|---|
| C1 never sorts | **Found.** Fix is in-place `intervals.sort(...)` (see below) | **Found.** Same in-place fix |
| C2 no integer check | **Missed (misdiagnosed).** Says non-integers "raise a TypeError instead of a ValueError", which contradicts the evaluator output ("returned ... without raising"); advises changing `TypeError` to `ValueError`, which violates the requirement | **Found.** Specific `isinstance(interval[0], int)` check raising `TypeError` |

For C1, both Critics recommend in-place sorting. That fixes `unsorted_input` but would break `input_not_mutated`, which candidate C currently passes.

### Tallies (from `eval/critic_validation_summary.py`)

| Critic | Candidates | Defects | Found | Partial | Missed | False claims | Contradicts evaluator evidence | Confidence not justified |
|---|---|---|---|---|---|---|---|---|
| 7B | A | 5 | 2 | 2 | 1 | 1 | 1 of 1 | 1 of 1 |
| 7B | B, C | 3 | 2 | 0 | 1 | 1 | 1 of 2 | 1 of 2 |
| 32B | A | 5 | 4 | 0 | 1 | 0 | 0 of 1 | 1 of 1 |
| 32B | B, C | 3 | 3 | 0 | 0 | 0 | 0 of 2 | 0 of 2 |
| **7B total** | | **8** | **4** | **2** | **2** | **2** | **2 of 3** | **2 of 3** |
| **32B total** | | **8** | **7** | **0** | **1** | **0** | **0 of 3** | **1 of 3** |

The 7B's C2 misdiagnosis is counted both as a miss and as a false claim.

## 5. False positives and false negatives

**False positives (false or evaluator-contradicting claims):**

- **A, 7B:** claims the code "does not sort the intervals" and cites `line 2: intervals.sort()`, the very line that sorts. The evaluator output for `input_not_mutated` shows the list was sorted. It then attributes the `touching`, `contained`, `chain` and `empty` failures to that nonexistent sorting problem.
- **C, 7B:** the C2 misdiagnosis above.
- **32B:** none.

**False negatives:**

- **A, 7B:** D1 (despite `input_not_mutated` being in the evidence); D4 and D5 only partially.
- **A, 32B:** D4. This was the subtlest seeded defect. Both Critics missed it or got it only partially.
- **C, 7B:** C2.

**Confidence.** All six responses reported 0.95 or higher. This included the 7B's wrong A and C responses (0.95 each) and the 32B's A response (1.0) that missed D4. Confidence was not informative.

**Automated check.** The harness records which failing tests are cited by at least one issue. It flagged the 32B's missed `contained` and the 7B's four uncited tests (including `input_not_mutated`). It would not have caught the 7B's C2 misdiagnosis, because that response cited both failing tests. I observed this and did not test it as a design.

## 6. Revision results and code-diff findings

Generator for all revisions: `Qwen/Qwen2.5-7B-Instruct`, so the Critic is the controlled variable. Every revision was run against the unchanged 14-test suite. Diffs are in the run file.

| Candidate | Variant | Before | After | Fixed | Regressed | Code change |
|---|---|---|---|---|---|---|
| B | 7B Critic | 13 | **14** | `input_not_mutated` | none | `sort()` replaced by `sorted()` copy; loop uses the copy |
| B | 32B Critic | 13 | **14** | `input_not_mutated` | none | same two-line change |
| C | 7B Critic | 12 | **11** | `unsorted_input` | `input_not_mutated`, `typeerror_bad_element` | added in-place sort; **changed `TypeError` to `ValueError`**, following the Critic's incorrect advice |
| C | 32B Critic | 12 | **13** | `typeerror_non_int_values` | none | added the `isinstance` integer check from the Critic's suggestion; **did not add the sort** |

Findings from the diffs:

- On candidate B (one defect), both Critics produced the exact fix and the Generator applied it correctly.
- On candidate C, the 7B Critic's wrong advice was applied literally and made the code worse than the control.
- With the 32B Critic, the Generator applied the integer-check suggestion but ignored the sort suggestion, so `unsorted_input` was never fixed. Instead it added a test expecting a `ValueError("Intervals must be sorted by start.")` that the code does not raise.
- All three revisions of candidate C still fail their own embedded tests (exit code 1), as the original did. The Generator's self-written tests are not reliable evidence.
- Revisions of B pass their own tests.

## 7. Control revision results

The control received the same task requirements, code and exact evaluator output, with no Critic feedback and otherwise identical wording.

| Candidate | Control result | What happened |
|---|---|---|
| B | 13 to 13 | The Generator returned **byte-identical code**. It ignored the failing test. |
| C | 12 to 12 | Fixed `unsorted_input` using in-place sort, which regressed `input_not_mutated`. No integer check added. Net zero. |

**Attribution:**

| Candidate | Evaluator evidence alone | + 7B Critic | + 32B Critic | Attribution |
|---|---|---|---|---|
| B | no improvement | improved | improved | **Critic feedback** (given evaluator evidence). Evidence alone was not enough for this Generator in this sample. |
| C | net zero (one fix, one regression) | worse than control | improved | **7B: negative. 32B: positive**, through the C2 fix. The C1 fix did not occur. |

Both Critics' B results rest on a single control sample in which the Generator happened to return unchanged code, so they could be sampling noise. I do not claim Critic-driven improvement beyond this one sample. Across B and C, 3 of the 6 revisions improved the score (all with a Critic), 2 were net zero, and 1 got worse.

## 8. Actual latency, token usage and cost

All values come from the stored run file, with no estimates. Usage and cost were present on every response. Latency uses `time.perf_counter()`.

| Request | Model | Latency (s) | Prompt tokens | Completion tokens | Reported cost (USD) |
|---|---|---:|---:|---:|---:|
| Critic A | 7B | 7.4 | 1467 | 614 | 0.00037219 |
| Critic A | 32B | 44.9 | 1467 | 676 | 0.00180876 |
| Critic B | 7B | 2.9 | 1221 | 181 | 0.00024377 |
| Critic B | 32B | 7.1 | 1221 | 226 | 0.00110148 |
| Critic C | 7B | 4.9 | 1376 | 412 | 0.00031632 |
| Critic C | 32B | 10.3 | 1376 | 405 | 0.00142168 |
| Revise B control | 7B | 5.5 | 944 | 491 | 0.00025868 |
| Revise B + 7B Critic | 7B | 6.7 | 1161 | 495 | 0.00029637 |
| Revise B + 32B Critic | 7B | 13.3 | 1206 | 468 | 0.00029862 |
| Revise C control | 7B | 31.8 | 1099 | 716 | 0.00033003 |
| Revise C + 7B Critic | 7B | 8.0 | 1547 | 601 | 0.00038319 |
| Revise C + 32B Critic | 7B | 9.4 | 1540 | 736 | 0.00040900 |

| Group | Calls | Mean latency | Cost |
|---|---:|---:|---:|
| 7B Critic | 3 | 5.1 s (median 4.9) | $0.000932 |
| 32B Critic | 3 | 20.7 s (median 10.3) | $0.004332 |
| 7B revisions | 6 | 12.5 s | $0.001976 |
| **Total** | **12** | | **$0.007240** |

- The 32B Critic cost 4.65 times as much per call as the 7B, and its median latency was about twice as long.
- The 32B's first call took 44.9 s. The model was not hot at the start, so cold-start time is included and cannot be separated out.
- The pre-run worst-case bound was $0.0221. Actual spend was $0.00724, which is under 1% of the $1.00 budget.
- No warm-up requests were made, no calls were repeated, and no request returned an error.

## 9. Limitations

- **Small and single-rater.** Three candidates, one task, one sample per configuration. One agent, who designed the experiment, scored the Critic responses after seeing them. Differences of one or two defects are not statistically meaningful.
- **No no-evidence control with the new prompt.** The improvement over Prompt 03.2 combines the added evidence with changes to the prompt and schema. I cannot say how much is due to the evidence alone.
- **Easy candidates.** For B and C the failing test almost names the defect, so identifying it is close to translation. Accuracy dropped on A, with its ten simultaneous failures (32B 4 of 5, 7B 2 of 5 plus 2 partial). This is an observation, not a tested relationship.
- **Revision noise.** The B control returned unchanged code in a single sample. Featherless documents `seed` as unreliable, so a rerun may differ.
- **Cost and latency.** Measured on one occasion. The 32B figure includes a possible cold start.
- **Local execution.** LLM-generated code ran in a subprocess with a timeout and closed stdin, not in a sandbox.
- **Not tested:** other tasks, other Critic models, function calling, a Critic reviewing its own Generator's output with evidence, and an accept-only-if-improved loop.

## 10. Recommendation

**Is the 7B model now acceptable as a Critic?**
Not as a trusted Critic. With evidence it handled the single-defect case as well as the 32B. But it contradicted the evaluator in 2 of 3 responses, gave confidence 0.95 or higher on both, and its advice made one revision worse (12 to 11). Use it only if its output is treated as untrusted and gated.

**Does the 32B model materially improve Critic accuracy?**
Directionally yes, but this is not established. It found 7 of 8 defects against 4 plus 2 partial for the 7B, made no false claims against 2, and produced +2 net test gain against 0 in revisions. It still missed one defect while reporting confidence 1.0. It costs about 4.6 times as much per call and is slower, though each call is still about a tenth of a cent. With this sample size the advantage could be chance.

**Does Critic feedback improve results beyond evaluator evidence alone?**
Not demonstrated. The control gained nothing on either candidate. The 32B Critic added a test gain on both (+1 each), but this is two candidates with one sample each, and one control was a no-op. The 7B Critic was mixed (+1 and -1). This is a weak positive signal for the 32B and not a result to build claims on.

**Should AutoEvolve proceed with a Critic-based revision loop?**
Yes, with these conditions, and without claiming the Critic is reliable:

1. The evaluator is the sole judge of improvement. A revision counts only if its measured score rises and no previously passing test regresses. In this run, applying that rule after the fact would have rejected 3 of the 6 revisions (including the 11/14 one) and accepted the three that improved.
2. The Critic receives the evaluator's failure details, not only scores. This is a change to the spec's stated Critic input and needs your approval.
3. Critic text and confidence are shown as "model opinion" and never as a result or a metric.
4. A ZK improvement claim is generated only from evaluator-measured scores.

**What is the safest architecture if neither model is reliable?**
Keep the existing Generator, Evaluator, Critic, Generator order, but make it evaluator-led:

1. Always give the Generator the raw evaluator failures (the control path).
2. Optionally also run the Critic path.
3. Evaluate every candidate revision with the same suite.
4. Keep the best verified version. If no revision improves, keep the previous version and record "no improvement" instead of inventing one.
5. Log each Critic claim against the evaluator outcome.

I have not tested this design end to end. It follows from the observations above and from the fact that the evaluator caught every regression in this run.

Each measured gain here was at most +1 test (about 7 percentage points of pass rate). The ZK `delta` threshold will need to be chosen with that scale in mind, and demo tasks should have enough failing tests for a visible improvement.

I suggest a small follow-up before committing to the 32B model: run both Critics on several different tasks, including a no-evidence control, with a second rater. That needs your approval, because it spends more budget.

## Files

**Created:**

- `eval/critic_validation.py` (harness with pre-registered rubric; subcommands `prepare` and `run`)
- `eval/critic_validation_summary.py` (computes the tables above)
- `eval/candidates/A_flawed.py`, `B_gen_7b.py`, `C_gen_coder.py`
- `eval/results/critic_validation_evidence.json`
- `eval/results/critic_validation_run_20261030_235825.json`
- `eval/results/critic_validation_judgments.json`
- `FEATHERLESS_CRITIC_VALIDATION_REPORT.md`
- `eval/__pycache__/` (Python bytecode, incidental)

**Modified:** none. `eval/featherless_compare.py` was imported and reused, not edited.

**Outside the repository:** `secret_scan.py` in `%TEMP%`.

**Prompt 03.2 result files:** the three `featherless_*.json` files have the same SHA-256 hashes as before this task, so they are unchanged. The credential scan found 0 of 23 project files containing the API key.

**Reproduce:**

```
python eval/critic_validation.py prepare
python eval/critic_validation.py run
python eval/critic_validation_summary.py
```
