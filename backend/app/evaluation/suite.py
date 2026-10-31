"""Trusted evaluation suites: pure data, defined and versioned by the backend.

A suite is NOT generated or supplied by an LLM or an API client. Test inputs and expected values
are plain Python literals; the child process rebuilds them with `ast.literal_eval`, so suite data
is never executed as code.

`suite_hash` fingerprints the whole definition. Two evaluations are only comparable when they
used the same suite hash and the same EVALUATOR_VERSION (the version of the scoring/checking code).
Bump EVALUATOR_VERSION whenever the meaning of a score changes.
"""
import ast
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

EVALUATOR_VERSION = "1"

CHECK_KINDS = ("returns", "raises", "unchanged_input", "all_items_of_type")
_ID = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SUITE_ID = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
SUPPORTED_LANGUAGES = ("python",)
EXCEPTION_NAMES = ("TypeError", "ValueError", "KeyError", "IndexError", "ZeroDivisionError", "AttributeError")
TYPE_NAMES = ("list", "tuple", "dict", "set", "str", "int", "float", "bool")


@dataclass(frozen=True)
class Check:
    """One assertion about a single call of the entry point.

    returns:           result is strictly equal to `expected` (same types all the way down)
    raises:            the call raises `expected` (a built-in exception class name)
    unchanged_input:   no argument is modified by the call, and the result is a new object
    all_items_of_type: result is a list whose every item is exactly of type `expected` (type name)
    """

    kind: str
    args: tuple = ()
    expected: Any = None


VISIBILITIES = ("public", "hidden")


@dataclass(frozen=True)
class TestCase:
    """`visibility`: public tests may be shown to the Generator, the Critic and API clients. Hidden
    tests are never shown to anyone: only their aggregate count leaves the evaluator. The score's
    pass-rate component is computed from hidden tests only (see app.evaluation.policy)."""

    __test__ = False  # not a pytest class

    id: str
    description: str
    checks: tuple[Check, ...]
    visibility: str = "hidden"


@dataclass(frozen=True)
class ContractSpec:
    """Interface-conformance checks that define the *correctness* score (see docs/EVALUATION_ENGINE.md)."""

    arity: int  # positional arguments the entry point must accept
    smoke_args: tuple  # a trivially valid call...
    smoke_type: str  # ...which must return an object of exactly this built-in type


@dataclass(frozen=True)
class QualitySpec:
    max_complexity: int = 10  # cyclomatic complexity of the worst function that earns full marks


@dataclass(frozen=True)
class EvaluationSuite:
    id: str
    description: str
    language: str
    entrypoint: str
    contract: ContractSpec
    quality: QualitySpec
    tests: tuple[TestCase, ...]

    @property
    def public_tests(self) -> tuple[TestCase, ...]:
        return tuple(t for t in self.tests if t.visibility == "public")

    @property
    def hidden_tests(self) -> tuple[TestCase, ...]:
        return tuple(t for t in self.tests if t.visibility == "hidden")

    def canonical(self, visibility: str | None = None) -> dict:
        """Canonical form for hashing. With `visibility`, only that part of the suite is included."""
        tests = self.tests if visibility is None else tuple(t for t in self.tests if t.visibility == visibility)
        return {
            "id": self.id,
            "language": self.language,
            "entrypoint": self.entrypoint,
            "contract": {"arity": self.contract.arity, "smoke_args": repr(self.contract.smoke_args),
                         "smoke_type": self.contract.smoke_type},
            "quality": {"max_complexity": self.quality.max_complexity},
            "part": visibility or "all",
            "tests": [
                {"id": t.id, "visibility": t.visibility,
                 "checks": [{"kind": c.kind, "args": repr(c.args), "expected": repr(c.expected)} for c in t.checks]}
                for t in tests
            ],
        }

    @staticmethod
    def _hash(data: dict) -> str:
        blob = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    @property
    def suite_hash(self) -> str:
        """Fingerprint of the whole suite (public + hidden + contract + quality settings)."""
        return self._hash(self.canonical())

    @property
    def public_suite_hash(self) -> str:
        return self._hash(self.canonical("public"))

    @property
    def hidden_suite_hash(self) -> str:
        """Commitment to the hidden tests. Safe to publish: it reveals nothing about their contents."""
        return self._hash(self.canonical("hidden"))

    def validate(self) -> None:
        """Structural validation. An EMPTY suite is representable (so it can be refused explicitly by
        the evaluator) but every test that exists must be well-formed."""
        problems = []
        if not _SUITE_ID.match(self.id):
            problems.append(f"bad suite id {self.id!r}")
        if self.language not in SUPPORTED_LANGUAGES:
            problems.append(f"unsupported language {self.language!r}")
        if not self.entrypoint.isidentifier():
            problems.append("entrypoint must be a Python identifier")
        if self.contract.arity < 0:
            problems.append("contract arity must be >= 0")
        if self.contract.smoke_type not in TYPE_NAMES:
            problems.append(f"unknown smoke type {self.contract.smoke_type!r}")
        if self.quality.max_complexity < 1:
            problems.append("max_complexity must be >= 1")
        seen: set[str] = set()
        for test in self.tests:
            if not _ID.match(test.id):
                problems.append(f"bad test id {test.id!r}")
            if test.id in seen:
                problems.append(f"duplicate test id {test.id!r}")
            seen.add(test.id)
            if test.visibility not in VISIBILITIES:
                problems.append(f"test {test.id!r}: visibility must be one of {VISIBILITIES}")
            if not test.checks:
                problems.append(f"test {test.id!r} has no checks")
            for check in test.checks:
                if check.kind not in CHECK_KINDS:
                    problems.append(f"test {test.id!r}: unknown check kind {check.kind!r}")
                if check.kind == "raises" and check.expected not in EXCEPTION_NAMES:
                    problems.append(f"test {test.id!r}: unsupported exception {check.expected!r}")
                if check.kind == "all_items_of_type" and check.expected not in TYPE_NAMES:
                    problems.append(f"test {test.id!r}: unknown type {check.expected!r}")
                for label, value in (("args", check.args), ("expected", check.expected)):
                    try:
                        if ast.literal_eval(repr(value)) != value:
                            problems.append(f"test {test.id!r}: {label} do not survive a literal round-trip")
                    except (ValueError, SyntaxError):
                        problems.append(f"test {test.id!r}: {label} are not plain literals")
        if problems:
            raise ValueError("invalid evaluation suite: " + "; ".join(problems))
