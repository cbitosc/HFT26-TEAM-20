"""Deterministic static code-quality score (0-100) from the standard-library `ast`.

Five equally weighted checks, each scored 0..1:
  syntax_valid                the source parses
  complexity_within_limit     worst cyclomatic complexity of any function <= suite limit (graded below it)
  entrypoint_documented       the entry point has a non-empty docstring
  entrypoint_type_annotated   every parameter and the return value of the entry point is annotated
  no_hazardous_constructs     no bare `except:`, eval/exec/__import__ calls, `import *`, mutable defaults

Quality is only assessed for code that actually provides the required entry point as a module-level
function. Otherwise the score is 0, so a module that merely parses cannot earn partial credit.

NOT measured (unsupported, deliberately): formatting, naming, style, readability, design, comments,
duplication, test coverage, time/space complexity, or a "lint score" (no linter is installed).
The checks inspect structure only; a docstring's presence says nothing about its content.
"""
import ast
from dataclasses import dataclass

from app.evaluation.suite import QualitySpec

CHECK_IDS = (
    "syntax_valid",
    "complexity_within_limit",
    "entrypoint_documented",
    "entrypoint_type_annotated",
    "no_hazardous_constructs",
)
_HAZARD_CALLS = {"eval", "exec", "__import__"}
_MUTABLE_DEFAULT_CALLS = {"list", "dict", "set"}
_PARSE_ERRORS = (SyntaxError, ValueError, RecursionError, MemoryError, OverflowError)


@dataclass(frozen=True)
class QualityCheck:
    id: str
    score: float  # 0..1
    detail: str


@dataclass(frozen=True)
class QualityReport:
    score: float  # 0..100
    checks: tuple[QualityCheck, ...]
    max_complexity: int | None


def cyclomatic_complexity(func: ast.AST) -> int:
    """1 + decision points inside the function, not counting nested function/class bodies (they are
    measured on their own): if/elif, ternary, for, while, except, each comprehension clause and
    comprehension condition, each extra operand of and/or, and each match case."""
    count = 1
    stack = list(ast.iter_child_nodes(func))
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if isinstance(node, (ast.If, ast.IfExp, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler)):
            count += 1
        elif isinstance(node, ast.comprehension):
            count += 1 + len(node.ifs)
        elif isinstance(node, ast.BoolOp):
            count += len(node.values) - 1
        elif isinstance(node, ast.match_case):
            count += 1
        stack.extend(ast.iter_child_nodes(node))
    return count


def _hazards(tree: ast.AST) -> list[str]:
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            found.append(f"bare except (line {node.lineno})")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _HAZARD_CALLS:
            found.append(f"call to {node.func.id}() (line {node.lineno})")
        elif isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names):
            found.append(f"wildcard import (line {node.lineno})")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            for default in [*node.args.defaults, *[d for d in node.args.kw_defaults if d is not None]]:
                mutable = isinstance(default, (ast.List, ast.Dict, ast.Set, ast.ListComp, ast.DictComp, ast.SetComp))
                call = (isinstance(default, ast.Call) and isinstance(default.func, ast.Name)
                        and default.func.id in _MUTABLE_DEFAULT_CALLS)
                if mutable or call:
                    found.append(f"mutable default argument (line {default.lineno})")
    return found


def _annotated(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    args = fn.args
    params = [*args.posonlyargs, *args.args, *args.kwonlyargs]
    if args.vararg:
        params.append(args.vararg)
    if args.kwarg:
        params.append(args.kwarg)
    params = [p for i, p in enumerate(params) if not (i == 0 and p.arg in {"self", "cls"})]
    return fn.returns is not None and all(p.annotation is not None for p in params)


def _zero(detail: str, max_complexity: int | None = None) -> QualityReport:
    return QualityReport(0.0, tuple(QualityCheck(i, 0.0, detail) for i in CHECK_IDS), max_complexity)


def analyze(source: str, entrypoint: str, spec: QualitySpec) -> QualityReport:
    try:
        tree = ast.parse(source, filename="candidate.py")
    except _PARSE_ERRORS as exc:
        return _zero(f"source does not parse: {type(exc).__name__}")
    entry = next(
        (n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == entrypoint),
        None,
    )
    if entry is None:
        return QualityReport(0.0, (QualityCheck("syntax_valid", 0.0, "not assessed: entry point missing"),
                                   *[QualityCheck(i, 0.0, "not assessed: entry point missing") for i in CHECK_IDS[1:]]), None)

    functions = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    worst = max(cyclomatic_complexity(f) for f in functions)
    limit = spec.max_complexity
    complexity_score = 1.0 if worst <= limit else max(0.0, 1.0 - (worst - limit) / limit)
    doc = ast.get_docstring(entry)
    hazards = _hazards(tree)

    checks = (
        QualityCheck("syntax_valid", 1.0, "source parses"),
        QualityCheck("complexity_within_limit", complexity_score, f"worst cyclomatic complexity {worst}, limit {limit}"),
        QualityCheck("entrypoint_documented", 1.0 if doc and doc.strip() else 0.0,
                     "docstring present" if doc and doc.strip() else "no docstring"),
        QualityCheck("entrypoint_type_annotated", 1.0 if _annotated(entry) else 0.0,
                     "fully annotated" if _annotated(entry) else "missing annotations"),
        QualityCheck("no_hazardous_constructs", 0.0 if hazards else 1.0, "; ".join(hazards[:3]) or "none found"),
    )
    return QualityReport(100.0 * sum(c.score for c in checks) / len(checks), checks, worst)
