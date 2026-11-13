"""EdDSA access tokens and opaque random tokens."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.settings import Settings

ISSUER = "provenance-risk"
AUDIENCE = "provenance-api"


@dataclass(frozen=True)
class AccessClaims:
    user_id: str
    tenant_id: str | None
    role: str
    family_id: str
    jti: str


@dataclass(frozen=True)
class MfaClaims:
    user_id: str
    enroll: bool  # True when the user must enroll before a session is issued


class TokenError(Exception):
    pass


class TokenService:
    def __init__(self, settings: Settings) -> None:
        self._s = settings
        if settings.jwt_private_key_pem:
            key = serialization.load_pem_private_key(settings.jwt_private_key_pem.encode(), None)
            if not isinstance(key, Ed25519PrivateKey):
                raise RuntimeError("JWT_PRIVATE_KEY_PEM must be an Ed25519 key")
            self._private = key
        elif settings.allow_ephemeral_secrets:
            self._private = Ed25519PrivateKey.generate()
        else:
            raise RuntimeError("JWT_PRIVATE_KEY_PEM is required")
        self._public = self._private.public_key()

    def _encode(self, claims: dict[str, object], minutes: int, typ: str) -> str:
        now = datetime.now(UTC)
        body = {**claims, "iss": ISSUER, "aud": AUDIENCE, "typ": typ, "iat": now,
                "nbf": now, "exp": now + timedelta(minutes=minutes), "jti": uuid.uuid4().hex}
        return jwt.encode(body, self._private, algorithm="EdDSA")

    def _decode(self, token: str, typ: str) -> dict[str, object]:
        try:
            claims: dict[str, object] = jwt.decode(
                token, self._public, algorithms=["EdDSA"], audience=AUDIENCE, issuer=ISSUER,
                options={"require": ["exp", "iat", "nbf", "iss", "aud", "sub", "jti"]})
        except jwt.PyJWTError as exc:
            raise TokenError("invalid token") from exc
        if claims.get("typ") != typ:
            raise TokenError("wrong token type")
        return claims

    def issue_access(self, user_id: str, tenant_id: str | None, role: str, family_id: str) -> str:
        return self._encode({"sub": user_id, "tid": tenant_id, "role": role, "fam": family_id},
                            self._s.access_minutes, "access")

    def read_access(self, token: str) -> AccessClaims:
        c = self._decode(token, "access")
        tid = c.get("tid")
        return AccessClaims(str(c["sub"]), str(tid) if tid else None, str(c["role"]),
                            str(c["fam"]), str(c["jti"]))

    def issue_mfa(self, user_id: str, enroll: bool) -> str:
        return self._encode({"sub": user_id, "enroll": enroll}, self._s.mfa_token_minutes, "mfa")

    def read_mfa(self, token: str) -> MfaClaims:
        c = self._decode(token, "mfa")
        return MfaClaims(str(c["sub"]), bool(c.get("enroll")))


def opaque_token() -> tuple[str, str]:
    """(raw value shown once, sha256 hex stored)."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def new_api_key() -> tuple[str, str, str]:
    """(full key shown once, prefix, secret hash). Format: pk_<prefix>_<secret>."""
    prefix = secrets.token_hex(4)
    secret = secrets.token_urlsafe(32)
    return f"pk_{prefix}_{secret}", prefix, hash_token(secret)


def split_api_key(key: str) -> tuple[str, str] | None:
    parts = key.split("_", 2)
    if len(parts) != 3 or parts[0] != "pk" or not parts[1] or not parts[2]:
        return None
    return parts[1], parts[2]
