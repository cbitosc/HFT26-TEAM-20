"""The ONLY sources of suite and evaluation data that may reach an LLM prompt.

Everything here is hidden-test safe by construction: public tests are rendered from the suite's public
part only; failure details are filtered to public tests; hidden results are reduced to two numbers.
Prompt builders must take their evaluation data from these functions, never from raw records.
"""
from dataclasses import dataclass

from app.evaluation.suite import EvaluationSuite

CLIP = 400


def _clip(text, limit: int = CLIP) -> str:
    text = "" if text is None else str(text)
    return text if len(text) <= limit else text[:limit] + "...[truncated]"


def render_public_tests(suite: EvaluationSuite) -> str:
    """Human-readable public tests. Hidden tests are never read here."""
    lines = []
    for test in suite.public_tests:
        lines.append(f"- {test.id}: {test.description}")
        for check in test.checks:
            call = f"{suite.entrypoint}({', '.join(repr(a) for a in check.args)})"
            if check.kind == "returns":
                lines.append(f"    {call} == {check.expected!r}")
            elif check.kind == "raises":
                lines.append(f"    {call} raises {check.expected}")
            elif check.kind == "unchanged_input":
                lines.append(f"    {call} leaves its argument unchanged and returns a new object")
            elif check.kind == "all_items_of_type":
                lines.append(f"    {call} returns a list whose items are all of type {check.expected}")
    return "\n".join(lines) if lines else "(no public tests)"


@dataclass(frozen=True)
class PublicEvidence:
    public_failures: list[dict]  # [{test, expected, actual, exception}] for PUBLIC tests only
    public_passed: int
    public_total: int


@dataclass(frozen=True)
class HiddenCounts:
    passed: int
    total: int


def public_evidence(evaluation) -> PublicEvidence:
    failures = [
        {"test": d.get("test_name"), "expected": _clip(d.get("expected")), "actual": _clip(d.get("actual")),
         "exception": _clip(d.get("exception")) if d.get("exception") else None}
        for d in (evaluation.failure_details or []) if d.get("visibility") == "public"
    ]
    return PublicEvidence(failures, evaluation.public_tests_passed or 0, evaluation.public_tests_total or 0)


def hidden_counts(evaluation) -> HiddenCounts:
    return HiddenCounts(evaluation.tests_passed, evaluation.tests_total)


def render_public_failures(evidence: PublicEvidence) -> str:
    if not evidence.public_failures:
        return f"All {evidence.public_total} public tests pass."
    lines = [f"{evidence.public_passed} of {evidence.public_total} public tests pass. Failing public tests:"]
    for f in evidence.public_failures:
        line = f"- {f['test']}: expected {f['expected']}; actual {f['actual']}"
        if f["exception"]:
            line += f"; exception {f['exception']}"
        lines.append(line)
    return "\n".join(lines)
