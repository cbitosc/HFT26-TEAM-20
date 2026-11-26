"""Scanner used by the autouse fixture in conftest.py and by tests: finds hidden test data in bundles.

Checked in every key and every string value of the bundle, except the candidate source fields
(`code`, `diff`), which are generator output:
  * every hidden test id of every registered suite, and the synthetic hidden ids t0..t49 used by gate tests
  * the description and the literal inputs/expected values of every hidden test of every registered suite
  * any per-test entry labelled hidden
"""
import json
import re
import sqlite3
from pathlib import Path

from app.evaluation.suites import SUITES

SOURCE_FIELDS = {"code", "diff"}


def hidden_markers() -> tuple[list[str], list[str]]:
    ids = {f"t{i}" for i in range(50)}
    contents: set[str] = set()
    for suite in SUITES.values():
        for test in suite.hidden_tests:
            ids.add(test.id)
            contents.add(test.description)
            for check in test.checks:
                contents.add(repr(check.args))
                if check.kind == "returns":
                    contents.add(repr(check.expected))
    # Very short literals (for example "[]") also occur in public data; only distinctive ones are checked.
    return sorted(ids), sorted(c for c in contents if len(c) >= 8)


def _strings(node, path=""):
    if isinstance(node, dict):
        for key, value in node.items():
            yield f"{path}.{key}", key
            if key in SOURCE_FIELDS:
                continue
            yield from _strings(value, f"{path}.{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from _strings(value, f"{path}[{i}]")
    elif isinstance(node, str):
        yield path, node


def scan_text(text: str) -> list[str]:
    """Hidden test ids (whole words), descriptions and literal inputs/expected values in free text,
    for example an LLM prompt."""
    ids, contents = hidden_markers()
    leaks = [f"hidden id {i!r}" for i in ids
             if re.search(rf"(?<![A-Za-z0-9_]){re.escape(i)}(?![A-Za-z0-9_])", text)]
    leaks += ["hidden test content" for c in contents if c in text]
    return leaks


def scan_bundle(bundle: dict) -> list[str]:
    ids, contents = hidden_markers()
    patterns = [(i, re.compile(rf"(?<![A-Za-z0-9_]){re.escape(i)}(?![A-Za-z0-9_])")) for i in ids]
    leaks = []
    for where, text in _strings(bundle):
        for hidden_id, rx in patterns:
            if rx.search(text):
                leaks.append(f"{where}: hidden id {hidden_id!r}")
        for content in contents:
            if content in text:
                leaks.append(f"{where}: hidden test content")
    for side in ("previous", "candidate"):
        for entry in (bundle.get(side) or {}).get("public_tests", []):
            if entry.get("visibility") == "hidden" or entry.get("test_id") in ids:
                leaks.append(f"{side}.public_tests: hidden entry")
    return leaks


def scan_database(path: Path) -> list[str]:
    con = sqlite3.connect(path)
    try:
        exists = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='evidence_bundles'").fetchone()
        rows = con.execute("SELECT id, bundle_json FROM evidence_bundles").fetchall() if exists else []
    finally:
        con.close()
    leaks = []
    for bundle_id, text in rows:
        leaks += [f"bundle {bundle_id}: {leak}" for leak in scan_bundle(json.loads(text))]
    return leaks
