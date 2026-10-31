"""Deterministic changelog of a revision against its parent, derived only from the unified diff and
the parsed definitions. No model is involved, and the same two sources always give the same lines."""
import ast
import difflib


def unified_diff(parent_code: str, code: str, parent_label: str, label: str) -> str:
    return "\n".join(difflib.unified_diff(parent_code.splitlines(), code.splitlines(),
                                          fromfile=parent_label, tofile=label, lineterm=""))


def _definitions(code: str) -> dict[str, str] | None:
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None
    return {node.name: ast.dump(node, include_attributes=False) for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}


def revision_changelog(parent_code: str, code: str, parent_label: str, label: str) -> list[str]:
    diff = unified_diff(parent_code, code, parent_label, label).splitlines()
    if not diff:
        return [f"{label} is identical to {parent_label}."]
    added = sum(1 for line in diff if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in diff if line.startswith("-") and not line.startswith("---"))
    hunks = sum(1 for line in diff if line.startswith("@@"))
    log = [f"{label} changes {parent_label}: +{added} / -{removed} lines in {hunks} hunk(s)."]
    before, after = _definitions(parent_code), _definitions(code)
    if before is None or after is None:
        log.append("Definitions not compared: " + ("the parent" if before is None else label) + " does not parse.")
        return log
    for kind, names in (("added", sorted(set(after) - set(before))),
                        ("removed", sorted(set(before) - set(after))),
                        ("changed", sorted(n for n in set(before) & set(after) if before[n] != after[n]))):
        if names:
            log.append(f"Definitions {kind}: {', '.join(names)}.")
    if len(log) == 1:
        log.append("No top-level definition changed (edits are in comments, formatting or module-level code).")
    return log
