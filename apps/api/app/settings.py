"""Application settings from environment variables. Secrets are never committed."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _bool(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str = ""
    valkey_url: str = ""  # empty means in-process rate limiting and pub/sub (single instance only)
    cookie_secure: bool = True
    cookie_domain: str | None = None
    # Token lifetimes
    access_minutes: int = 10
    refresh_idle_minutes: int = 480
    session_absolute_days: int = 30
    mfa_token_minutes: int = 5
    reset_token_minutes: int = 30
    # Secrets (base64 or PEM from the environment; development generates ephemeral ones)
    jwt_private_key_pem: str = ""
    data_key: str = ""  # symmetric key for MFA secrets and identifier columns
    cursor_secret: str = ""
    # Argon2id cost (defaults follow RFC 9106 low-memory profile)
    argon_time_cost: int = 3
    argon_memory_kib: int = 65536
    argon_parallelism: int = 4
    # Login protection
    lock_threshold: int = 5
    lock_base_minutes: int = 1
    lock_max_minutes: int = 60
    # Rate limits: (requests, window seconds)
    ip_limit: tuple[int, int] = (600, 60)
    login_ip_limit: tuple[int, int] = (20, 60)
    login_account_limit: tuple[int, int] = (10, 900)
    user_limit: tuple[int, int] = (300, 60)
    key_limit: tuple[int, int] = (600, 60)
    # Size limits (bytes) and upload row limit
    max_body_bytes: int = 1_000_000
    max_upload_bytes: int = 10_000_000
    max_upload_rows: int = 10_000
    trust_proxy_headers: bool = False
    smtp_host: str = ""
    smtp_port: int = 1025
    mail_from: str = "no-reply@provenance.example"
    web_base_url: str = "https://localhost"
    allow_ephemeral_secrets: bool = True
    mandatory_mfa_roles: frozenset[str] = field(
        default_factory=lambda: frozenset({"tenant_admin", "platform_admin"}))

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            database_url=os.environ.get("DATABASE_URL", ""),
            valkey_url=os.environ.get("VALKEY_URL", ""),
            cookie_secure=_bool("COOKIE_SECURE", True),
            jwt_private_key_pem=os.environ.get("JWT_PRIVATE_KEY_PEM", ""),
            data_key=os.environ.get("DATA_KEY", ""),
            cursor_secret=os.environ.get("CURSOR_SECRET", ""),
            trust_proxy_headers=_bool("TRUST_PROXY_HEADERS", False),
            smtp_host=os.environ.get("SMTP_HOST", ""),
            smtp_port=int(os.environ.get("SMTP_PORT", "1025")),
            web_base_url=os.environ.get("WEB_BASE_URL", "https://localhost"),
            allow_ephemeral_secrets=_bool("ALLOW_EPHEMERAL_SECRETS", False),
        )
