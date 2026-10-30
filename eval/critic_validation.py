"""Prompt 03.3 - evaluator-guided Critic validation (research harness, not application code).

Subcommands
  prepare   Local only, no API calls. Extracts the exact candidates from the stored Prompt 03.2
            results, executes them against the UNCHANGED 14-test suite with failure-detail capture,
            and verifies the capture reproduces the Prompt 03.2 pass/fail results exactly.
  run       Bounded Featherless experiment (needs FEATHERLESS_API_KEY; never printed or written).

Reuses featherless_compare.py (task text, request/usage/cost recording, secret-output check,
hidden test suite). Prompt 03.2 result files are only read, never written.

PRE-REGISTERED SCORING RUBRIC (fixed before any request is made; judgments are made by a human
reading each response, keyword matching is only an aid):
  identified (TP)  an identified_issue whose location points at the defective construct (or names
                   the missing behavior) AND whose description gives the correct cause.
  partial          correct cause but vague/wrong location, or only part of the defect (for D5:
                   only the TypeError half or only the ValueError half).
  fix adequate     the suggested change, if applied, would plausibly remove that defect's failing
                   tests without breaking others.
  false positive   an issue asserting something false: contradicts a passing test, or misdescribes
                   the code under review.
  valid-other      a true statement about a requirement violation the evaluator does not test
                   (e.g. missing docstring); neither TP nor FP.
  confidence       NOT justified if confidence >= 0.8 and the response has any FN or FP.
"""
import difflib
import hashlib
import json
import linecache
import math
import os
import pathlib
import subprocess
import sys
import tempfile
import traceback
import datetime

HERE = pathlib.Path(__file__).resolve().parent
RESULTS = HERE / "results"
CANDS = HERE / "candidates"
MARK = "@@RESULT@@"
PRIOR_FILES = [
    "featherless_compare_20261030_233408.json",
    "featherless_followup_20261030_233845.json",
    "featherless_control_20261030_234108.json",
]
EVIDENCE_FILE = RESULTS / "critic_validation_evidence.json"

GENERATOR = "Qwen/Qwen2.5-7B-Instruct"
CRITIC_A = "Qwen/Qwen2.5-7B-Instruct"
CRITIC_B = "Qwen/Qwen2.5-32B-Instruct"
BUDGET_USD = 1.00
MAX_TOKENS_CRITIC = 1800
MAX_TOKENS_REVISE = 1800
CHARS_PER_TOKEN_FLOOR = 2.0  # deliberately pessimistic (real text is ~3.5-4 chars/token)

# Ground truth, established from the unchanged hidden suite (verified against evidence in `prepare`).
DEFECTS = {
    "A_flawed": [
        {"id": "D1", "name": "mutates the caller's list", "location": "line 2: intervals.sort()", "tests": ["input_not_mutated"]},
        {"id": "D2", "name": "crashes on an empty list", "location": "line 3: merged = [intervals[0]]", "tests": ["empty"]},
        {"id": "D3", "name": "touching intervals are not merged", "location": "line 6: `start < last_end` should be `<=`", "tests": ["touching", "chain"]},
        {"id": "D4", "name": "contained interval shrinks the merged end", "location": "line 7: (last_start, end) should use max(last_end, end)", "tests": ["contained"]},
        {"id": "D5", "name": "no input validation", "location": "missing behavior: TypeError / ValueError checks",
         "tests": ["typeerror_not_list", "typeerror_bad_element", "typeerror_non_int_values",
                   "valueerror_start_gt_end", "validation_applies_to_all"]},
    ],
    "B_gen_7b": [
        {"id": "B1", "name": "mutates the caller's list", "location": "intervals.sort(key=lambda x: x[0])", "tests": ["input_not_mutated"]},
    ],
    "C_gen_coder": [
        {"id": "C1", "name": "never sorts the input", "location": "main loop iterates `intervals` in the given order; no sort anywhere", "tests": ["unsorted_input"]},
        {"id": "C2", "name": "no integer type check on interval values", "location": "validation loop checks only tuple-ness and len == 2", "tests": ["typeerror_non_int_values"]},
    ],
}
CANDIDATE_LABELS = {
    "A_flawed": "Deliberately flawed implementation (FLAWED_CODE constant, 5 seeded defects)",
    "B_gen_7b": "Qwen/Qwen2.5-7B-Instruct actual generated solution (Prompt 03.2 gen_initial)",
    "C_gen_coder": "Qwen/Qwen2.5-Coder-7B-Instruct actual generated solution (Prompt 03.2 gen_initial)",
}


# --------------------------------------------------------------------------
# Evidence mode (subprocess): same 14 tests as featherless_compare.py, but records
# call / expected / actual / traceback for every check. No short-circuiting, so a
# failing test reports all of its failing sub-checks. Pass/fail per test is identical.
# --------------------------------------------------------------------------
def evidence_mode(path):
    src = pathlib.Path(path).read_text(encoding="utf-8")
    linecache.cache["candidate"] = (len(src), None, src.splitlines(True), "candidate")
    out = {"load_error": None, "tests": []}
    ns = {"__name__": "candidate"}
    try:
        exec(compile(src, "candidate", "exec"), ns)
        f = ns["merge_intervals"]
    except BaseException as e:  # noqa: BLE001
        out["load_error"] = f"{type(e).__name__}: {e}"[:200]
        print("\n" + MARK + json.dumps(out))
        return

    def rep(v, n=220):
        r = repr(v)
        return r if len(r) <= n else r[:n] + "..."

    def frames(e):
        fr = [x for x in traceback.extract_tb(e.__traceback__) if x.filename == "candidate"]
        return [f"line {x.lineno}, in {x.name}: {(x.line or '').strip()}" for x in fr[-3:]]

    def run(*args):
        try:
            return True, f(*args)
        except BaseException as e:  # noqa: BLE001
            return False, e

    def exc_text(e):
        return f"raised {type(e).__name__}: {e}"

    def callstr(args):
        return "merge_intervals(" + ", ".join(rep(a) for a in args) + ")"

    def value_check(args, expected):
        ok, v = run(*args)
        c = {"call": callstr(args), "expected": f"returns {rep(expected)}"}
        if not ok:
            return {**c, "actual": exc_text(v), "trace": frames(v), "passed": False}
        return {**c, "actual": f"returned {rep(v)}", "trace": [], "passed": v == expected}

    def raises_check(exc, args):
        ok, v = run(*args)
        c = {"call": callstr(args), "expected": f"raises {exc.__name__}"}
        if ok:
            return {**c, "actual": f"returned {rep(v)} without raising", "trace": [], "passed": False}
        passed = isinstance(v, exc)
        return {**c, "actual": exc_text(v) + (" (as expected)" if passed else ""),
                "trace": [] if passed else frames(v), "passed": passed}

    def not_mutated():
        inp = [(5, 6), (1, 2), (2, 3)]
        snap = list(inp)
        call = f"merge_intervals(inp) where inp = {rep(snap)}"
        ok, res = run(inp)
        if not ok:
            return [{"call": call, "expected": "returns normally and leaves inp unchanged",
                     "actual": exc_text(res), "trace": frames(res), "passed": False}]
        a = {"call": call, "expected": f"input list unchanged: {rep(snap)}",
             "actual": f"input list after the call: {rep(inp)}", "trace": [], "passed": inp == snap}
        b = {"call": call, "expected": "returns a different list object than inp",
             "actual": "returned the same list object as inp" if res is inp else "returned a different list object",
             "trace": [], "passed": res is not inp}
        return [a, b]

    def returns_tuples():
        args = ([(1, 2), (2, 3), (7, 8)],)
        ok, v = run(*args)
        c = {"call": callstr(args), "expected": "returns a list in which every item has type tuple"}
        if not ok:
            return [{**c, "actual": exc_text(v), "trace": frames(v), "passed": False}]
        try:
            passed = all(type(x) is tuple for x in v)
            kinds = [type(x).__name__ for x in v]
        except BaseException:  # noqa: BLE001
            return [{**c, "actual": f"returned {rep(v)} (not iterable as a list)", "trace": [], "passed": False}]
        return [{**c, "actual": f"returned {rep(v)} with item types {kinds}", "trace": [], "passed": passed}]

    tests = [
        ("overlap", lambda: [value_check(([(1, 3), (2, 6), (8, 10)],), [(1, 6), (8, 10)])]),
        ("touching", lambda: [value_check(([(1, 3), (3, 5)],), [(1, 5)])]),
        ("contained", lambda: [value_check(([(1, 10), (2, 3)],), [(1, 10)])]),
        ("unsorted_input", lambda: [value_check(([(8, 10), (1, 3), (2, 6)],), [(1, 6), (8, 10)])]),
        ("chain", lambda: [value_check(([(1, 4), (4, 5), (5, 9), (10, 11)],), [(1, 9), (10, 11)])]),
        ("empty", lambda: [value_check(([],), [])]),
        ("single_point", lambda: [value_check(([(4, 4)],), [(4, 4)])]),
        ("input_not_mutated", not_mutated),
        ("returns_tuples", returns_tuples),
        ("typeerror_not_list", lambda: [raises_check(TypeError, (None,)), raises_check(TypeError, (((1, 2),),))]),
        ("typeerror_bad_element", lambda: [raises_check(TypeError, ([(1, 2), (3,)],)),
                                           raises_check(TypeError, ([(1, "a")],)),
                                           raises_check(TypeError, ([(1, 2), [3, 4]],))]),
        ("valueerror_start_gt_end", lambda: [raises_check(ValueError, ([(5, 1)],))]),
        ("validation_applies_to_all", lambda: [raises_check(ValueError, ([(1, 2), (9, 3)],))]),
        ("typeerror_non_int_values", lambda: [raises_check(TypeError, ([(1.5, 2.5)],)),
                                              raises_check(TypeError, ([("a", "b")],))]),
    ]
    for name, build in tests:
        try:
            checks = build()
        except BaseException as e:  # noqa: BLE001
            checks = [{"call": "(harness)", "expected": "-", "actual": exc_text(e), "trace": [], "passed": False}]
        out["tests"].append({"name": name, "passed": all(c["passed"] for c in checks), "checks": checks})
    print("\n" + MARK + json.dumps(out))


if len(sys.argv) == 3 and sys.argv[1] == "--evidence":
    evidence_mode(sys.argv[2])
    sys.exit(0)

# --------------------------------------------------------------------------
# Shared helpers (parent process)
# --------------------------------------------------------------------------
sys.path.insert(0, str(HERE))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass


def load_fc():
    import featherless_compare as fc  # exits with a message if FEATHERLESS_API_KEY is unset
    return fc


def sha256(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest().upper()


def prior_hashes():
    return {n: sha256(RESULTS / n) for n in PRIOR_FILES}


def run_marker(cmd):
    with tempfile.TemporaryDirectory() as d:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL, cwd=d)
    i = r.stdout.rfind(MARK)
    if i < 0:
        raise RuntimeError(f"no result marker; stderr tail: {r.stderr[-300:]}")
    return json.loads(r.stdout[i + len(MARK):])


def capture_evidence(path):
    return run_marker([sys.executable, str(pathlib.Path(__file__).resolve()), "--evidence", str(path)])


def suite_result(path):
    return run_marker([sys.executable, str(HERE / "featherless_compare.py"), "--hidden-tests", str(path)])


def evidence_text(ev):
    tests = ev["tests"]
    failed = [t for t in tests if not t["passed"]]
    passed = [t["name"] for t in tests if t["passed"]]
    lines = [f"EVALUATOR RESULT: {len(passed)} of {len(tests)} tests passed; {len(failed)} failed."]
    for t in failed:
        lines.append(f"\nFAILED TEST: {t['name']}")
        for c in t["checks"]:
            if c["passed"]:
                continue
            lines.append(f"  call:     {c['call']}")
            lines.append(f"  expected: {c['expected']}")
            lines.append(f"  actual:   {c['actual']}")
            for fr in c.get("trace", []):
                lines.append(f"  traceback (code under review): {fr}")
    lines.append("\nPASSED TESTS: " + (", ".join(passed) if passed else "(none)"))
    return "\n".join(lines)


# --------------------------------------------------------------------------
# prepare
# --------------------------------------------------------------------------
def cmd_prepare():
    fc = load_fc()
    CANDS.mkdir(exist_ok=True)
    before = prior_hashes()
    compare = json.loads((RESULTS / PRIOR_FILES[0]).read_text(encoding="utf-8"))
    followup = json.loads((RESULTS / PRIOR_FILES[1]).read_text(encoding="utf-8"))
    gen = {r["model"]: r for r in compare["requests"] if r["label"] == "gen_initial"}
    stored_failed = {
        "B_gen_7b": followup["evaluations"]["rescored_initial"]["Qwen/Qwen2.5-7B-Instruct"]["failed_tests"],
        "C_gen_coder": followup["evaluations"]["rescored_initial"]["Qwen/Qwen2.5-Coder-7B-Instruct"]["failed_tests"],
    }
    code = {
        "A_flawed": fc.FLAWED_CODE,
        "B_gen_7b": fc.extract_code(gen["Qwen/Qwen2.5-7B-Instruct"]["content"]),
        "C_gen_coder": fc.extract_code(gen["Qwen/Qwen2.5-Coder-7B-Instruct"]["content"]),
    }
    names = {"A_flawed": "A_flawed.py", "B_gen_7b": "B_gen_7b.py", "C_gen_coder": "C_gen_coder.py"}
    out = {"created": datetime.datetime.now().isoformat(timespec="seconds"), "prior_file_sha256": before,
           "candidates": {}, "ok": True}
    print("== Evidence reconstruction (local execution only, no API calls) ==")
    for cid, src in code.items():
        if src is None:
            sys.exit(f"STOP: could not extract stored code for {cid}")
        p = CANDS / names[cid]
        p.write_text(src, encoding="utf-8", newline="\n")
        ev = capture_evidence(p)
        suite = suite_result(p)
        ev_map = {t["name"]: t["passed"] for t in ev["tests"]}
        equivalent = ev_map == suite["tests"] and ev["load_error"] is None
        failed = sorted(k for k, v in ev_map.items() if not v)
        truth_union = sorted({t for d in DEFECTS[cid] for t in d["tests"]})
        matches_truth = failed == truth_union
        matches_stored = None if cid not in stored_failed else sorted(stored_failed[cid]) == failed
        ok = equivalent and matches_truth and matches_stored in (True, None)
        out["ok"] &= ok
        out["candidates"][cid] = {
            "label": CANDIDATE_LABELS[cid], "file": f"eval/candidates/{names[cid]}", "code_sha256": hashlib.sha256(src.encode()).hexdigest().upper(),
            "defects_ground_truth": DEFECTS[cid], "failed_tests": failed, "passed_count": sum(ev_map.values()),
            "total": len(ev_map), "equivalent_to_03_2_suite": equivalent, "failed_matches_defect_ground_truth": matches_truth,
            "failed_matches_stored_03_2_result": matches_stored, "evidence": ev,
        }
        print(f"{cid:<12} {sum(ev_map.values())}/{len(ev_map)} passed | failed={failed}\n"
              f"             equivalent_to_03.2_suite={equivalent} matches_defect_ground_truth={matches_truth} "
              f"matches_stored_03.2_failures={matches_stored}")
    ref = pathlib.Path(os.environ.get("TEMP", "")) / "ref_good.py"
    if ref.exists():
        ev = capture_evidence(ref)
        suite = suite_result(ref)
        same = {t["name"]: t["passed"] for t in ev["tests"]} == suite["tests"]
        n = sum(t["passed"] for t in ev["tests"])
        out["reference_good_sanity"] = {"passed": n, "equivalent": same}
        out["ok"] &= same and n == 14
        print(f"reference (correct) implementation: {n}/14, equivalent={same}")
    after = prior_hashes()
    out["prior_files_unchanged"] = before == after
    out["ok"] &= out["prior_files_unchanged"]
    blob = json.dumps(out, indent=2, ensure_ascii=False)
    if fc.KEY in blob:
        sys.exit("Refusing to write evidence: credential string found in output.")
    EVIDENCE_FILE.write_text(blob, encoding="utf-8")
    print(f"\nprior 03.2 result files unchanged: {out['prior_files_unchanged']}")
    print("prepare:", "OK" if out["ok"] else "FAILED - do not proceed")
    print("wrote", EVIDENCE_FILE)
    if not out["ok"]:
        sys.exit(1)


# --------------------------------------------------------------------------
# run
# --------------------------------------------------------------------------
SCHEMA_TEXT = """{
  "root_cause": "<string: the root cause(s) of the failing tests>",
  "evidence": ["<string: for each failure you explain, quote the test name and the observed vs expected result>"],
  "identified_issues": [
    {
      "description": "<what is wrong, and why the observed output differs from the expected output>",
      "location": "<the exact code line or construct, or 'missing behavior: ...' if the code lacks something>",
      "status": "confirmed" or "possible",
      "failing_tests": ["<names of the failing tests this issue explains; [] if none>"]
    }
  ],
  "suggested_changes": ["<a specific correction, for example the replacement line or code>"],
  "confidence": <number between 0 and 1>,
  "no_issues": <true or false>
}"""


def requirements_text(fc):
    return fc.TASK_SPEC.split("Return the complete code")[0].strip()


def critic_prompt(fc, code, ev_text):
    return (
        f"Requirements the code must satisfy:\n{requirements_text(fc)}\n\n"
        f"Code under review:\n```python\n{code}\n```\n\n"
        "Evaluator output from executing this exact code against a fixed test suite. These are genuine "
        f"execution results; treat them as ground truth:\n{ev_text}\n\n"
        "Your task:\n"
        "1. Identify the root cause of each failure.\n"
        "2. Point to the relevant code location (the exact line or construct, or the missing behavior).\n"
        "3. Explain why the observed output differs from the expected output.\n"
        "4. Propose a specific correction.\n"
        "5. Mark each issue \"confirmed\" if it directly explains one or more failing tests, or \"possible\" if "
        "the evaluator output does not demonstrate it.\n"
        "6. Do not invent defects, and do not claim that a passing test fails. If every test passed and you find "
        "no defect, set no_issues to true and identified_issues to [].\n\n"
        "Respond with ONLY a JSON object (no markdown fences, no prose) with exactly these keys, in this order:\n"
        f"{SCHEMA_TEXT}"
    )


def revise_prompt(fc, code, ev_text, feedback):
    parts = [
        fc.TASK_SPEC, "",
        f"Here is the current implementation:\n```python\n{code}\n```", "",
        "Evaluator output from executing it against the fixed test suite (genuine execution results):\n" + ev_text, "",
    ]
    if feedback is not None:
        parts += ["A reviewer returned the following feedback (verbatim):\n<feedback>\n" + feedback + "\n</feedback>", ""]
    parts.append(
        "Revise the implementation so that every requirement is satisfied and the failing tests pass, without "
        "breaking behavior that already passes."
        + (" Use the reviewer feedback where it is correct; ignore anything that contradicts the evaluator output "
           "or the requirements." if feedback is not None else "")
        + " Return the complete revised code in a single ```python block (including the run_tests function as "
          "specified), then at most 3 sentences describing what you changed.")
    return "\n".join(parts)


def parse_json(text):
    import re
    if text is None:
        return None, False, False
    try:
        return json.loads(text), True, True
    except Exception:  # noqa: BLE001
        stripped = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", text.strip())
        try:
            return json.loads(stripped), False, True
        except Exception:  # noqa: BLE001
            return None, False, False


def validate_critic(obj, failed, passed):
    keys = ["root_cause", "evidence", "identified_issues", "suggested_changes", "confidence", "no_issues"]
    errs = []
    if not isinstance(obj, dict):
        return ["top level is not an object"], {}, []
    if set(keys) - set(obj):
        errs.append(f"missing keys {sorted(set(keys) - set(obj))}")
    if set(obj) - set(keys):
        errs.append(f"extra keys {sorted(set(obj) - set(keys))}")
    if not (isinstance(obj.get("root_cause"), str) and obj.get("root_cause").strip()):
        errs.append("root_cause must be a non-empty string")
    for k in ("evidence", "suggested_changes"):
        v = obj.get(k)
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            errs.append(f"{k} must be a list of strings")
    c = obj.get("confidence")
    if isinstance(c, bool) or not isinstance(c, (int, float)) or not 0 <= c <= 1:
        errs.append("confidence must be a number in [0,1]")
    if not isinstance(obj.get("no_issues"), bool):
        errs.append("no_issues must be a boolean")
    issues = obj.get("identified_issues")
    cited = set()
    if not isinstance(issues, list):
        errs.append("identified_issues must be a list")
        issues = []
    for i, it in enumerate(issues):
        if not isinstance(it, dict):
            errs.append(f"issue {i} is not an object")
            continue
        for k in ("description", "location"):
            if not (isinstance(it.get(k), str) and it[k].strip()):
                errs.append(f"issue {i}: {k} must be a non-empty string")
        if it.get("status") not in ("confirmed", "possible"):
            errs.append(f"issue {i}: status must be confirmed|possible")
        ft = it.get("failing_tests")
        if not isinstance(ft, list) or not all(isinstance(x, str) for x in ft):
            errs.append(f"issue {i}: failing_tests must be a list of strings")
        else:
            cited |= set(ft)
    if obj.get("no_issues") is True and issues:
        errs.append("no_issues=true but identified_issues is not empty")
    if obj.get("no_issues") is False and not issues:
        errs.append("no_issues=false but identified_issues is empty")
    all_names = set(failed) | set(passed)
    aids = {"cited_tests": sorted(cited), "cited_unknown_tests": sorted(cited - all_names),
            "cited_passing_tests": sorted(cited & set(passed)),
            "failing_tests_cited": sorted(cited & set(failed)), "failing_tests_not_cited": sorted(set(failed) - cited)}
    contradictions = []
    if failed and obj.get("no_issues") is True:
        contradictions.append(f"claims no_issues=true although {len(failed)} test(s) failed")
    if aids["cited_passing_tests"]:
        contradictions.append(f"cites passing tests as failing: {aids['cited_passing_tests']}")
    if aids["cited_unknown_tests"]:
        contradictions.append(f"cites test names that do not exist: {aids['cited_unknown_tests']}")
    return errs, aids, contradictions


def cmd_run():
    fc = load_fc()
    if not EVIDENCE_FILE.exists():
        sys.exit("Run `prepare` first.")
    evid = json.loads(EVIDENCE_FILE.read_text(encoding="utf-8"))
    if not evid.get("ok"):
        sys.exit("Evidence reconstruction did not pass. Stopping.")
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    fc.OUT_PATH = RESULTS / f"critic_validation_run_{ts}.json"
    orig_http = fc.http
    fc.http = lambda method, url, body=None, timeout=600: orig_http(method, url, body, timeout)  # allow cold starts

    # ---- model verification (GET only, no inference, no cost) ----
    print("== Model verification ==")
    details = {}
    for m in sorted({CRITIC_A, CRITIC_B, GENERATOR}):
        status, raw, _ = fc.http("GET", f"{fc.BASE}/models/{m}", None, 60)
        j = json.loads(raw) if status == 200 else {}
        d = {"http_status": status, "status": j.get("status"), "available_on_current_plan": j.get("available_on_current_plan"),
             "pricing": j.get("pricing"), "context_length": j.get("context_length"), "max_completion_tokens": j.get("max_completion_tokens"),
             "concurrency_cost": j.get("concurrency_cost"), "is_gated": j.get("is_gated"), "availability": j.get("availability")}
        details[m] = d
        print(f"{m}: HTTP {status} status={d['status']} plan_ok={d['available_on_current_plan']} ctx={d['context_length']} "
              f"price_in={(d['pricing'] or {}).get('prompt')} price_out={(d['pricing'] or {}).get('completion')} "
              f"tier={(d['availability'] or {}).get('tier')} hot_live={(d['availability'] or {}).get('is_hot_live')}")
        if status != 200 or d["status"] != "active" or d["available_on_current_plan"] is not True or not d["pricing"]:
            fc.EVALS["model_details"] = details
            fc.save()
            sys.exit(f"STOP: {m} is not verifiably available on this plan. No inference requests were made.")
    price = {m: (float(details[m]["pricing"]["prompt"]), float(details[m]["pricing"]["completion"])) for m in details}

    # ---- prompts ----
    code = {cid: pathlib.Path(HERE.parent / evid["candidates"][cid]["file"]).read_text(encoding="utf-8") for cid in evid["candidates"]}
    ev_txt = {cid: evidence_text(evid["candidates"][cid]["evidence"]) for cid in evid["candidates"]}
    cprompts = {cid: critic_prompt(fc, code[cid], ev_txt[cid]) for cid in code}
    gen_ids = ["B_gen_7b", "C_gen_coder"]

    # ---- worst-case cost bound ----
    def tok_ub(chars):
        return math.ceil(chars / CHARS_PER_TOKEN_FLOOR) + 50

    bound = []
    for cid in cprompts:
        for m in (CRITIC_A, CRITIC_B):
            pi, po = price[m]
            bound.append((f"critic {cid} {m.split('/')[-1]}", tok_ub(len(cprompts[cid]) + len(fc.SYS_CRITIC)) * pi + MAX_TOKENS_CRITIC * po))
    for cid in gen_ids:
        pi, po = price[GENERATOR]
        base = len(revise_prompt(fc, code[cid], ev_txt[cid], None)) + len(fc.SYS_GEN)
        for variant in ("control", "critic7b", "critic32b"):
            extra = 0 if variant == "control" else math.ceil(MAX_TOKENS_CRITIC * 6)  # chars: pessimistic 6 chars/token response
            bound.append((f"revise {cid} {variant}", tok_ub(base + extra) * pi + MAX_TOKENS_REVISE * po))
    total_ub = sum(c for _, c in bound)
    print(f"\n== Worst-case cost bound: {len(bound)} requests, ${total_ub:.4f} (budget ${BUDGET_USD:.2f}) ==")
    for n, c in bound:
        print(f"  {n:<36} <= ${c:.5f}")
    fc.EVALS["model_details"] = details
    fc.EVALS["cost_bound"] = {"requests": len(bound), "worst_case_usd": total_ub, "budget_usd": BUDGET_USD,
                              "assumptions": f"prompt tokens >= chars/{CHARS_PER_TOKEN_FLOOR} (pessimistic), completion = max_tokens"}
    if total_ub > BUDGET_USD:
        fc.save()
        sys.exit("STOP: worst-case cost exceeds the budget. Approval required.")
    if os.environ.get("CV_DRY") == "1":
        print("Dry run: stopping before any inference request.")
        return

    def spent():
        return sum((r["reported_cost_usd"] or 0.0) for r in fc.REQUESTS)

    def gchat(model, role, label, system, user, max_tokens):
        if spent() > BUDGET_USD:
            fc.save()
            sys.exit("STOP: actual spend exceeded the budget.")
        return fc.chat(model, role, label, system, user, max_tokens)

    exp = {"critics": [], "revisions": []}
    fc.EVALS["experiment"] = exp

    # ---- critic stage ----
    print("\n== Critic stage (same candidate code and same evaluator evidence for both Critics) ==")
    critic_resp = {}
    for cid in cprompts:
        failed = evid["candidates"][cid]["failed_tests"]
        passed = [t["name"] for t in evid["candidates"][cid]["evidence"]["tests"] if t["passed"]]
        for m in (CRITIC_A, CRITIC_B):
            tag = "7b" if m == CRITIC_A else "32b"
            rec = gchat(m, "critic", f"critic_{cid[0]}_{tag}", fc.SYS_CRITIC, cprompts[cid], MAX_TOKENS_CRITIC)
            obj, strict, lenient = parse_json(rec["content"])
            errs, aids, contra = validate_critic(obj, failed, passed) if lenient else (["unparseable JSON"], {}, [])
            critic_resp[(cid, tag)] = rec
            exp["critics"].append({"candidate": cid, "critic": m, "tag": tag, "http_status": rec["http_status"],
                                   "finish_reason": rec["finish_reason"], "strict_json": strict, "lenient_json": lenient,
                                   "schema_errors": errs, "evidence_aids": aids, "contradictions": contra,
                                   "confidence": (obj or {}).get("confidence") if isinstance(obj, dict) else None,
                                   "no_issues": (obj or {}).get("no_issues") if isinstance(obj, dict) else None})
            fc.save()
    print(f"spent so far: ${spent():.6f}")

    # ---- revision stage (Generator fixed = Qwen2.5-7B-Instruct) ----
    print("\n== Revision stage (Generator fixed; Critic is the controlled variable; control gets no Critic feedback) ==")
    for cid in gen_ids:
        before_failed = evid["candidates"][cid]["failed_tests"]
        variants = [("control", None)]
        for tag in ("7b", "32b"):
            r = critic_resp[(cid, tag)]
            variants.append((f"critic_{tag}", r["content"] if r["http_status"] == 200 and r["content"] else None))
        for name, feedback in variants:
            if name != "control" and feedback is None:
                exp["revisions"].append({"candidate": cid, "variant": name, "skipped": "critic call failed"})
                continue
            prompt = revise_prompt(fc, code[cid], ev_txt[cid], feedback)
            rec = gchat(GENERATOR, "generator", f"revise_{cid[0]}_{name}", fc.SYS_GEN, prompt, MAX_TOKENS_REVISE)
            new_code = fc.extract_code(rec["content"]) if rec["content"] else None
            after = fc.evaluate_solution(rec["content"]) if rec["content"] else {"error": rec["error"]}
            diff = "\n".join(difflib.unified_diff(code[cid].splitlines(), (new_code or "").splitlines(), "original", "revised", lineterm="", n=1)) if new_code else None
            fixed = sorted(set(before_failed) - set(after.get("failed_tests") or []))
            regressed = sorted(set(after.get("failed_tests") or []) - set(before_failed)) if new_code else None
            exp["revisions"].append({"candidate": cid, "variant": name, "http_status": rec["http_status"],
                                     "before_passed": 14 - len(before_failed), "before_failed": before_failed,
                                     "after_passed": after.get("hidden_passed"), "after_failed": after.get("failed_tests"),
                                     "fixed_tests": fixed, "regressed_tests": regressed,
                                     "code_identical_to_original": (new_code or "").strip() == code[cid].strip() if new_code else None,
                                     "own_tests_exit": after.get("own_tests_exit"), "diff": diff, "after_eval": after})
            fc.save()
    after_hashes = prior_hashes()
    exp["prior_files_unchanged"] = after_hashes == evid["prior_file_sha256"]
    exp["total_reported_cost_usd"] = spent()
    exp["request_count"] = len(fc.REQUESTS)
    fc.save()

    print("\n== Run summary ==")
    for c in exp["critics"]:
        print(f"critic {c['candidate']:<12} {c['tag']:<4} strict_json={c['strict_json']} schema_errors={len(c['schema_errors'])} "
              f"no_issues={c['no_issues']} conf={c['confidence']} contradictions={len(c['contradictions'])}")
    for r in exp["revisions"]:
        if "skipped" in r:
            print(f"revise {r['candidate']:<12} {r['variant']:<10} SKIPPED ({r['skipped']})")
        else:
            print(f"revise {r['candidate']:<12} {r['variant']:<10} {r['before_passed']}/14 -> {r['after_passed']}/14 "
                  f"fixed={r['fixed_tests']} regressed={r['regressed_tests']} identical={r['code_identical_to_original']}")
    print(f"requests={exp['request_count']} total reported cost=${exp['total_reported_cost_usd']:.6f} prior_files_unchanged={exp['prior_files_unchanged']}")
    print("results:", fc.OUT_PATH)


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "prepare":
        cmd_prepare()
    elif len(sys.argv) == 2 and sys.argv[1] == "run":
        cmd_run()
    else:
        sys.exit("usage: critic_validation.py prepare | run")
