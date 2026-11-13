"""Argon2id hashing and the password policy (length plus strength, no composition rules)."""

from __future__ import annotations

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from zxcvbn import zxcvbn

from app.settings import Settings

MIN_LENGTH = 12
MAX_LENGTH = 256
MIN_SCORE = 3
_COMMON = frozenset({
    "password1234", "passwordpassword", "123456789012", "qwertyuiopas", "iloveyou1234",
    "administrator", "welcome12345", "letmein123456", "changeme1234", "password123456",
    "1234567890123", "abcdefghijkl", "qwertyqwerty"})


class PasswordService:
    def __init__(self, settings: Settings) -> None:
        self._hasher = PasswordHasher(
            time_cost=settings.argon_time_cost, memory_cost=settings.argon_memory_kib,
            parallelism=settings.argon_parallelism, type=Type.ID)
        # Verified when the account does not exist, so response time does not reveal accounts.
        self._dummy = self._hasher.hash("dummy-password-for-timing-equalisation")

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, stored_hash: str | None, password: str) -> bool:
        try:
            if stored_hash is None:
                self._hasher.verify(self._dummy, password[:MAX_LENGTH])
                return False
            return self._hasher.verify(stored_hash, password[:MAX_LENGTH])
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    def needs_rehash(self, stored_hash: str) -> bool:
        return self._hasher.check_needs_rehash(stored_hash)

    @staticmethod
    def problems(password: str, user_inputs: list[str] | None = None) -> list[str]:
        out: list[str] = []
        if len(password) < MIN_LENGTH:
            out.append(f"Use at least {MIN_LENGTH} characters.")
        if len(password) > MAX_LENGTH:
            out.append(f"Use at most {MAX_LENGTH} characters.")
            return out
        if password.casefold() in _COMMON:
            out.append("This password is too common.")
        elif len(password) >= MIN_LENGTH:
            result = zxcvbn(password, user_inputs=[u for u in (user_inputs or []) if u])
            if result["score"] < MIN_SCORE:
                hint = result["feedback"].get("warning") or "Choose a less predictable password."
                out.append(hint)
        return out
