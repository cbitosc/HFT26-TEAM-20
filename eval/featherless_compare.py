"""Featherless model comparison harness (evaluation tooling, not application code).

Compares two models for Generator / Critic roles with real API calls.
- Key is read from FEATHERLESS_API_KEY and is never printed or written.
- Latency uses time.perf_counter(). Tokens and cost are copied from the
  provider's `usage` object; if a field is absent it is recorded as null.
- Candidate code is executed in a subprocess with a timeout (stdin closed).

Usage:  python eval/featherless_compare.py
"""
import ast
import datetime
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

# --------------------------------------------------------------------------
# Hidden-test mode (runs inside a subprocess; no network, no key needed)
# --------------------------------------------------------------------------
HIDDEN_TEST_NAMES = []


def hidden_test_mode(path):
    code = pathlib.Path(path).read_text(encoding="utf-8")
    ns = {"__name__": "candidate"}  # keeps `if __name__ == "__main__"` blocks from running
    out = {"load_error": None, "tests": {}}
    try:
        exec(compile(code, "candidate", "exec"), ns)
        f = ns["merge_intervals"]
    except BaseException as e:  # noqa: BLE001
        out["load_error"] = f"{type(e).__name__}: {e}"[:200]
        print("\n@@RESULT@@" + json.dumps(out))
        return

    def raises(exc, *args):
        try:
            f(*args)
        except exc:
            return True
        except BaseException:  # noqa: BLE001
            return False
        return False

    def not_mutated():
        inp = [(5, 6), (1, 2), (2, 3)]
        snap = list(inp)
        res = f(inp)
        return inp == snap and res is not inp

    tests = {
        "overlap": lambda: f([(1, 3), (2, 6), (8, 10)]) == [(1, 6), (8, 10)],
        "touching": lambda: f([(1, 3), (3, 5)]) == [(1, 5)],
        "contained": lambda: f([(1, 10), (2, 3)]) == [(1, 10)],
        "unsorted_input": lambda: f([(8, 10), (1, 3), (2, 6)]) == [(1, 6), (8, 10)],
        "chain": lambda: f([(1, 4), (4, 5), (5, 9), (10, 11)]) == [(1, 9), (10, 11)],
        "empty": lambda: f([]) == [],
        "single_point": lambda: f([(4, 4)]) == [(4, 4)],
        "input_not_mutated": not_mutated,
        "returns_tuples": lambda: all(type(x) is tuple for x in f([(1, 2), (2, 3), (7, 8)])),
        "typeerror_not_list": lambda: raises(TypeError, None) and raises(TypeError, ((1, 2),)),
        "typeerror_bad_element": lambda: (
            raises(TypeError, [(1, 2), (3,)])
            and raises(TypeError, [(1, "a")])
            and raises(TypeError, [(1, 2), [3, 4]])
        ),
        "valueerror_start_gt_end": lambda: raises(ValueError, [(5, 1)]),
        "validation_applies_to_all": lambda: raises(ValueError, [(1, 2), (9, 3)]),
        # Added after run 1: a candidate without an explicit int check passed
        # `[(1, "a")]` only because `1 > "a"` raises TypeError. These two cases
        # compare without error, so only a real type check rejects them.
        "typeerror_non_int_values": lambda: raises(TypeError, [(1.5, 2.5)]) and raises(TypeError, [("a", "b")]),
    }
    for name, fn in tests.items():
        try:
            out["tests"][name] = bool(fn())
        except BaseException:  # noqa: BLE001
            out["tests"][name] = False
    print("\n@@RESULT@@" + json.dumps(out))


if len(sys.argv) == 3 and sys.argv[1] == "--hidden-tests":
    hidden_test_mode(sys.argv[2])
    sys.exit(0)

# --------------------------------------------------------------------------
# Harness
# --------------------------------------------------------------------------
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

BASE = "https://api.featherless.ai/v1"
MODELS = ["Qwen/Qwen2.5-7B-Instruct", "Qwen/Qwen2.5-Coder-7B-Instruct"]
KEY = os.environ.get("FEATHERLESS_API_KEY", "").strip()
if not KEY:
    sys.exit("FEATHERLESS_API_KEY is not set. Stopping.")

HEADERS = {
    "Authorization": f"Bearer {KEY}",
    "Content-Type": "application/json",
    "User-Agent": "autoevolve-eval/0.1",
    "X-Title": "AutoEvolve model evaluation",
}

REQUESTS = []
EVALS = {}
OUT_PATH = None

SYS_GEN = "You are an expert Python engineer. Follow the requirements exactly."
SYS_CRITIC = ("You are a strict, accurate code reviewer. Report only real defects that "
              "violate the stated requirements. Do not invent problems.")

TASK_SPEC = """Implement a Python function `merge_intervals(intervals)`.

Requirements:
- `intervals` is a list of (start, end) tuples of integers.
- Return a NEW list of (start, end) tuples, sorted by start, in which all intervals that overlap or touch are merged. Two intervals touch when next.start == current.end (for example (1, 3) and (3, 5) merge to (1, 5)).
- An interval fully contained in another must not shrink the merged interval (for example (1, 10) and (2, 3) merge to (1, 10)).
- An empty list returns an empty list.
- The input list must not be modified.
- Raise TypeError if `intervals` is not a list, or if any element is not a tuple of exactly two integers.
- Raise ValueError if any interval has start > end.
- Use type hints and a docstring.
- Include a small set of tests: plain `assert` statements inside a `def run_tests():` function, called under `if __name__ == "__main__":`.
Return the complete code in a single ```python block, followed by an explanation of at most 3 sentences."""

FLAWED_CODE = '''def merge_intervals(intervals):
    intervals.sort()
    merged = [intervals[0]]
    for start, end in intervals[1:]:
        last_start, last_end = merged[-1]
        if start < last_end:
            merged[-1] = (last_start, end)
        else:
            merged.append((start, end))
    return merged
'''
# Seeded defects (ground truth known to the harness author):
SEEDED = {
    "D1_mutates_input": r"mutat|modif\w* (the )?(input|original|argument|list)|in-?place|side[- ]effect|sorts? (the )?(input|original|list)|copy",
    "D2_empty_crashes": r"empty|index ?error|intervals\[0\]|no (elements|intervals)",
    "D3_touching_not_merged": r"touch|adjacent|<=|equal|start == |start==",
    "D4_contained_shrinks": r"contain|max\(|shrink|nested|encompass|fully|overwrit|smaller end|larger end",
    "D5_no_validation": r"valid|type ?error|value ?error|isinstance|start > end|not a list|tuple",
}

JSON_INSTRUCTIONS = """Respond with ONLY a JSON object (no markdown fences, no prose) with exactly these keys:
{"status": "issues_found" or "no_issues",
 "identified_issues": [list of strings, each "<defect> - <why it violates the requirements>"],
 "suggested_changes": [list of strings, each a concrete fix],
 "confidence": number between 0 and 1}"""

SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["issues_found", "no_issues"]},
        "identified_issues": {"type": "array", "items": {"type": "string"}},
        "suggested_changes": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["status", "identified_issues", "suggested_changes", "confidence"],
    "additionalProperties": False,
}


def save():
    blob = json.dumps({"requests": REQUESTS, "evaluations": EVALS}, indent=2, ensure_ascii=False)
    if KEY in blob:
        sys.exit("Refusing to write results: credential string found in output.")
    OUT_PATH.write_text(blob, encoding="utf-8")


def http(method, url, body=None, timeout=180):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=HEADERS, method=method)
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status, raw = r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        status, raw = None, f"{type(e).__name__}: {e}"
    return status, raw, time.perf_counter() - t0


def chat(model, role, label, system, user, max_tokens, response_format=None):
    body = {"model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0, "max_tokens": max_tokens}
    if response_format is not None:
        body["response_format"] = response_format
    status, raw, latency = http("POST", f"{BASE}/chat/completions", body)
    rec = {"model": model, "role": role, "label": label, "http_status": status,
           "latency_s": round(latency, 3), "request_body": body,
           "content": None, "finish_reason": None, "prompt_tokens": None,
           "completion_tokens": None, "total_tokens": None, "reported_cost_usd": None,
           "error": None}
    try:
        j = json.loads(raw)
    except Exception:  # noqa: BLE001
        j = None
    if status == 200 and isinstance(j, dict) and j.get("choices"):
        ch = j["choices"][0]
        rec["content"] = (ch.get("message") or {}).get("content")
        rec["finish_reason"] = ch.get("finish_reason")
        u = j.get("usage") or {}
        rec["prompt_tokens"] = u.get("prompt_tokens")
        rec["completion_tokens"] = u.get("completion_tokens")
        rec["total_tokens"] = u.get("total_tokens")
        rec["reported_cost_usd"] = u.get("cost")
    else:
        rec["error"] = raw[:1500]
    REQUESTS.append(rec)
    save()
    print(f"[{label:<28}] {model.split('/')[-1]:<24} HTTP {status} {latency:6.1f}s "
          f"p={rec['prompt_tokens']} c={rec['completion_tokens']} fin={rec['finish_reason']}")
    return rec


def extract_code(text):
    for m in re.finditer(r"```[a-zA-Z]*[ \t]*\r?\n(.*?)```", text or "", re.S):
        if "def merge_intervals" in m.group(1):
            return m.group(1)
    return None


def evaluate_solution(text):
    code = extract_code(text)
    res = {"code_extracted": code is not None, "hidden_passed": 0, "hidden_total": 14,
           "failed_tests": [], "syntax_ok": None, "has_docstring": None, "has_type_hints": None,
           "own_tests_in_block": None, "own_tests_exit": None, "own_tests_stderr_tail": None,
           "load_error": None}
    if code is None:
        res["failed_tests"] = ["no code block containing merge_intervals"]
        return res
    try:
        tree = ast.parse(code)
        res["syntax_ok"] = True
        fn = next((n for n in ast.walk(tree)
                   if isinstance(n, ast.FunctionDef) and n.name == "merge_intervals"), None)
        res["has_docstring"] = bool(fn and ast.get_docstring(fn))
        res["has_type_hints"] = bool(fn and fn.returns is not None
                                     and all(a.annotation is not None for a in fn.args.args))
    except SyntaxError as e:
        res["syntax_ok"] = False
        res["load_error"] = f"SyntaxError: {e}"
        return res
    res["own_tests_in_block"] = bool(re.search(r"\bassert\b|unittest|def test_", code))
    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d) / "candidate.py"
        p.write_text(code, encoding="utf-8")
        try:
            r = subprocess.run([sys.executable, os.path.abspath(__file__), "--hidden-tests", str(p)],
                               capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL, cwd=d)
            marker = r.stdout.rfind("@@RESULT@@")
            parsed = json.loads(r.stdout[marker + len("@@RESULT@@"):]) if marker >= 0 else None
        except subprocess.TimeoutExpired:
            parsed = {"load_error": "TIMEOUT (30s)", "tests": {}}
        if parsed is None:
            parsed = {"load_error": "runner produced no result", "tests": {}}
        res["load_error"] = parsed["load_error"]
        tests = parsed["tests"]
        res["hidden_passed"] = sum(1 for v in tests.values() if v)
        res["failed_tests"] = [k for k, v in tests.items() if not v]
        if parsed["load_error"]:
            res["failed_tests"] = ["(load error) " + parsed["load_error"]]
        if res["own_tests_in_block"]:
            try:
                r = subprocess.run([sys.executable, str(p)], capture_output=True, text=True,
                                   timeout=30, stdin=subprocess.DEVNULL, cwd=d)
                res["own_tests_exit"] = r.returncode
                res["own_tests_stderr_tail"] = (r.stderr.strip().splitlines() or [""])[-1][:160]
            except subprocess.TimeoutExpired:
                res["own_tests_exit"] = "TIMEOUT"
    return res


def validate_review(obj):
    if not isinstance(obj, dict):
        return ["top level is not an object"]
    errs = []
    expected = {"status", "identified_issues", "suggested_changes", "confidence"}
    if expected - set(obj):
        errs.append(f"missing keys {sorted(expected - set(obj))}")
    if set(obj) - expected:
        errs.append(f"extra keys {sorted(set(obj) - expected)}")
    if obj.get("status") not in ("issues_found", "no_issues"):
        errs.append("status not in enum")
    for k in ("identified_issues", "suggested_changes"):
        v = obj.get(k)
        if not isinstance(v, list) or not all(isinstance(x, str) and x.strip() for x in v):
            errs.append(f"{k} must be a list of non-empty strings")
    c = obj.get("confidence")
    if isinstance(c, bool) or not isinstance(c, (int, float)) or not 0 <= c <= 1:
        errs.append("confidence must be a number in [0,1]")
    if obj.get("status") == "issues_found" and not obj.get("identified_issues"):
        errs.append("status=issues_found but identified_issues empty")
    return errs


def parse_review(text):
    out = {"strict_json": False, "lenient_json": False, "schema_errors": None, "parsed": None}
    if text is None:
        return out
    try:
        obj = json.loads(text)
        out["strict_json"] = out["lenient_json"] = True
    except Exception:  # noqa: BLE001
        stripped = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", text.strip())
        try:
            obj = json.loads(stripped)
            out["lenient_json"] = True
        except Exception:  # noqa: BLE001
            return out
    out["schema_errors"] = validate_review(obj)
    out["parsed"] = obj
    return out


def seeded_hints(parsed):
    if not isinstance(parsed, dict):
        return {k: None for k in SEEDED}
    blob = " ".join(str(x) for x in (parsed.get("identified_issues") or [])).lower()
    return {k: bool(re.search(rx, blob)) for k, rx in SEEDED.items()}


def critic_prompt(code, json_mode=True):
    base = f"Requirements the code must satisfy:\n{TASK_SPEC.split('Return the complete code')[0]}\n\nCode under review:\n```python\n{code}```\n\n"
    if json_mode:
        return base + "Identify genuine defects with respect to the requirements, explain why each is a defect, and suggest concrete fixes.\n\n" + JSON_INSTRUCTIONS
    return base + "Review this code against the requirements. List the genuine defects, why each is a defect, and concrete fixes."


def revise_prompt(code, feedback):
    return (f"{TASK_SPEC}\n\nHere is your previous solution:\n```python\n{code}```\n\n"
            f"A reviewer returned the following feedback (verbatim):\n<feedback>\n{feedback}\n</feedback>\n\n"
            "Revise the solution. Fix every genuine defect the feedback identifies, ignore anything in the "
            "feedback that is incorrect, and keep all requirements above satisfied. Return the complete revised "
            "code in a single ```python block (including tests as specified), then at most 3 sentences "
            "describing what you changed.")


def short(m):
    return m.split("/")[-1]


def main():
    global OUT_PATH
    out_dir = pathlib.Path(__file__).resolve().parent / "results"
    out_dir.mkdir(exist_ok=True)
    OUT_PATH = out_dir / f"featherless_compare_{datetime.datetime.now():%Y%m%d_%H%M%S}.json"

    # ---- 0. availability ----
    print("== Model availability ==")
    for m in MODELS:
        status, raw, lat = http("GET", f"{BASE}/models/{m}", timeout=30)
        j = json.loads(raw) if status == 200 else {}
        info = {"http_status": status, "status": j.get("status"), "available_on_current_plan": j.get("available_on_current_plan"),
                "pricing": j.get("pricing"), "availability": j.get("availability"), "context_length": j.get("context_length")}
        EVALS.setdefault("model_detail", {})[m] = info
        print(f"{m}: HTTP {status} status={info['status']} plan_ok={info['available_on_current_plan']} "
              f"tier={(info['availability'] or {}).get('tier')} hot_live={(info['availability'] or {}).get('is_hot_live')}")
        if status != 200 or info["status"] != "active" or info["available_on_current_plan"] is not True:
            save()
            sys.exit(f"{m} is not available on this plan. Stopping without substitution.")

    # ---- warm-up (reported separately) ----
    print("\n== Warm-up ==")
    for m in MODELS:
        chat(m, "warmup", "warmup", "Reply briefly.", "Reply with the single word OK.", 8)

    # ---- 1. Generator test ----
    print("\n== Generator test (same prompt, both models) ==")
    gens = {}
    for m in MODELS:
        rec = chat(m, "generator", "gen_initial", SYS_GEN, TASK_SPEC, 1500)
        gens[m] = rec
        EVALS.setdefault("generator_initial", {})[m] = evaluate_solution(rec["content"]) if rec["content"] else {"error": rec["error"]}
        save()

    # ---- 2. Critic test on the same flawed code ----
    print("\n== Critic test (same flawed code, prompt-requested JSON) ==")
    for m in MODELS:
        rec = chat(m, "critic", "critic_flawed_prompt_json", SYS_CRITIC, critic_prompt(FLAWED_CODE), 1200)
        pr = parse_review(rec["content"])
        EVALS.setdefault("critic_flawed", {})[m] = {**{k: v for k, v in pr.items() if k != "parsed"},
                                                    "seeded_keyword_hints": seeded_hints(pr["parsed"])}
        save()

    # ---- 3. Genuine Critic -> Generator revision pipelines ----
    print("\n== Revision pipelines (exact solution -> exact critic reply -> exact revise prompt) ==")
    EVALS["pipelines"] = []
    for g in MODELS:
        init_text = gens[g]["content"]
        code = extract_code(init_text)
        if code is None:
            print(f"skip pipelines for generator {g}: no code extracted")
            continue
        before = EVALS["generator_initial"][g]
        for c in MODELS:
            crit = chat(c, "critic", f"critic_on_{short(g)[:12]}", SYS_CRITIC, critic_prompt(code), 1200)
            if crit["content"] is None:
                EVALS["pipelines"].append({"generator": g, "critic": c, "error": "critic call failed"})
                continue
            pr = parse_review(crit["content"])
            rev = chat(g, "generator", f"revise_G{short(g)[:6]}_C{short(c)[:6]}", SYS_GEN,
                       revise_prompt(code, crit["content"]), 1800)
            after = evaluate_solution(rev["content"]) if rev["content"] else {"error": rev["error"]}
            EVALS["pipelines"].append({
                "generator": g, "critic": c,
                "before_hidden_passed": before.get("hidden_passed"), "before_failed": before.get("failed_tests"),
                "after_hidden_passed": after.get("hidden_passed"), "after_failed": after.get("failed_tests"),
                "critic_strict_json": pr["strict_json"], "critic_schema_errors": pr["schema_errors"],
                "critic_status": (pr["parsed"] or {}).get("status") if pr["parsed"] else None,
                "after_eval": after,
            })
            save()

    # ---- 4. Provider-enforced structured output ----
    print("\n== Structured output: is JSON provider-enforced or prompt-induced? ==")
    EVALS["structured"] = []
    modes = {
        "prose_prompt+json_object": {"type": "json_object"},
        "prose_prompt+json_schema": {"type": "json_schema",
                                     "json_schema": {"name": "code_review", "strict": True, "schema": SCHEMA}},
    }
    for m in MODELS:
        for name, rf in modes.items():
            rec = chat(m, "critic", f"struct_{name[-11:]}", SYS_CRITIC, critic_prompt(FLAWED_CODE, json_mode=False), 1200, rf)
            pr = parse_review(rec["content"])
            EVALS["structured"].append({"model": m, "mode": name, "http_status": rec["http_status"],
                                        "error": rec["error"], **{k: v for k, v in pr.items() if k != "parsed"}})
            save()

    # ---- summary ----
    print("\n== SUMMARY ==")
    for m in MODELS:
        ev = EVALS["generator_initial"].get(m, {})
        print(f"gen {short(m)}: hidden {ev.get('hidden_passed')}/{ev.get('hidden_total')} failed={ev.get('failed_tests')} "
              f"docstring={ev.get('has_docstring')} hints={ev.get('has_type_hints')} own_tests_exit={ev.get('own_tests_exit')}")
    for p in EVALS["pipelines"]:
        print(f"pipeline G={short(p['generator'])} C={short(p['critic'])}: "
              f"{p.get('before_hidden_passed')} -> {p.get('after_hidden_passed')} after_failed={p.get('after_failed')}")
    for m in MODELS:
        recs = [r for r in REQUESTS if r["model"] == m and r["role"] != "warmup"]
        costs = [r["reported_cost_usd"] for r in recs]
        tot = sum(c for c in costs if c is not None)
        print(f"{short(m)}: {len(recs)} requests, reported cost sum=${tot:.6f} "
              f"(missing cost on {sum(c is None for c in costs)})")
    print(f"\nResults written to {OUT_PATH}")


def followup(src):
    """Supplementary run: (1) re-score stored outputs with the stricter hidden tests (no API calls);
    (2) free-text Critic (no JSON constraint) on the same stored initial solutions, then revise
    with that Critic's exact reply."""
    global OUT_PATH
    reqs = json.loads(pathlib.Path(src).read_text(encoding="utf-8"))["requests"]
    out_dir = pathlib.Path(__file__).resolve().parent / "results"
    OUT_PATH = out_dir / f"featherless_followup_{datetime.datetime.now():%Y%m%d_%H%M%S}.json"
    EVALS["source_run"] = pathlib.Path(src).name

    inits = {r["model"]: r for r in reqs if r["label"] == "gen_initial"}
    init_eval = {m: evaluate_solution(inits[m]["content"]) for m in MODELS}
    EVALS["rescored_initial"] = init_eval
    pairs = [(g, c) for g in MODELS for c in MODELS]
    revises = [r for r in reqs if r["label"].startswith("revise_")]
    EVALS["rescored_json_critic_revisions"] = []
    print("== Re-score of stored outputs with 14 hidden tests (no API calls) ==")
    for m in MODELS:
        e = init_eval[m]
        print(f"initial  {short(m):<24} {e['hidden_passed']}/{e['hidden_total']} failed={e['failed_tests']}")
    for (g, c), r in zip(pairs, revises):
        e = evaluate_solution(r["content"])
        same = extract_code(r["content"]) == extract_code(inits[g]["content"])
        EVALS["rescored_json_critic_revisions"].append({"generator": g, "critic": c, "eval": e, "code_identical_to_initial": same})
        print(f"revised  G={short(g):<22} C={short(c):<22} {e['hidden_passed']}/{e['hidden_total']} failed={e['failed_tests']} identical_to_initial={same}")
    save()

    print("\n== Free-text Critic -> exact reply -> Generator revision (8 requests) ==")
    EVALS["freetext_pipelines"] = []
    for g in MODELS:
        code = extract_code(inits[g]["content"])
        for c in MODELS:
            crit = chat(c, "critic", f"ft_critic_{short(c)[7:12]}_on_{short(g)[7:12]}", SYS_CRITIC,
                        critic_prompt(code, json_mode=False), 1200)
            if crit["content"] is None:
                EVALS["freetext_pipelines"].append({"generator": g, "critic": c, "error": crit["error"]})
                continue
            rev = chat(g, "generator", f"ft_revise_G{short(g)[7:12]}_C{short(c)[7:12]}", SYS_GEN,
                       revise_prompt(code, crit["content"]), 1800)
            after = evaluate_solution(rev["content"]) if rev["content"] else {"error": rev["error"]}
            EVALS["freetext_pipelines"].append({
                "generator": g, "critic": c,
                "before_hidden_passed": init_eval[g]["hidden_passed"], "before_failed": init_eval[g]["failed_tests"],
                "after_hidden_passed": after.get("hidden_passed"), "after_failed": after.get("failed_tests"),
                "code_identical_to_initial": extract_code(rev["content"]) == extract_code(inits[g]["content"]) if rev["content"] else None,
                "critic_finish_reason": crit["finish_reason"], "after_eval": after})
            save()
    print("\n== Free-text pipeline summary ==")
    for p in EVALS["freetext_pipelines"]:
        print(f"G={short(p['generator'])} C={short(p['critic'])}: {p.get('before_hidden_passed')} -> {p.get('after_hidden_passed')} "
              f"after_failed={p.get('after_failed')} identical={p.get('code_identical_to_initial')}")
    print(f"\nResults written to {OUT_PATH}")


def control():
    """Control for the structured-output test: the SAME prose prompt, no response_format."""
    global OUT_PATH
    out_dir = pathlib.Path(__file__).resolve().parent / "results"
    OUT_PATH = out_dir / f"featherless_control_{datetime.datetime.now():%Y%m%d_%H%M%S}.json"
    EVALS["control_no_response_format"] = []
    print("== Control: prose prompt, no response_format ==")
    for m in MODELS:
        rec = chat(m, "critic", "ctrl_no_response_format", SYS_CRITIC, critic_prompt(FLAWED_CODE, json_mode=False), 1200)
        pr = parse_review(rec["content"])
        EVALS["control_no_response_format"].append({
            "model": m, "http_status": rec["http_status"], "finish_reason": rec["finish_reason"],
            "strict_json": pr["strict_json"], "lenient_json": pr["lenient_json"],
            "starts_with": (rec["content"] or "")[:80]})
        save()
    print(f"Results written to {OUT_PATH}")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--followup":
        followup(sys.argv[2])
    elif len(sys.argv) == 2 and sys.argv[1] == "--control":
        control()
    else:
        main()
