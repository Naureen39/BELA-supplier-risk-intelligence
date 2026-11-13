"""SQL for users, MFA, sessions, reset tokens, and API keys (system connection)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

Row = dict[str, Any]


def _one(row: Any) -> Row | None:
    return None if row is None else dict(row)


def user_by_email(conn: Any, email: str) -> Row | None:
    return _one(conn.execute(
        "SELECT u.*, coalesce(t.require_mfa, false) AS tenant_require_mfa "
        "FROM users u LEFT JOIN tenants t ON t.id = u.tenant_id WHERE lower(u.email) = lower(%s)",
        (email,)).fetchone())


def user_by_id(conn: Any, user_id: str) -> Row | None:
    return _one(conn.execute(
        "SELECT u.*, coalesce(t.require_mfa, false) AS tenant_require_mfa "
        "FROM users u LEFT JOIN tenants t ON t.id = u.tenant_id WHERE u.id = %s",
        (user_id,)).fetchone())


def record_failure(conn: Any, user_id: str, locked_until: datetime | None) -> int:
    row = conn.execute(
        "UPDATE users SET failed_logins = failed_logins + 1, locked_until = %s WHERE id = %s "
        "RETURNING failed_logins", (locked_until, user_id)).fetchone()
    return int(row["failed_logins"])


def record_success(conn: Any, user_id: str) -> None:
    conn.execute("UPDATE users SET failed_logins = 0, locked_until = NULL, last_login_at = now() "
                 "WHERE id = %s", (user_id,))


def set_password(conn: Any, user_id: str, password_hash: str) -> None:
    conn.execute("UPDATE users SET password_hash = %s, failed_logins = 0, locked_until = NULL "
                 "WHERE id = %s", (password_hash, user_id))


# ---- MFA
def get_mfa(conn: Any, user_id: str) -> Row | None:
    return _one(conn.execute("SELECT * FROM user_mfa WHERE user_id = %s", (user_id,)).fetchone())


def upsert_pending_mfa(conn: Any, user_id: str, secret_encrypted: bytes, hashes: list[str]) -> None:
    conn.execute(
        "INSERT INTO user_mfa (user_id, secret_encrypted, recovery_code_hashes) VALUES (%s,%s,%s) "
        "ON CONFLICT (user_id) DO UPDATE SET secret_encrypted = EXCLUDED.secret_encrypted, "
        "recovery_code_hashes = EXCLUDED.recovery_code_hashes, confirmed_at = NULL, "
        "last_used_step = NULL WHERE user_mfa.confirmed_at IS NULL",
        (user_id, secret_encrypted, hashes))


def confirm_mfa(conn: Any, user_id: str, step: int) -> None:
    conn.execute("UPDATE user_mfa SET confirmed_at = now(), last_used_step = %s WHERE user_id = %s",
                 (step, user_id))


def set_mfa_step(conn: Any, user_id: str, step: int) -> bool:
    """Advance the last used step atomically; False when another request already used it."""
    row = conn.execute(
        "UPDATE user_mfa SET last_used_step = %s WHERE user_id = %s AND "
        "(last_used_step IS NULL OR last_used_step < %s) RETURNING 1", (step, user_id, step)
    ).fetchone()
    return row is not None


def consume_recovery_code(conn: Any, user_id: str, code_hash: str) -> bool:
    row = conn.execute(
        "UPDATE user_mfa SET recovery_code_hashes = array_remove(recovery_code_hashes, %s) "
        "WHERE user_id = %s AND %s = ANY(recovery_code_hashes) RETURNING 1",
        (code_hash, user_id, code_hash)).fetchone()
    return row is not None


def delete_mfa(conn: Any, user_id: str) -> None:
    conn.execute("DELETE FROM user_mfa WHERE user_id = %s", (user_id,))


# ---- sessions
def insert_refresh(conn: Any, user_id: str, family_id: str, token_hash: str, expires_at: datetime,
                   user_agent: str | None) -> None:
    conn.execute(
        "INSERT INTO refresh_tokens (user_id, family_id, token_hash, expires_at, user_agent) "
        "VALUES (%s,%s,%s,%s,%s)", (user_id, family_id, token_hash, expires_at, (user_agent or "")[:300]))


def refresh_by_hash(conn: Any, token_hash: str) -> Row | None:
    return _one(conn.execute("SELECT * FROM refresh_tokens WHERE token_hash = %s FOR UPDATE",
                        (token_hash,)).fetchone())


def mark_refresh_used(conn: Any, token_id: str) -> None:
    conn.execute("UPDATE refresh_tokens SET used_at = now() WHERE id = %s", (token_id,))


def family_started(conn: Any, family_id: str) -> datetime | None:
    row = conn.execute("SELECT min(created_at) AS started FROM refresh_tokens WHERE family_id = %s",
                       (family_id,)).fetchone()
    return row["started"] if row else None


def revoke_family(conn: Any, family_id: str) -> int:
    return int(conn.execute(
        "UPDATE refresh_tokens SET revoked_at = now() WHERE family_id = %s AND revoked_at IS NULL",
        (family_id,)).rowcount)


def revoke_user_sessions(conn: Any, user_id: str) -> int:
    return int(conn.execute(
        "UPDATE refresh_tokens SET revoked_at = now() WHERE user_id = %s AND revoked_at IS NULL",
        (user_id,)).rowcount)


def family_active(conn: Any, family_id: str, user_id: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM refresh_tokens WHERE family_id = %s AND user_id = %s AND revoked_at IS NULL "
        "LIMIT 1", (family_id, user_id)).fetchone() is not None


def list_sessions(conn: Any, user_id: str) -> list[Row]:
    return list(conn.execute(
        "SELECT family_id, min(created_at) AS started_at, max(created_at) AS last_seen_at, "
        "max(user_agent) AS user_agent, bool_and(revoked_at IS NOT NULL) AS revoked, "
        "max(expires_at) AS expires_at FROM refresh_tokens WHERE user_id = %s "
        "GROUP BY family_id HAVING bool_and(revoked_at IS NULL) AND max(expires_at) > now() "
        "ORDER BY max(created_at) DESC", (user_id,)))


# ---- reset tokens
def insert_reset(conn: Any, user_id: str, token_hash: str, expires_at: datetime) -> None:
    conn.execute("UPDATE password_reset_tokens SET used_at = now() WHERE user_id = %s AND "
                 "used_at IS NULL", (user_id,))
    conn.execute("INSERT INTO password_reset_tokens (user_id, token_hash, expires_at) "
                 "VALUES (%s,%s,%s)", (user_id, token_hash, expires_at))


def consume_reset(conn: Any, token_hash: str) -> str | None:
    row = conn.execute(
        "UPDATE password_reset_tokens SET used_at = now() WHERE token_hash = %s AND used_at IS NULL "
        "AND expires_at > now() RETURNING user_id", (token_hash,)).fetchone()
    return str(row["user_id"]) if row else None


# ---- API keys
def key_by_prefix(conn: Any, prefix: str) -> Row | None:
    return _one(conn.execute("SELECT * FROM api_keys WHERE prefix = %s", (prefix,)).fetchone())


def touch_key(conn: Any, key_id: str) -> None:
    conn.execute("UPDATE api_keys SET last_used_at = now() WHERE id = %s AND "
                 "(last_used_at IS NULL OR last_used_at < now() - interval '1 minute')", (key_id,))
