"""Trusted suite for the `merge_intervals` task: 5 public tests and 10 hidden tests.

The behaviours are the ones the Prompt 03.2/03.3 research harness used (touching/contained/unsorted/
empty inputs, no mutation of the caller's list, the exact TypeError/ValueError contract), plus one
hidden test for duplicate intervals so the hidden part has 10 tests (one hidden test = 5 points).

Public tests can be shown to the Generator and the Critic. Hidden tests must never be shown to them
or to API clients; only the hidden aggregate count leaves the evaluator.

LIMITATION (demo): this file is in the repository, so anyone who can read the repository can read the
hidden tests. "Hidden" here means hidden from the agents and the API, not secret. Holding hidden suites
outside the repository is an open production decision (PRD open decision 5).
"""
from app.evaluation.suite import Check, ContractSpec, EvaluationSuite, QualitySpec, TestCase


def _returns(name, description, intervals, expected, visibility):
    return TestCase(name, description, (Check("returns", (intervals,), expected),), visibility)


def _raises(name, description, exc, visibility, *arg_sets):
    return TestCase(name, description, tuple(Check("raises", args, exc) for args in arg_sets), visibility)


PUBLIC, HIDDEN = "public", "hidden"

SUITE = EvaluationSuite(
    id="python-merge-intervals-v1",
    description="Merge overlapping or touching (start, end) integer intervals; validates input; never mutates it.",
    language="python",
    entrypoint="merge_intervals",
    contract=ContractSpec(arity=1, smoke_args=([(1, 2)],), smoke_type="list"),
    quality=QualitySpec(max_complexity=10),
    tests=(
        # ---- public (5) ----
        _returns("overlap", "overlapping intervals merge", [(1, 3), (2, 6), (8, 10)], [(1, 6), (8, 10)], PUBLIC),
        _returns("touching", "intervals that touch merge", [(1, 3), (3, 5)], [(1, 5)], PUBLIC),
        _returns("unsorted_input", "unsorted input is handled", [(8, 10), (1, 3), (2, 6)], [(1, 6), (8, 10)], PUBLIC),
        _returns("empty", "an empty list returns an empty list", [], [], PUBLIC),
        _raises("typeerror_not_list", "a non-list argument raises TypeError", "TypeError", PUBLIC,
                (None,), (((1, 2),),)),
        # ---- hidden (10) ----
        _returns("contained", "a contained interval must not shrink the result", [(1, 10), (2, 3)], [(1, 10)], HIDDEN),
        _returns("chain", "a chain of touching intervals collapses", [(1, 4), (4, 5), (5, 9), (10, 11)],
                 [(1, 9), (10, 11)], HIDDEN),
        _returns("single_point", "a zero-length interval survives", [(4, 4)], [(4, 4)], HIDDEN),
        _returns("duplicates", "duplicate intervals collapse to one", [(2, 5), (2, 5), (3, 3)], [(2, 5)], HIDDEN),
        TestCase("input_not_mutated", "the caller's list is not modified and a new list is returned",
                 (Check("unchanged_input", ([(5, 6), (1, 2), (2, 3)],)),), HIDDEN),
        TestCase("returns_tuples", "merged intervals are tuples",
                 (Check("all_items_of_type", ([(1, 2), (2, 3), (7, 8)],), "tuple"),), HIDDEN),
        _raises("typeerror_bad_element", "a malformed element raises TypeError", "TypeError", HIDDEN,
                ([(1, 2), (3,)],), ([(1, "a")],), ([(1, 2), [3, 4]],)),
        _raises("valueerror_start_gt_end", "start > end raises ValueError", "ValueError", HIDDEN, ([(5, 1)],)),
        _raises("validation_applies_to_all", "every interval is validated", "ValueError", HIDDEN, ([(1, 2), (9, 3)],)),
        _raises("typeerror_non_int_values", "non-integer values raise TypeError", "TypeError", HIDDEN,
                ([(1.5, 2.5)],), ([("a", "b")],)),
    ),
)
