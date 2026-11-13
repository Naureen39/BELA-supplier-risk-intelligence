"""TOTP enrollment and verification, and single-use recovery codes."""

from __future__ import annotations

import hmac
import secrets
import time

import pyotp

from app.auth.crypto import DataCipher

ISSUER = "Provenance Risk"
PERIOD = 30
RECOVERY_COUNT = 10
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def new_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret, interval=PERIOD).provisioning_uri(name=email, issuer_name=ISSUER)


def verify_totp(secret: str, code: str, last_used_step: int | None, now: float | None = None
                ) -> int | None:
    """Return the matched time step, or None. A step at or below the last used one is rejected
    (replay protection). One step of clock drift is allowed in either direction."""
    code = code.strip().replace(" ", "")
    if not (code.isdigit() and len(code) == 6):
        return None
    totp = pyotp.TOTP(secret, interval=PERIOD)
    current = int((now if now is not None else time.time()) // PERIOD)
    for step in (current - 1, current, current + 1):
        if hmac.compare_digest(totp.at(step * PERIOD), code):
            if last_used_step is not None and step <= last_used_step:
                return None
            return step
    return None


def new_recovery_codes(cipher: DataCipher) -> tuple[list[str], list[str]]:
    """(codes shown once, hashes stored). Each code carries 80 bits of entropy."""
    codes = []
    for _ in range(RECOVERY_COUNT):
        raw = "".join(secrets.choice(_ALPHABET) for _ in range(16))
        codes.append("-".join(raw[i : i + 4] for i in range(0, 16, 4)))
    return codes, [cipher.keyed_hash(normalize_code(c)) for c in codes]


def normalize_code(code: str) -> str:
    return code.replace("-", "").replace(" ", "").upper()
