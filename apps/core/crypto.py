"""
AES-256-GCM encryption for delivery data, sensitive customer fields and
upstream API keys. The key lives only in the environment (FIELD_ENCRYPTION_KEY).

Token layout: 1 byte key version | 12 byte nonce | ciphertext+tag
"""

import base64
import hashlib
import hmac
import os
from functools import lru_cache

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

KEY_VERSION = 1
_NONCE_SIZE = 12


class DecryptionError(Exception):
    pass


@lru_cache(maxsize=4)
def _key(raw_key: str) -> bytes:
    try:
        key = base64.b64decode(raw_key, validate=True)
    except Exception as exc:
        raise ImproperlyConfigured("FIELD_ENCRYPTION_KEY must be base64.") from exc
    if len(key) != 32:
        raise ImproperlyConfigured("FIELD_ENCRYPTION_KEY must decode to exactly 32 bytes.")
    return key


def _current_key() -> bytes:
    return _key(settings.FIELD_ENCRYPTION_KEY)


def encrypt(plaintext: str, associated_data: bytes = b"") -> bytes:
    nonce = os.urandom(_NONCE_SIZE)
    ciphertext = AESGCM(_current_key()).encrypt(nonce, plaintext.encode("utf-8"), associated_data or None)
    return bytes([KEY_VERSION]) + nonce + ciphertext


def decrypt(token: bytes, associated_data: bytes = b"") -> str:
    token = bytes(token)
    if not token or token[0] != KEY_VERSION:
        raise DecryptionError("Unknown key version.")
    nonce, ciphertext = token[1 : 1 + _NONCE_SIZE], token[1 + _NONCE_SIZE :]
    try:
        return AESGCM(_current_key()).decrypt(nonce, ciphertext, associated_data or None).decode("utf-8")
    except Exception as exc:
        raise DecryptionError("Could not decrypt value.") from exc


def fingerprint(value: str, scope: str = "") -> str:
    """Keyed hash used to detect duplicates without storing plaintext."""
    key = hashlib.sha256(b"fingerprint:" + _current_key()).digest()
    normalized = " ".join(value.split())
    return hmac.new(key, f"{scope}\x00{normalized}".encode("utf-8"), hashlib.sha256).hexdigest()
