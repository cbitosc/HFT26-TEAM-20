"""Encryption at rest for uploaded hidden tests (app.sealing)."""
import pytest
from cryptography.fernet import Fernet

from app import sealing
from app.config import Settings


def _settings(tmp_path, **kw):
    base = dict(_env_file=None, app_env="test", database_url=f"sqlite:///{(tmp_path / 't.db').as_posix()}",
                hidden_suite_key_file=str(tmp_path / ".key"))
    base.update(kw)
    return Settings(**base)


def test_round_trip_and_ciphertext_differs_from_plaintext(tmp_path):
    s = _settings(tmp_path, hidden_suite_key=Fernet.generate_key().decode())
    plaintext = b'[{"id": "hid_1", "secret": "do not leak"}]'
    token = sealing.encrypt(s, plaintext)
    assert token != plaintext and b"do not leak" not in token and b"hid_1" not in token
    assert sealing.decrypt(s, token) == plaintext


def test_tampered_ciphertext_is_refused(tmp_path):
    s = _settings(tmp_path, hidden_suite_key=Fernet.generate_key().decode())
    token = bytearray(sealing.encrypt(s, b"payload"))
    token[-1] ^= 0x01  # flip one bit
    with pytest.raises(sealing.SuiteDecryptionError):
        sealing.decrypt(s, bytes(token))


def test_a_token_made_with_another_key_is_refused(tmp_path):
    maker = _settings(tmp_path, hidden_suite_key=Fernet.generate_key().decode())
    token = sealing.encrypt(maker, b"payload")
    other = _settings(tmp_path, hidden_suite_key=Fernet.generate_key().decode())
    with pytest.raises(sealing.SuiteDecryptionError):
        sealing.decrypt(other, token)


def test_dev_generates_a_key_file_and_logs_the_fact_never_the_key(tmp_path, caplog):
    import logging

    caplog.set_level(logging.DEBUG, logger="app.sealing")
    s = _settings(tmp_path, app_env="development")  # no key configured
    sealing._GENERATED_FILES.discard(s.hidden_suite_key_file)
    token = sealing.encrypt(s, b"payload")
    key_file = tmp_path / ".key"
    assert key_file.exists()
    key_bytes = key_file.read_bytes()
    assert sealing.decrypt(s, token) == b"payload"
    assert "generated a new hidden-suite encryption key file" in caplog.text
    assert key_bytes.decode() not in caplog.text  # the key itself is never logged


def test_production_without_a_key_refuses(tmp_path):
    s = _settings(tmp_path, app_env="production")
    assert sealing.encryption_available(s) is False
    with pytest.raises(sealing.SealingUnavailableError):
        sealing.get_cipher(s)
    assert not (tmp_path / ".key").exists()  # production never generates a key file


def test_production_with_a_key_works(tmp_path):
    s = _settings(tmp_path, app_env="production", hidden_suite_key=Fernet.generate_key().decode())
    assert sealing.encryption_available(s) is True
    assert sealing.decrypt(s, sealing.encrypt(s, b"x")) == b"x"
