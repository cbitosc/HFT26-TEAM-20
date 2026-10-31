# Egress Gate

**Status:** implemented (Milestone 10, slice A). Module: `backend/app/egress/`.
Tests: `backend/tests/test_egress.py` (includes a 32-secret red-team).

The egress gate is the last check before any evidence bundle leaves the process. Nothing is uploaded
to IPFS or referenced on-chain until a bundle has passed through it.

## What it does

`scan_bundle(bundle, forbidden_tokens=...)` walks every **string value** of the bundle (never the
keys), redacts anything sensitive, and returns an `EgressReport`:

| Field | Meaning |
|---|---|
| `outcome` | `passed`, `redacted`, or `blocked` |
| `categories` | **counts only**, per category — never a matched value |
| `original_sha256` | SHA-256 of the canonical bundle before redaction |
| `redacted_sha256` | SHA-256 of the canonical bundle after redaction |
| `redacted_bundle` | the copy that may be uploaded — **only when `outcome != blocked`** |

Outcomes:
- **passed** — nothing sensitive found; upload as-is.
- **redacted** — secrets/PII/paths/hostnames were replaced with `[REDACTED:<category>]`; the redacted
  copy may be uploaded. The original is never uploaded.
- **blocked** — a private-key block or hidden test data was found. Nothing is uploaded; the
  publication stays local. (`BLOCK_CATEGORIES = {private_key, hidden_leak}`.)

Categories detected: `secret` (provider token shapes and `key = value` assignments), `private_key`
(PEM blocks, `0x`+64-hex Ethereum keys), `high_entropy` (long mixed tokens), `pii_email`,
`pii_phone`, `pii_id` (SSN/card shapes), `local_path` (Windows and Unix), `hostname` (URLs,
`localhost:port`, bare domains), and `hidden_leak` (any hidden test id/literal supplied in
`forbidden_tokens`; derive these server-side with `suite_hidden_tokens()`).

The report deliberately carries **counts and hashes only** — a caller or an API can show "3 secrets,
1 email redacted" without ever re-exposing the value it just removed.

### Why the bundle's own hashes survive
An evidence bundle is full of SHA-256 hashes (64 hex), and publishing those is the entire point. The
entropy detector therefore skips pure-hex tokens. Ethereum private keys are a **different** shape
(`0x` + 64 hex) and are flagged.

## What regex and entropy scanning CANNOT catch

This gate reduces risk; it does not guarantee a leak-free export. It will miss:

1. **Semantic leaks.** A secret paraphrased in prose, split across fields, or described rather than
   quoted ("the key starts with sk and ends in R8U") is invisible to pattern matching.
2. **Encoded or transformed secrets.** Base64/hex/gzip/rot13 of a secret, or a secret reconstructed
   from pieces, won't match a plaintext pattern. (High-entropy detection catches *some* encoded
   blobs but also cannot see meaning.)
3. **Novel or short credentials.** Tokens that don't match a known provider shape and are short or
   low-entropy (a 10-character password, an internal API id) slip through the named patterns.
4. **Legitimate-looking data that is actually sensitive.** A customer id that looks like an ordinary
   integer, an internal hostname that uses a public TLD, a path that doesn't start with the known
   roots — all look benign.
5. **Hidden test logic, as opposed to hidden test identifiers.** `forbidden_tokens` blocks known
   hidden ids and distinctive literals, but it cannot recognise a hidden test's *logic* if the
   generated code or diff happens to reconstruct it. Hidden-suite contents are kept out of bundles at
   the source (bundles carry counts only); this gate is a second line, not the first.
6. **Over-redaction risk.** Aggressive entropy thresholds would start redacting legitimate
   high-entropy code tokens or identifiers, corrupting the published artifact. The thresholds here
   are deliberately conservative, which trades some recall for not mangling valid data.

Because of the above, the primary defences remain upstream: bundles are built from hidden-safe data
(counts only, no hidden ids/inputs/results), secrets live in environment variables and are never
written into records, and this gate is the final backstop — not the only one.
