"""Encryption at rest for uploaded hidden tests (Fernet: AES-128-CBC + HMAC-SHA256, authenticated).

The key comes from the environment (`HIDDEN_SUITE_KEY`). In development or test, if no key is configured,
a per-install key file is created and that FACT is logged (never the key). In production a missing key
means uploads are refused: no key is ever generated silently on a production host.

SECURITY LIMIT, stated plainly: the key lives on the same machine as the evaluator (an env var or a
local file). This is encryption at rest. It protects a stolen database file or backup; it does NOT
protect against an attacker who already controls the host, who can read the key and decrypt. The
hidden tests are decrypted in memory at evaluation time; nothing persists the plaintext (the subprocess
runner does write the suite to a per-run temp directory while the child runs, then deletes it).
"""
import logging
import os
import stat

from cryptography.fernet import Fernet, InvalidToken

log = logging.getLogger("app.sealing")

_GENERATED_FILES: set[str] = set()  # paths we have already logged a generation for (avoids repeat logs)


class SealingUnavailableError(Exception):
    """No key is configured and none may be generated (production). Uploads must be refused."""


class SuiteDecryptionError(Exception):
    """A stored hidden-suite token could not be decrypted (wrong key, or tampering). Fernet is
    authenticated, so this covers both a corrupted token and the wrong key."""


def _key_from_settings(settings) -> bytes | None:
    key = getattr(settings, "hidden_suite_key", None)
    if key is None:
        return None
    raw = key.get_secret_value() if hasattr(key, "get_secret_value") else str(key)
    return raw.strip().encode() if raw.strip() else None


def _load_or_create_key_file(settings) -> bytes:
    path = settings.hidden_suite_key_file
    if os.path.exists(path):
        return open(path, "rb").read().strip()
    key = Fernet.generate_key()
    # Write with owner-only permissions where the OS honours them (best effort on Windows).
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, stat.S_IRUSR | stat.S_IWUSR)
    try:
        os.write(fd, key)
    finally:
        os.close(fd)
    if path not in _GENERATED_FILES:
        _GENERATED_FILES.add(path)
        log.warning("generated a new hidden-suite encryption key file at %s (key not logged)", path)
    return key


def encryption_available(settings) -> bool:
    """True when a hidden-suite suite could be encrypted right now (without creating anything)."""
    if _key_from_settings(settings) is not None:
        return True
    if settings.app_env == "production":
        return False
    return True  # dev/test can create a key file on demand


def get_cipher(settings) -> Fernet:
    """The Fernet cipher for hidden tests, or raise SealingUnavailableError if none is available.
    In dev/test a key file is created on first use; in production the key must already be configured."""
    key = _key_from_settings(settings)
    if key is None:
        if settings.app_env == "production":
            raise SealingUnavailableError(
                "HIDDEN_SUITE_KEY is not set. A production host will not generate a key automatically, so "
                "uploaded hidden suites cannot be sealed. Set HIDDEN_SUITE_KEY."
            )
        key = _load_or_create_key_file(settings)
    try:
        return Fernet(key)
    except (ValueError, TypeError) as exc:
        raise SealingUnavailableError("The configured hidden-suite key is not a valid Fernet key.") from exc


def encrypt(settings, plaintext: bytes) -> bytes:
    return get_cipher(settings).encrypt(plaintext)


def decrypt(settings, token: bytes) -> bytes:
    try:
        return get_cipher(settings).decrypt(token)
    except InvalidToken as exc:
        raise SuiteDecryptionError(
            "The stored hidden suite could not be decrypted (wrong key or tampered data)."
        ) from exc
