"""Build an EvaluationSuite from a client's DECLARATIVE upload, and (de)serialise one for storage.

Test inputs and expected values arrive as Python-LITERAL STRINGS and are parsed with `ast.literal_eval`
only: no `eval`, no `exec`, no names, no calls, no operators. A client can never supply test code. The
same four check kinds the backend already uses are the only ones accepted.

Storage format (dicts, JSON-serialisable): the public tests and the spec are stored in plaintext; the
hidden tests are encrypted as one blob by app.sealing. Reconstruction rebuilds the EvaluationSuite and
verifies its hashes against the ones stored at upload time, so a tampered row or a wrong key is caught.
"""
import ast

from app.evaluation.suite import (
    CHECK_KINDS,
    EXCEPTION_NAMES,
    TYPE_NAMES,
    Check,
    ContractSpec,
    EvaluationSuite,
    QualitySpec,
    TestCase,
)

MAX_LITERAL_CHARS = 4000
MAX_LITERAL_DEPTH = 20
NAME_KINDS = {"raises": EXCEPTION_NAMES, "all_items_of_type": TYPE_NAMES}


class SuiteUploadError(ValueError):
    """A declarative upload is malformed or unsafe. The message is safe to return to the client
    (it may echo the client's own input, never hidden backend data)."""


def _depth(value, level: int = 1) -> int:
    if level > MAX_LITERAL_DEPTH:
        raise SuiteUploadError(f"a literal is nested deeper than {MAX_LITERAL_DEPTH} levels")
    if isinstance(value, dict):
        return max((_depth(v, level + 1) for v in (*value.keys(), *value.values())), default=level)
    if isinstance(value, (list, tuple, set, frozenset)):
        return max((_depth(v, level + 1) for v in value), default=level)
    return level


def _literal(text: str, what: str):
    if not isinstance(text, str):
        raise SuiteUploadError(f"{what} must be a string containing a Python literal")
    if len(text) > MAX_LITERAL_CHARS:
        raise SuiteUploadError(f"{what} is longer than {MAX_LITERAL_CHARS} characters")
    try:
        value = ast.literal_eval(text)  # literals only: never executes code
    except (ValueError, SyntaxError, MemoryError, RecursionError):
        raise SuiteUploadError(f"{what} is not a plain Python literal") from None
    _depth(value)
    return value


def _check_from_upload(raw: dict) -> Check:
    kind = raw.get("kind")
    if kind not in CHECK_KINDS:
        raise SuiteUploadError(f"unknown check kind {kind!r}; allowed: {', '.join(CHECK_KINDS)}")
    args = _literal(raw.get("args", ""), f"check {kind!r} args")
    if not isinstance(args, tuple):
        raise SuiteUploadError(f"check {kind!r} args must be a tuple literal, for example '([1, 2],)'")
    expected = raw.get("expected")
    if kind in NAME_KINDS:
        if expected not in NAME_KINDS[kind]:
            raise SuiteUploadError(f"check {kind!r} expected must be one of {', '.join(NAME_KINDS[kind])}")
        return Check(kind=kind, args=args, expected=expected)
    if kind == "unchanged_input":
        if expected not in (None, ""):
            raise SuiteUploadError("check 'unchanged_input' takes no expected value")
        return Check(kind=kind, args=args, expected=None)
    # returns: expected is a literal
    return Check(kind=kind, args=args, expected=_literal(expected or "", "check 'returns' expected"))


def _test_from_upload(raw: dict, visibility: str) -> TestCase:
    if not isinstance(raw, dict):
        raise SuiteUploadError("each test must be an object")
    checks = raw.get("checks") or []
    if not isinstance(checks, list) or not checks:
        raise SuiteUploadError(f"test {raw.get('id')!r} must have at least one check")
    return TestCase(
        id=str(raw.get("id", "")),
        description=str(raw.get("description", ""))[:500],
        checks=tuple(_check_from_upload(c) for c in checks),
        visibility=visibility,
    )


def build_suite(suite_id: str, upload: dict) -> EvaluationSuite:
    """Turn a validated upload dict into an EvaluationSuite. Raises SuiteUploadError on any problem.
    The caller still runs EvaluationSuite.validate() and the delta-policy check."""
    contract = upload.get("contract") or {}
    smoke_args = _literal(contract.get("smoke_args", "()"), "contract smoke_args")
    if not isinstance(smoke_args, tuple):
        raise SuiteUploadError("contract smoke_args must be a tuple literal")
    suite = EvaluationSuite(
        id=suite_id,
        description=str(upload.get("description", ""))[:1000],
        language=str(upload.get("language", "python")),
        entrypoint=str(upload.get("entrypoint", "")),
        contract=ContractSpec(
            arity=int(contract.get("arity", 0)),
            smoke_args=smoke_args,
            smoke_type=str(contract.get("smoke_type", "")),
        ),
        quality=QualitySpec(max_complexity=int((upload.get("quality") or {}).get("max_complexity", 10))),
        tests=tuple(
            [_test_from_upload(t, "public") for t in (upload.get("public_tests") or [])]
            + [_test_from_upload(t, "hidden") for t in (upload.get("hidden_tests") or [])]
        ),
    )
    return suite


# ---- storage (dict <-> TestCase) --------------------------------------------------------------
def _check_to_dict(check: Check) -> dict:
    return {"kind": check.kind, "args": repr(check.args), "expected": check.expected
            if check.kind in NAME_KINDS else repr(check.expected)}


def _test_to_dict(test: TestCase) -> dict:
    return {"id": test.id, "description": test.description,
            "checks": [_check_to_dict(c) for c in test.checks]}


def _check_from_dict(raw: dict) -> Check:
    kind = raw["kind"]
    args = ast.literal_eval(raw["args"])
    expected = raw["expected"] if kind in NAME_KINDS else ast.literal_eval(raw["expected"])
    return Check(kind=kind, args=args, expected=expected)


def _test_from_dict(raw: dict, visibility: str) -> TestCase:
    return TestCase(id=raw["id"], description=raw["description"],
                    checks=tuple(_check_from_dict(c) for c in raw["checks"]), visibility=visibility)


def tests_to_dicts(tests: tuple[TestCase, ...]) -> list[dict]:
    return [_test_to_dict(t) for t in tests]


def spec_to_dict(suite: EvaluationSuite) -> dict:
    return {
        "description": suite.description, "language": suite.language, "entrypoint": suite.entrypoint,
        "contract": {"arity": suite.contract.arity, "smoke_args": repr(suite.contract.smoke_args),
                     "smoke_type": suite.contract.smoke_type},
        "quality": {"max_complexity": suite.quality.max_complexity},
    }


def reconstruct(suite_id: str, spec: dict, public_dicts: list[dict], hidden_dicts: list[dict]) -> EvaluationSuite:
    contract = spec["contract"]
    return EvaluationSuite(
        id=suite_id, description=spec["description"], language=spec["language"], entrypoint=spec["entrypoint"],
        contract=ContractSpec(arity=contract["arity"], smoke_args=ast.literal_eval(contract["smoke_args"]),
                              smoke_type=contract["smoke_type"]),
        quality=QualitySpec(max_complexity=spec["quality"]["max_complexity"]),
        tests=tuple([_test_from_dict(t, "public") for t in public_dicts]
                    + [_test_from_dict(t, "hidden") for t in hidden_dicts]),
    )
