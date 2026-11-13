"""Symmetric encryption for MFA secrets, with keys from the environment."""

from __future__ import annotations

import base64
import hashlib
import hmac

from cryptography.fernet import Fernet

from app.settings import Settings


class DataCipher:
    def __init__(self, settings: Settings) -> None:
        key = settings.data_key
        if not key:
            if not settings.allow_ephemeral_secrets:
                raise RuntimeError("DATA_KEY is required")
            key = Fernet.generate_key().decode()
        # Accept any secret string: derive a valid Fernet key deterministically.
        digest = hashlib.sha256(key.encode()).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(digest))
        self._pepper = hashlib.sha256(b"pepper:" + key.encode()).digest()
        self.raw_key = key

    def encrypt(self, data: bytes) -> bytes:
        return self._fernet.encrypt(data)

    def decrypt(self, token: bytes) -> bytes:
        return self._fernet.decrypt(token)

    def keyed_hash(self, value: str) -> str:
        """HMAC for single-use codes stored in the database."""
        return hmac.new(self._pepper, value.encode(), hashlib.sha256).hexdigest()
