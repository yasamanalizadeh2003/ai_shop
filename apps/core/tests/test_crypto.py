import base64
import os

import pytest

from apps.core import crypto


def test_roundtrip():
    token = crypto.encrypt("user@mail.com|secret")
    assert b"secret" not in token
    assert crypto.decrypt(token) == "user@mail.com|secret"


def test_same_plaintext_gives_different_ciphertexts():
    assert crypto.encrypt("x") != crypto.encrypt("x")


def test_tampering_is_detected():
    token = bytearray(crypto.encrypt("hello"))
    token[-1] ^= 1
    with pytest.raises(crypto.DecryptionError):
        crypto.decrypt(bytes(token))


def test_associated_data_must_match():
    token = crypto.encrypt("hello", b"variant:1")
    assert crypto.decrypt(token, b"variant:1") == "hello"
    with pytest.raises(crypto.DecryptionError):
        crypto.decrypt(token, b"variant:2")


def test_wrong_key_cannot_decrypt(settings):
    token = crypto.encrypt("hello")
    settings.FIELD_ENCRYPTION_KEY = base64.b64encode(os.urandom(32)).decode()
    with pytest.raises(crypto.DecryptionError):
        crypto.decrypt(token)


def test_fingerprint_is_stable_and_scoped():
    assert crypto.fingerprint("a  b") == crypto.fingerprint("a b")
    assert crypto.fingerprint("a", "variant:1") != crypto.fingerprint("a", "variant:2")
