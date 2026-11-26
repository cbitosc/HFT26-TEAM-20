"""Egress gate: the last check before any evidence leaves the process.

Nothing is uploaded until a bundle passes this gate. The gate scans a bundle for secrets, PII,
local paths, hostnames and any hidden test id or literal, then returns one of three outcomes:

    passed     nothing sensitive found; the bundle may be uploaded as-is
    redacted   sensitive values were replaced with [REDACTED:<category>]; the REDACTED bundle may
               be uploaded (the original never is)
    blocked    something that must never leave was found (a private key block, or hidden test data);
               nothing is uploaded and the publication stays local

The report carries COUNTS BY CATEGORY ONLY and the original/redacted hashes. It never carries a
matched value. See docs/EGRESS_GATE.md for what regex and entropy scanning cannot catch.
"""
from app.egress.scanner import (
    BLOCK_CATEGORIES,
    OUTCOME_BLOCKED,
    OUTCOME_PASSED,
    OUTCOME_REDACTED,
    EgressReport,
    scan_bundle,
    suite_hidden_tokens,
)

__all__ = [
    "BLOCK_CATEGORIES",
    "OUTCOME_BLOCKED",
    "OUTCOME_PASSED",
    "OUTCOME_REDACTED",
    "EgressReport",
    "scan_bundle",
    "suite_hidden_tokens",
]
