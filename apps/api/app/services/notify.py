"""Alert notifications: in-app (the alert and live stream), email, and webhook with SSRF checks."""

from __future__ import annotations

import ipaddress
import socket
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

import httpx
import structlog

from app.container import Container

log = structlog.get_logger()
MANAGER_ROLES = ("manager", "tenant_admin")


class UnsafeUrl(ValueError):
    pass


def assert_public_https(url: str) -> None:
    """Reject non-https URLs and hosts that resolve to private, loopback, or reserved addresses."""
    parts = urlparse(url)
    if parts.scheme != "https" or not parts.hostname:
        raise UnsafeUrl("webhook URLs must use https")
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnsafeUrl("the host does not resolve") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                or ip.is_multicast or ip.is_unspecified):
            raise UnsafeUrl("the host resolves to a non-public address")


class Notifier:
    def __init__(self, c: Container, http: httpx.Client | None = None,
                 url_check: Callable[[str], None] = assert_public_https,
                 sleep: Callable[[float], None] = time.sleep, attempts: int = 3) -> None:
        self.c, self._url_check, self._sleep, self._attempts = c, url_check, sleep, attempts
        self._http = http or httpx.Client(timeout=c.settings.webhook_timeout, follow_redirects=False)

    def _log(self, conn: Any, alert_id: str, rule_id: str | None, channel: str, status: str,
             detail: str | None = None) -> None:
        conn.execute("INSERT INTO alert_deliveries (alert_id, rule_id, channel, status, detail) "
                     "VALUES (%s,%s,%s,%s,%s)", (alert_id, rule_id, channel, status, (detail or "")[:300]))

    def dispatch(self, tenant_id: str, alert_ids: list[str]) -> None:
        if not alert_ids:
            return
        with self.c.db.system() as conn:
            alerts = conn.execute(
                "SELECT a.id, a.kind, a.detail, a.created_at, a.rule_id, s.uploaded_name FROM alerts a "
                "JOIN suppliers s ON s.id = a.supplier_id WHERE a.id = ANY(%s) AND a.tenant_id = %s",
                (alert_ids, tenant_id)).fetchall()
            rules = {str(r["id"]): r for r in conn.execute(
                "SELECT id, channels, webhook_url FROM alert_rules WHERE tenant_id = %s", (tenant_id,))}
            recipients = [r["email"] for r in conn.execute(
                "SELECT email FROM users WHERE tenant_id = %s AND is_active AND role = ANY(%s)",
                (tenant_id, list(MANAGER_ROLES))).fetchall()]
            for a in alerts:
                rule = rules.get(str(a["rule_id"])) if a["rule_id"] else None
                channels = list(rule["channels"]) if rule else ["in_app"]
                rid = str(a["rule_id"]) if a["rule_id"] else None
                for ch in channels:
                    if ch == "in_app":
                        self._log(conn, str(a["id"]), rid, ch, "sent", "alert queue and live stream")
                    elif ch == "email":
                        self._email(conn, a, rid, recipients)
                    elif ch == "webhook":
                        self._webhook(conn, a, rid, rule["webhook_url"] if rule else None)

    def _email(self, conn: Any, a: dict[str, Any], rid: str | None, recipients: list[str]) -> None:
        if not recipients:
            self._log(conn, str(a["id"]), rid, "email", "skipped", "no recipients")
            return
        body = (f"A new alert was raised for the supplier {a['uploaded_name']}.\n{a['detail']}\n\n"
                f"Review it at {self.c.settings.web_base_url}/app/alerts\n\n"
                "Risk signals are leads for human review and not statements of fault.")
        try:
            for to in recipients:
                self.c.mailer.send(to, "New supplier risk alert", body)
            self._log(conn, str(a["id"]), rid, "email", "sent", f"{len(recipients)} recipients")
        except Exception as exc:
            self._log(conn, str(a["id"]), rid, "email", "failed", type(exc).__name__)

    def _webhook(self, conn: Any, a: dict[str, Any], rid: str | None, url: str | None) -> None:
        if not url:
            self._log(conn, str(a["id"]), rid, "webhook", "skipped", "no URL configured")
            return
        try:
            self._url_check(url)
        except UnsafeUrl as exc:
            self._log(conn, str(a["id"]), rid, "webhook", "failed", f"blocked: {exc}")
            return
        payload = {"alert_id": str(a["id"]), "kind": a["kind"], "supplier": a["uploaded_name"],
                   "detail": a["detail"], "created_at": a["created_at"].isoformat(),
                   "link": f"{self.c.settings.web_base_url}/app/alerts",
                   "notice": "Risk signals are leads for human review and not statements of fault."}
        last = ""
        for attempt in range(self._attempts):
            try:
                r = self._http.post(url, json=payload)
                if r.status_code < 300:
                    self._log(conn, str(a["id"]), rid, "webhook", "sent", f"status {r.status_code}")
                    return
                last = f"status {r.status_code}"
                if r.status_code < 500:
                    break  # client errors are not retried
            except httpx.HTTPError as exc:
                last = type(exc).__name__
            if attempt + 1 < self._attempts:
                self._sleep(0.5 * 2**attempt)
        self._log(conn, str(a["id"]), rid, "webhook", "failed", last)
