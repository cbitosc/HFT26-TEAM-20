"""Hashing and canonical serialisation shared by versions, evaluations and evidence bundles.

code_sha256: SHA-256 of the UTF-8 bytes of the source exactly as stored, lowercase hex.
canonical_json: sorted keys, no insignificant whitespace, UTF-8 (non-ASCII kept as is), no NaN or
Infinity. The same object always serialises to the same bytes, so its hash is stable.
"""
import hashlib
import json
import re

SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
# SQLite CHECK fragment: exactly 64 lowercase hex characters.
SHA256_SQL = "length({col}) = 64 AND {col} NOT GLOB '*[^0-9a-f]*'"


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def code_sha256(code: str) -> str:
    return sha256_hex(code.encode("utf-8"))


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def canonical_sha256(obj) -> str:
    return sha256_hex(canonical_json(obj).encode("utf-8"))


def is_canonical(text: str) -> bool:
    try:
        return canonical_json(json.loads(text)) == text
    except (ValueError, TypeError):
        return False
