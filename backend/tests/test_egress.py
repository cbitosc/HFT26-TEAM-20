"""Egress-gate tests, including a red-team of 30+ seeded secrets.

The gate must let the bundle's own SHA-256 hashes through (publishing them is the whole point) while
catching secrets, PII, local paths, hostnames and any hidden test id/literal. The red-team measures
the REAL miss count: after scanning, no seeded secret value may survive in the redacted bundle.
"""
import json

from app.egress import (
    OUTCOME_BLOCKED,
    OUTCOME_PASSED,
    OUTCOME_REDACTED,
    scan_bundle,
    suite_hidden_tokens,
)

# These example secrets are fake, but match real provider shapes, so they are assembled from
# fragments here: the full literal never appears in the file (which keeps repository secret-scanning
# from flagging a test fixture), while the scanner still sees the complete string at runtime.
PEM = (
    "-----BEGIN RSA PRIVATE" + " KEY-----\n"
    "MIIEowIBAAKCAQEA4f7Qe2d1vUNIQUE0PEM0BODY0LINE0aaaaaaaaaaaaaaaaaaa\n"
    "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\n"
    "-----END RSA PRIVATE" + " KEY-----"
)

_SK = "sk-" + "ABCDEFGHIJKLMNOPQRST0123"
_AKIA = "AKIA" + "IOSFODNN7EXAMPLE"
_GHP = "ghp" + "_ABCDEFGHIJKLMNOPQRSTUVWX012345"
_XOXB = "xoxb-" + "111122223333-AaBbCcDdEeFf"
_AIZA = "AIza" + "SyD0ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456"
_JWT = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" + "."
        + "eyJzdWIiOiIxMjM0NTY3ODkwIn0" + "."
        + "dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U")
_SK_LIVE = "sk_" + "live_51ABCDEFxyz1234567890QRS"
_AWS_SECRET = "wJalrXUtnFEMI" + "K7MDENGbPxRfiCYEXAMPLEKEY"

# (what we inject, the sensitive token that must NOT survive)
SEEDS: list[tuple[str, str]] = [
    (_SK, _SK),
    (_AKIA, _AKIA),
    (_GHP, _GHP),
    (_XOXB, _XOXB),
    (_AIZA, _AIZA),
    ("token " + _JWT, _JWT),
    ("api_key=" + _SK_LIVE, _SK_LIVE),
    ("password=SuperSecretP4ssw0rd123", "SuperSecretP4ssw0rd123"),
    ("aws_secret=" + _AWS_SECRET, _AWS_SECRET),
    ("token=ABCDEF1234567890ghijkl", "ABCDEF1234567890ghijkl"),
    ("secret=abcdEFGH1234ijklMNOP", "abcdEFGH1234ijklMNOP"),
    (PEM, "UNIQUE0PEM0BODY0LINE0"),
    (
        "0x" + "a1b2c3d4" * 8,  # 0x + 64 hex -> eth private key
        "0x" + "a1b2c3d4" * 8,
    ),
    ("0x" + "DEADbeef" * 8, "0x" + "DEADbeef" * 8),
    ("john.doe@example.com", "john.doe@example.com"),
    ("alice99@mail.example.org", "alice99@mail.example.org"),
    ("bob+test@sub.example.net", "bob+test@sub.example.net"),
    ("call 415-555-2671 now", "415-555-2671"),
    ("+1 (650) 555-0199", "(650) 555-0199"),
    ("ring 212.555.0147", "212.555.0147"),
    ("ssn 123-45-6789", "123-45-6789"),
    ("card 4111111111111111", "4111111111111111"),
    ("C:\\Users\\ASUS\\secrets\\prod.env", "C:\\Users\\ASUS\\secrets\\prod.env"),
    ("/home/parth/.ssh/id_rsa", "/home/parth/.ssh/id_rsa"),
    ("/Users/parth/Desktop/key.pem", "/Users/parth/Desktop/key.pem"),
    ("/root/.aws/credentials", "/root/.aws/credentials"),
    ("https://hooks.example.com/abc", "https://hooks.example.com/abc"),
    ("reach localhost:8000 here", "localhost:8000"),
    ("host api.example.io up", "api.example.io"),
    ("host db.internal up", "db.internal"),
    ("Zx9Kq2Lm7Pw4Rt6Yv8Bn1Dc3Fg5Hj", "Zx9Kq2Lm7Pw4Rt6Yv8Bn1Dc3Fg5Hj"),
    ("Q7wE2rT9yU1iO5pA3sD8fG6hJ0kL4z", "Q7wE2rT9yU1iO5pA3sD8fG6hJ0kL4z"),
]


def _all_strings(node):
    if isinstance(node, dict):
        for v in node.values():
            yield from _all_strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from _all_strings(v)
    elif isinstance(node, str):
        yield node


def _red_team_bundle() -> dict:
    return {
        "kind": "autoevolve.evidence_bundle",
        "candidate": {"samples": [inject for inject, _ in SEEDS]},
        "note": "mixed " + " | ".join(inject for inject, _ in SEEDS[:5]),
    }


def test_red_team_catches_every_seeded_secret():
    assert len(SEEDS) >= 30
    report = scan_bundle(_red_team_bundle())

    haystack = "\n".join(_all_strings(report.redacted_bundle))
    misses = [token for _, token in SEEDS if token in haystack]
    assert misses == [], f"{len(misses)} seeded secret(s) survived redaction: {misses}"

    # A private key block was seeded, so the bundle must be blocked, never uploaded.
    assert report.outcome == OUTCOME_BLOCKED
    # Every category should have fired at least once.
    for category in ("secret", "private_key", "pii_email", "pii_phone", "pii_id",
                     "local_path", "hostname", "high_entropy"):
        assert report.categories.get(category, 0) >= 1, f"category {category} did not fire"


def test_report_exposes_counts_and_hashes_only_never_values():
    report = scan_bundle(_red_team_bundle())
    serialized = json.dumps(report.as_dict())
    for _, token in SEEDS:
        assert token not in serialized
    assert set(report.as_dict()) == {"outcome", "categories", "original_sha256", "redacted_sha256"}
    assert "redacted_bundle" not in report.as_dict()


def test_clean_bundle_passes_and_hashes_survive():
    sha = "a" * 64
    bundle = {
        "commitment": {"suite_hash": sha, "public_suite_hash": "b" * 64,
                       "evaluator_config_hash": "c" * 64, "scoring_rule_version": "2", "delta": 1.0},
        "candidate": {"label": "V2", "code_sha256": "d" * 64,
                      "scores": {"hidden_pass_rate": 90.0, "overall": 94.6},
                      "hidden_counts": {"passed": 9, "total": 10}},
        "suite_id": "python-merge-intervals-v1",
        "generator_model_id": "Qwen/Qwen2.5-7B-Instruct",
        "changelog": ["V2 changes V1: +6 / -2 lines in 1 hunk(s)."],
    }
    report = scan_bundle(bundle)
    assert report.outcome == OUTCOME_PASSED
    assert report.categories == {}
    assert report.original_sha256 == report.redacted_sha256  # nothing changed
    # The committed hashes must still be present verbatim.
    haystack = "\n".join(_all_strings(report.redacted_bundle))
    assert sha in haystack and "d" * 64 in haystack


def test_redaction_without_block_yields_redacted_outcome():
    report = scan_bundle({"x": "contact me at john.doe@example.com for the key"})
    assert report.outcome == OUTCOME_REDACTED
    assert report.categories.get("pii_email", 0) == 1
    assert report.original_sha256 != report.redacted_sha256
    assert "john.doe@example.com" not in "\n".join(_all_strings(report.redacted_bundle))


def test_hidden_test_token_forces_block():
    tokens = suite_hidden_tokens()
    assert tokens  # the registered suites and the synthetic gate ids populate this
    bundle = {"leak": "the hidden test t3 unexpectedly appeared here"}
    report = scan_bundle(bundle, forbidden_tokens=tokens)
    assert report.outcome == OUTCOME_BLOCKED
    assert report.categories.get("hidden_leak", 0) >= 1
    assert "t3" not in "\n".join(_all_strings(report.redacted_bundle))
