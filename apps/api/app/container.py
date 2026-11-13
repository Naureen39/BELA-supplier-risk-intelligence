"""Dependency container: built once at startup, injected through FastAPI dependencies."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.auth.crypto import DataCipher
from app.auth.passwords import PasswordService
from app.auth.service import AuthService
from app.auth.tokens import TokenService
from app.core.mailer import Mailer, MemoryMailer, SmtpMailer
from app.core.ratelimit import RateLimiter, make_limiter
from app.db import Database
from app.events_bus import Broker, make_broker
from app.settings import Settings


@dataclass
class Container:
    settings: Settings
    db: Database
    limiter: RateLimiter
    broker: Broker
    passwords: PasswordService
    tokens: TokenService
    cipher: DataCipher
    mailer: Mailer
    auth: AuthService
    cursor_secret: bytes
    resolver_cache: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def build(cls, settings: Settings, db: Database | None = None, mailer: Mailer | None = None,
              limiter: RateLimiter | None = None, broker: Broker | None = None) -> Container:
        db = db or Database(settings.database_url)
        passwords = PasswordService(settings)
        tokens = TokenService(settings)
        cipher = DataCipher(settings)
        mail = mailer or (SmtpMailer(settings.smtp_host, settings.smtp_port, settings.mail_from)
                          if settings.smtp_host else MemoryMailer())
        secret = (settings.cursor_secret or cipher.raw_key).encode()
        return cls(settings, db, limiter or make_limiter(settings.valkey_url),
                   broker or make_broker(settings.valkey_url), passwords, tokens, cipher, mail,
                   AuthService(db, settings, passwords, tokens, cipher, mail), secret)
