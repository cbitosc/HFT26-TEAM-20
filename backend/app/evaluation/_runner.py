"""Child process that executes candidate code. Standard library only; copied into a temporary
working directory and run by `execution.py`.

THIS IS NOT A SECURITY SANDBOX. It bounds time (the parent kills it), closes stdin, discards the
candidate's stdout/stderr, runs in a throwaway directory with a minimal environment, and compares
results type-strictly. Hostile code can still read files, use the network, spawn processes or
tamper with this process. Never evaluate untrusted code on a machine that matters.

Protocol: JSON lines appended to the result file named in suite.json:
  {"t":"start","id":ID}                       about to run ID
  {"t":"import", ...}                         result of importing the module and inspecting the entry point
  {"t":"result","id":ID,"passed":bool,...}    outcome of ID
  {"t":"done"}                                every requested item was run
"""
import ast
import builtins
import copy
import inspect
import json
import linecache
import sys
import traceback

CLIP = 300
TRACE_FRAMES = 3
FILENAME = "candidate.py"

_type = type
_isinstance = isinstance
_len = len
_repr = repr


def clip(value, limit=CLIP):
    try:
        text = value if _isinstance(value, str) else _repr(value)
    except BaseException:  # a hostile __repr__ must not break the evaluator
        text = "<unrepresentable object>"
    return text if _len(text) <= limit else text[:limit] + "...[truncated]"


class Discard:
    """Replaces sys.stdout/sys.stderr while candidate code runs; keeps nothing."""

    def write(self, text):
        return _len(text)

    def flush(self):
        pass

    def isatty(self):
        return False


def strict_equal(actual, expected):
    """Equality that cannot be faked by a custom __eq__: types must be identical all the way down."""
    if _type(actual) is not _type(expected):
        return False
    if _type(expected) in (list, tuple):
        return _len(actual) == _len(expected) and all(strict_equal(a, e) for a, e in zip(actual, expected))
    if _type(expected) is dict:
        return actual.keys() == expected.keys() and all(strict_equal(actual[k], expected[k]) for k in expected)
    if _type(expected) in (int, float, str, bool, bytes, set, frozenset, _type(None)):
        return actual == expected
    return False


def main():
    spec = json.load(open("suite.json", encoding="utf-8"))
    source = open(FILENAME, encoding="utf-8").read()
    out = open(spec["result_file"], "a", encoding="utf-8", buffering=1)

    def emit(record):
        out.write(json.dumps(record) + "\n")
        out.flush()

    linecache.cache[FILENAME] = (_len(source), None, source.splitlines(True), FILENAME)
    entry_name = spec["entrypoint"]

    def frames(exc):
        found = [fr for fr in traceback.extract_tb(exc.__traceback__) if fr.filename == FILENAME]
        return [clip(f"line {fr.lineno}, in {fr.name}: {(fr.line or '').strip()}", 200) for fr in found[-TRACE_FRAMES:]]

    def describe(exc):
        return clip(f"{_type(exc).__name__}: {exc}")

    def fresh_namespace():
        namespace = {"__name__": "candidate", "__builtins__": builtins}
        exec(compile(source, FILENAME, "exec"), namespace)
        return namespace

    sys.stdout, sys.stderr = Discard(), Discard()

    emit({"t": "start", "id": "__import__"})
    info = {"t": "import", "imports_cleanly": False, "entrypoint_defined": False, "arity_ok": False,
            "error": None, "trace": []}
    entry = None
    try:
        namespace = fresh_namespace()
        info["imports_cleanly"] = True
        entry = namespace.get(entry_name)
    except BaseException as exc:
        info["error"] = describe(exc)
        info["trace"] = frames(exc)
    if callable(entry):
        info["entrypoint_defined"] = True
        try:
            inspect.signature(entry).bind(*([object()] * spec["arity"]))
            info["arity_ok"] = True
        except (TypeError, ValueError):
            pass
    emit(info)
    if not (info["imports_cleanly"] and info["entrypoint_defined"]):
        emit({"t": "done"})
        return

    def call(func, args):
        try:
            return True, func(*args), None
        except BaseException as exc:
            return False, None, exc

    def run_check(func, check):
        args = ast.literal_eval(check["args"])
        kind = check["kind"]
        before = copy.deepcopy(args)
        ok, result, exc = call(func, args)
        callstr = clip(f"{entry_name}({', '.join(clip(a, 80) for a in args)})")
        base = {"call": callstr}
        if kind == "raises":
            expected_exc = getattr(builtins, check["expected"])
            expected = f"raises {check['expected']}"
            if ok:
                return {**base, "passed": False, "expected": expected, "actual": clip(f"returned {clip(result)} without raising")}
            passed = _isinstance(exc, expected_exc)
            return {**base, "passed": passed, "expected": expected, "actual": clip(f"raised {describe(exc)}"),
                    "exception": None if passed else describe(exc), "trace": [] if passed else frames(exc)}
        if not ok:
            return {**base, "passed": False, "expected": clip(check.get("label", kind)), "actual": clip(f"raised {describe(exc)}"),
                    "exception": describe(exc), "trace": frames(exc)}
        if kind == "returns":
            expected_value = ast.literal_eval(check["expected"])
            return {**base, "passed": strict_equal(result, expected_value), "expected": clip(f"returns {check['expected']}"),
                    "actual": clip(f"returned {clip(result)}")}
        if kind == "unchanged_input":
            unchanged = strict_equal(list(args), list(before))
            fresh = not (args and result is args[0])
            actual = ("input modified: " + clip(args)) if not unchanged else "returned the same object as the input" if not fresh else "ok"
            return {**base, "passed": unchanged and fresh, "expected": clip(f"input unchanged: {clip(before)}; result is a new object"),
                    "actual": clip(actual)}
        if kind == "returns_type":  # internal: used by the contract smoke call
            wanted = getattr(builtins, check["expected"])
            return {**base, "passed": _type(result) is wanted, "expected": f"a result of exactly type {check['expected']}",
                    "actual": clip(f"returned {_type(result).__name__}: {clip(result, 100)}")}
        if kind == "all_items_of_type":
            wanted = getattr(builtins, check["expected"])
            good = _type(result) is list and all(_type(item) is wanted for item in result)
            return {**base, "passed": good, "expected": f"a list whose items are all exactly {check['expected']}",
                    "actual": clip(f"returned {clip(result)}")}
        return {**base, "passed": False, "expected": "known check", "actual": f"unknown check kind {kind}"}

    for item in spec["items"]:
        emit({"t": "start", "id": item["id"]})
        record = {"t": "result", "id": item["id"], "passed": True, "expected": None, "actual": None,
                  "exception": None, "trace": []}
        try:
            func = fresh_namespace()[entry_name]  # fresh module state for every item
            for check in item["checks"]:
                outcome = run_check(func, check)
                if not outcome["passed"]:
                    record.update(passed=False, expected=outcome["expected"], actual=outcome["actual"],
                                  exception=outcome.get("exception"), trace=outcome.get("trace", []))
                    break
        except BaseException as exc:
            record.update(passed=False, expected="the item to run", actual=clip(f"raised {describe(exc)}"),
                          exception=describe(exc), trace=frames(exc))
        emit(record)
    emit({"t": "done"})


main()
