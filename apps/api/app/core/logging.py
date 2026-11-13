"""Structured JSON logging with redaction of secrets and identifiers."""

from __future__ import annotations

import logging
import re
from collections.abc import MutableMapping
from typing import Any

import structlog

_SENSITIVE = re.compile(r"pass(word)?|token|secret|authorization|cookie|api[_-]?key|tax|account|code",
                        re.IGNORECASE)


def redact(_logger: Any, _name: str, event: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    for key in list(event):
        if _SENSITIVE.search(key):
            event[key] = "[redacted]"
    return event


def configure_logging(level: int = logging.INFO) -> None:
    structlog.configure(
        processors=[structlog.processors.add_log_level, structlog.processors.TimeStamper(fmt="iso"),
                    redact, structlog.processors.JSONRenderer()],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=False)
