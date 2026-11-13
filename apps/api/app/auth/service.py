"""Authentication workflows: login, MFA, sessions with rotation and reuse detection, resets."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.auth import mfa
from app.auth.crypto import DataCipher
from app.auth.passwords import PasswordService
from app.auth.tokens import MfaClaims, TokenError, TokenService, hash_token, opaque_token
from app.core import audit
from app.core.errors import ApiError
from app.core.mailer import Mailer
from app.db import Database
from app.repo import auth as repo
from app.settings import Settings


def _invalid() -> ApiError:
    return ApiError(401, "Invalid credentials.", code="invalid-credentials")


@dataclass(frozen=True)
class SessionTokens:
    access: str
    refresh: str
    family_id: str
    user: dict[str, Any]


@dataclass(frozen=True)
class LoginOutcome:
    status: str  # session, mfa_required, mfa_enrollment_required
    tokens: SessionTokens | None = None
    mfa_token: str | None = None


class AuthService:
    def __init__(self, db: Database, settings: Settings, passwords: PasswordService,
                 tokens: TokenService, cipher: DataCipher, mailer: Mailer) -> None:
        self.db, self.s, self.passwords = db, settings, passwords
        self.tokens, self.cipher, self.mailer = tokens, cipher, mailer

    # ------------------------------------------------------------------ login
    def login(self, email: str, password: str, ip: str, user_agent: str | None) -> LoginOutcome:
        now = datetime.now(UTC)
        failure: str | None = None
        user: dict[str, Any] | None = None
        outcome: LoginOutcome | None = None
        with self.db.system() as conn:
            user = repo.user_by_email(conn, email)
            locked = bool(user and user["locked_until"] and user["locked_until"] > now)
            ok = self.passwords.verify(user["password_hash"] if user else None, password)
            if not user:
                failure = "unknown_account"
            elif locked:
                failure = "locked"
            elif not user["is_active"]:
                failure = "inactive"
            elif not ok:
                failure = "bad_password"
                n = int(user["failed_logins"]) + 1
                until = None
                if n >= self.s.lock_threshold:
                    minutes = min(self.s.lock_base_minutes * 2 ** (n - self.s.lock_threshold),
                                  self.s.lock_max_minutes)
                    until = now + timedelta(minutes=minutes)
                repo.record_failure(conn, str(user["id"]), until)
            else:
                outcome = self._after_password(conn, user, password, user_agent)
        if failure or outcome is None or user is None:
            audit.record(self.db, action="auth.login_failed",
                         tenant_id=str(user["tenant_id"]) if user and user["tenant_id"] else None,
                         actor=str(user["id"]) if user else None,
                         detail={"reason": failure, "ip": ip})
            raise _invalid()
        audit.record(self.db, action="auth.login" if outcome.status == "session" else "auth.login_mfa_step",
                     tenant_id=str(user["tenant_id"]) if user["tenant_id"] else None,
                     actor=str(user["id"]), detail={"ip": ip, "step": outcome.status})
        return outcome

    def _after_password(self, conn: Any, user: dict[str, Any], password: str, ua: str | None) -> LoginOutcome:
        uid = str(user["id"])
        if self.passwords.needs_rehash(user["password_hash"]):
            repo.set_password(conn, uid, self.passwords.hash(password))
        m = repo.get_mfa(conn, uid)
        if m and m["confirmed_at"]:
            return LoginOutcome("mfa_required", mfa_token=self.tokens.issue_mfa(uid, False))
        if user["role"] in self.s.mandatory_mfa_roles or user["tenant_require_mfa"]:
            return LoginOutcome("mfa_enrollment_required", mfa_token=self.tokens.issue_mfa(uid, True))
        repo.record_success(conn, uid)
        return LoginOutcome("session", tokens=self._start_session(conn, user, None, ua))

    # ------------------------------------------------------------------ sessions
    def _start_session(self, conn: Any, user: dict[str, Any], family: str | None,
                       ua: str | None, started: datetime | None = None) -> SessionTokens:
        import uuid

        now = datetime.now(UTC)
        family_id = family or str(uuid.uuid4())
        started = started or now
        raw, digest = opaque_token()
        expires = min(now + timedelta(minutes=self.s.refresh_idle_minutes),
                      started + timedelta(days=self.s.session_absolute_days))
        repo.insert_refresh(conn, str(user["id"]), family_id, digest, expires, ua)
        access = self.tokens.issue_access(str(user["id"]),
                                          str(user["tenant_id"]) if user["tenant_id"] else None,
                                          user["role"], family_id)
        return SessionTokens(access, raw, family_id, user)

    def refresh(self, raw: str, ua: str | None) -> SessionTokens:
        error: ApiError | None = None
        reuse: dict[str, str] | None = None
        result: SessionTokens | None = None
        with self.db.system() as conn:
            row = repo.refresh_by_hash(conn, hash_token(raw))
            now = datetime.now(UTC)
            if row is None or row["revoked_at"] is not None:
                error = ApiError(401, "The session is no longer valid.", code="session-invalid")
            elif row["used_at"] is not None:
                repo.revoke_family(conn, str(row["family_id"]))
                reuse = {"user": str(row["user_id"]), "family": str(row["family_id"])}
                error = ApiError(401, "The session is no longer valid.", code="session-invalid")
            elif row["expires_at"] <= now:
                error = ApiError(401, "The session has expired.", code="session-expired")
            else:
                user = repo.user_by_id(conn, str(row["user_id"]))
                started = repo.family_started(conn, str(row["family_id"])) or now
                if not user or not user["is_active"]:
                    repo.revoke_family(conn, str(row["family_id"]))
                    error = ApiError(401, "The session is no longer valid.", code="session-invalid")
                elif now > started + timedelta(days=self.s.session_absolute_days):
                    repo.revoke_family(conn, str(row["family_id"]))
                    error = ApiError(401, "The session has expired.", code="session-expired")
                else:
                    repo.mark_refresh_used(conn, str(row["id"]))
                    result = self._start_session(conn, user, str(row["family_id"]), ua, started)
        if reuse:
            audit.record(self.db, action="auth.refresh_reuse_detected", actor=reuse["user"],
                         target_type="session", target_id=reuse["family"])
        if error or result is None:
            raise error or ApiError(401, "The session is no longer valid.", code="session-invalid")
        return result

    def logout(self, family_id: str, user_id: str, tenant_id: str | None) -> None:
        with self.db.system() as conn:
            repo.revoke_family(conn, family_id)
        audit.record(self.db, action="auth.logout", tenant_id=tenant_id, actor=user_id,
                     target_type="session", target_id=family_id)

    # ------------------------------------------------------------------ MFA
    def setup_mfa(self, user_id: str) -> dict[str, Any]:
        with self.db.system() as conn:
            user = repo.user_by_id(conn, user_id)
            existing = repo.get_mfa(conn, user_id)
            if not user:
                raise _invalid()
            if existing and existing["confirmed_at"]:
                raise ApiError(409, "Multi-factor authentication is already enabled.",
                               code="mfa-enabled")
            secret = mfa.new_secret()
            codes, hashes = mfa.new_recovery_codes(self.cipher)
            repo.upsert_pending_mfa(conn, user_id, self.cipher.encrypt(secret.encode()), hashes)
        audit.record(self.db, action="auth.mfa_setup_started", actor=user_id,
                     tenant_id=str(user["tenant_id"]) if user["tenant_id"] else None)
        return {"secret": secret, "otpauth_uri": mfa.provisioning_uri(secret, user["email"]),
                "recovery_codes": codes}

    def verify_mfa(self, user_id: str, code: str | None, recovery_code: str | None,
                   ua: str | None, issue_session: bool) -> SessionTokens | None:
        """Verify a TOTP or recovery code. Confirms enrollment when the secret is pending."""
        ok = False
        user: dict[str, Any] | None = None
        session: SessionTokens | None = None
        used_recovery = False
        with self.db.system() as conn:
            user = repo.user_by_id(conn, user_id)
            row = repo.get_mfa(conn, user_id)
            if user and user["is_active"] and row:
                if recovery_code and row["confirmed_at"]:
                    h = self.cipher.keyed_hash(mfa.normalize_code(recovery_code))
                    ok = used_recovery = repo.consume_recovery_code(conn, user_id, h)
                elif code:
                    secret = self.cipher.decrypt(bytes(row["secret_encrypted"])).decode()
                    step = mfa.verify_totp(secret, code, row["last_used_step"])
                    if step is not None:
                        if row["confirmed_at"]:
                            ok = repo.set_mfa_step(conn, user_id, step)
                        else:
                            repo.confirm_mfa(conn, user_id, step)
                            ok = True
            if ok and user and issue_session:
                repo.record_success(conn, user_id)
                session = self._start_session(conn, user, None, ua)
        tenant = str(user["tenant_id"]) if user and user["tenant_id"] else None
        if not ok:
            audit.record(self.db, action="auth.mfa_failed", actor=user_id, tenant_id=tenant)
            raise ApiError(401, "The verification code is not valid.", code="mfa-invalid")
        audit.record(self.db, action="auth.mfa_recovery_used" if used_recovery else "auth.mfa_verified",
                     actor=user_id, tenant_id=tenant)
        return session

    def read_mfa_token(self, token: str) -> MfaClaims:
        try:
            return self.tokens.read_mfa(token)
        except TokenError as exc:
            raise ApiError(401, "The verification step has expired. Sign in again.",
                           code="mfa-token-invalid") from exc

    # ------------------------------------------------------------------ password reset
    def forgot_password(self, email: str) -> None:
        raw: str | None = None
        user: dict[str, Any] | None = None
        with self.db.system() as conn:
            user = repo.user_by_email(conn, email)
            if user and user["is_active"]:
                raw, digest = opaque_token()
                repo.insert_reset(conn, str(user["id"]), digest,
                                  datetime.now(UTC) + timedelta(minutes=self.s.reset_token_minutes))
        if user and raw:
            link = f"{self.s.web_base_url}/reset-password?token={raw}"
            self.mailer.send(user["email"], "Reset your password",
                             f"Use this link within {self.s.reset_token_minutes} minutes: {link}\n"
                             "If you did not request this, you can ignore this message.")
            audit.record(self.db, action="auth.password_reset_requested", actor=str(user["id"]),
                         tenant_id=str(user["tenant_id"]) if user["tenant_id"] else None)

    def reset_password(self, raw_token: str, new_password: str) -> None:
        with self.db.system() as conn:
            peek = conn.execute(
                "SELECT t.user_id, u.email, u.tenant_id FROM password_reset_tokens t "
                "JOIN users u ON u.id = t.user_id WHERE t.token_hash = %s AND t.used_at IS NULL "
                "AND t.expires_at > now()", (hash_token(raw_token),)).fetchone()
            if not peek:
                raise ApiError(400, "The reset link is invalid or has expired.", code="reset-invalid")
            problems = self.passwords.problems(new_password, [peek["email"].split("@")[0]])
            if problems:
                raise ApiError(422, " ".join(problems), code="weak-password")
            uid = repo.consume_reset(conn, hash_token(raw_token))
            if uid is None:
                raise ApiError(400, "The reset link is invalid or has expired.", code="reset-invalid")
            repo.set_password(conn, uid, self.passwords.hash(new_password))
            repo.revoke_user_sessions(conn, uid)
        audit.record(self.db, action="auth.password_reset", actor=uid,
                     tenant_id=str(peek["tenant_id"]) if peek["tenant_id"] else None)

