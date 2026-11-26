"""The egress scanner. Pure functions, no I/O, no network, no database.

`scan_bundle(bundle, forbidden_tokens=...)` walks every STRING VALUE of the bundle (keys are left
alone), redacts anything sensitive, and returns an `EgressReport`. Hidden test data and private-key
blocks force the `blocked` outcome; everything else is redacted and the run may continue with the
redacted copy.

Design notes:
- We scan values, not keys, so field names like `generation_prompt_tokens` are never touched.
- 64-hex strings are the bundle's own SHA-256 hashes and MUST survive (publishing them is the point),
  so the entropy detector explicitly skips pure-hex tokens. Ethereum private keys are 0x + 64 hex,
  which is a distinct shape and IS flagged.
"""
from __future__ import annotations

import copy
import math
import re
from dataclasses import dataclass

from app.hashing import canonical_json, sha256_hex

OUTCOME_PASSED = "passed"
OUTCOME_REDACTED = "redacted"
OUTCOME_BLOCKED = "blocked"

# A finding in any of these categories means the bundle must never be uploaded, even redacted.
BLOCK_CATEGORIES: frozenset[str] = frozenset({"private_key", "hidden_leak"})

# Bundle fields that hold generator source. They are scanned like everything else (a secret pasted
# into code must still be caught), but see docs/EGRESS_GATE.md on the limits for code.
_PLACEHOLDER = "[REDACTED:{category}]"

# (category, compiled pattern, group). group 0 redacts the whole match; a positive group redacts only
# that capture (used for `key = value` shapes so the label stays readable).
_PATTERNS: list[tuple[str, re.Pattern[str], int]] = [
    # Private key PEM blocks -> BLOCK.
    ("private_key",
     re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9 ]*PRIVATE KEY-----"),
     0),
    # Ethereum private key: 0x + exactly 64 hex (distinct from the bundle's bare 64-hex hashes).
    ("private_key", re.compile(r"\b0x[a-fA-F0-9]{64}\b"), 0),
    # Named provider tokens.
    ("secret", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"), 0),              # OpenAI-style
    ("secret", re.compile(r"\bAKIA[0-9A-Z]{16}\b"), 0),                # AWS access key id
    ("secret", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), 0),      # GitHub token
    ("secret", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), 0),    # Slack token
    ("secret", re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}\b"), 0),         # Google API key
    ("secret", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"), 0),  # JWT
    # key = value / key: value assignments (redact the value only).
    ("secret",
     re.compile(r"(?i)(?:api[_-]?key|secret|token|password|passwd|pwd|authorization|bearer)"
                r"\s*[:=]\s*['\"]?([A-Za-z0-9/+_\-\.]{12,})"),
     1),
    # PII.
    ("pii_email", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"), 0),
    ("pii_phone",
     re.compile(r"(?<!\d)(?:\+?\d{1,3}[\s.\-]?)?(?:\(?\d{3}\)?[\s.\-]?)\d{3}[\s.\-]?\d{4}(?!\d)"),
     0),
    ("pii_id", re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), 0),               # SSN-shaped
    ("pii_id", re.compile(r"(?<!\d)\d{13,19}(?!\d)"), 0),              # card-shaped long digit run
    # Local filesystem paths.
    ("local_path", re.compile(r"[A-Za-z]:\\[^\s\"'<>|]+"), 0),         # Windows
    ("local_path", re.compile(r"/(?:home|Users|root)/[^\s\"'<>|]+"), 0),  # Unix
    # Hostnames / URLs.
    ("hostname", re.compile(r"\bhttps?://[^\s\"'<>]+"), 0),
    ("hostname", re.compile(r"\blocalhost:\d{2,5}\b"), 0),
    ("hostname", re.compile(r"\b(?:[a-z0-9\-]+\.)+(?:com|net|org|io|ai|co|internal|local|dev)\b"), 0),
]

_ENTROPY_TOKEN = re.compile(r"[A-Za-z0-9/+_=]{24,}")
_HEX_ONLY = re.compile(r"^[0-9a-fA-F]+$")


@dataclass
class EgressReport:
    outcome: str
    categories: dict[str, int]          # counts only, never values
    original_sha256: str
    redacted_sha256: str
    redacted_bundle: dict               # the copy that MAY be uploaded (only when not blocked)

    def as_dict(self) -> dict:
        """The hidden-safe view for an API or a record: counts and hashes, never a matched value."""
        return {
            "outcome": self.outcome,
            "categories": dict(sorted(self.categories.items())),
            "original_sha256": self.original_sha256,
            "redacted_sha256": self.redacted_sha256,
        }


def _shannon_entropy(text: str) -> float:
    if not text:
        return 0.0
    freq: dict[str, int] = {}
    for ch in text:
        freq[ch] = freq.get(ch, 0) + 1
    n = len(text)
    return -sum((c / n) * math.log2(c / n) for c in freq.values())


def _looks_like_secret_token(token: str) -> bool:
    """A long, high-entropy, mixed-case/digit run that is not a plain hex hash."""
    if _HEX_ONLY.match(token):
        return False  # the bundle's own SHA-256 hashes must survive
    has_alpha = any(c.isalpha() for c in token)
    has_digit = any(c.isdigit() for c in token)
    if not (has_alpha and has_digit):
        return False
    return _shannon_entropy(token) >= 4.2


def _redact_text(text: str, forbidden_tokens: frozenset[str]) -> tuple[str, dict[str, int]]:
    counts: dict[str, int] = {}

    def bump(category: str, n: int = 1) -> None:
        if n:
            counts[category] = counts.get(category, 0) + n

    # Hidden test ids / literals first (exact substring); these force a block upstream.
    for token in forbidden_tokens:
        if token and token in text:
            occurrences = text.count(token)
            text = text.replace(token, _PLACEHOLDER.format(category="hidden_leak"))
            bump("hidden_leak", occurrences)

    for category, pattern, group in _PATTERNS:
        def _sub(match: re.Match[str]) -> str:
            if group == 0:
                return _PLACEHOLDER.format(category=category)
            start, end = match.span(group)
            whole = match.group(0)
            rel_s, rel_e = start - match.start(), end - match.start()
            return whole[:rel_s] + _PLACEHOLDER.format(category=category) + whole[rel_e:]

        text, n = pattern.subn(_sub, text)
        bump(category, n)

    # Entropy pass last, on whatever survived, skipping our own placeholders.
    def _entropy_sub(match: re.Match[str]) -> str:
        token = match.group(0)
        if token in ("REDACTED",) or _looks_like_secret_token(token) is False:
            return token
        bump("high_entropy", 1)
        return _PLACEHOLDER.format(category="high_entropy")

    text = _ENTROPY_TOKEN.sub(_entropy_sub, text)
    return text, counts


def _walk_redact(node, forbidden_tokens: frozenset[str], counts: dict[str, int]):
    if isinstance(node, dict):
        return {k: _walk_redact(v, forbidden_tokens, counts) for k, v in node.items()}
    if isinstance(node, list):
        return [_walk_redact(v, forbidden_tokens, counts) for v in node]
    if isinstance(node, str):
        new_text, local = _redact_text(node, forbidden_tokens)
        for category, n in local.items():
            counts[category] = counts.get(category, 0) + n
        return new_text
    return node


def scan_bundle(bundle: dict, *, forbidden_tokens: frozenset[str] = frozenset()) -> EgressReport:
    """Scan and redact a bundle. Returns an EgressReport whose `redacted_bundle` is safe to upload
    only when `outcome != blocked`."""
    original = copy.deepcopy(bundle)
    counts: dict[str, int] = {}
    redacted = _walk_redact(original, frozenset(forbidden_tokens), counts)

    if any(counts.get(cat, 0) for cat in BLOCK_CATEGORIES):
        outcome = OUTCOME_BLOCKED
    elif counts:
        outcome = OUTCOME_REDACTED
    else:
        outcome = OUTCOME_PASSED

    original_sha256 = sha256_hex(canonical_json(bundle).encode("utf-8"))
    redacted_sha256 = sha256_hex(canonical_json(redacted).encode("utf-8"))
    return EgressReport(
        outcome=outcome,
        categories={k: v for k, v in counts.items() if v},
        original_sha256=original_sha256,
        redacted_sha256=redacted_sha256,
        redacted_bundle=redacted,
    )


def suite_hidden_tokens() -> frozenset[str]:
    """Hidden test ids and distinctive literals across every registered suite, plus the synthetic
    gate ids t0..t49. These are what the gate refuses to let leave the process. Derived server-side;
    never uploaded."""
    from app.evaluation.suites import SUITES

    tokens: set[str] = {f"t{i}" for i in range(50)}
    for suite in SUITES.values():
        for test in suite.hidden_tests:
            tokens.add(test.id)
            if test.description and len(test.description) >= 8:
                tokens.add(test.description)
            for check in test.checks:
                args_repr = repr(check.args)
                if len(args_repr) >= 8:
                    tokens.add(args_repr)
                if check.kind == "returns":
                    exp_repr = repr(check.expected)
                    if len(exp_repr) >= 8:
                        tokens.add(exp_repr)
    return frozenset(tokens)
