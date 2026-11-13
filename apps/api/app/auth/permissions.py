"""Role to permission matrix (plan section 10)."""

from __future__ import annotations

from typing import Final

VIEW: Final = "view"  # suppliers, events, alerts, graph
UPLOAD_REVIEW: Final = "upload_review"
ALERT_ACTION: Final = "alert_action"
MANAGE_RULES: Final = "manage_rules"  # alert rules, analytics, reports
MANAGE_USERS: Final = "manage_users"  # users, API keys, risk config
VIEW_AUDIT: Final = "view_audit"
VIEW_REVENUE: Final = "view_revenue"
PLATFORM: Final = "platform"  # tenants, platform settings, platform review queue

ALL_PERMISSIONS: Final = frozenset({VIEW, UPLOAD_REVIEW, ALERT_ACTION, MANAGE_RULES, MANAGE_USERS,
                                    VIEW_AUDIT, VIEW_REVENUE, PLATFORM})

ROLE_PERMISSIONS: Final[dict[str, frozenset[str]]] = {
    "viewer": frozenset({VIEW}),
    "analyst": frozenset({VIEW, UPLOAD_REVIEW, ALERT_ACTION}),
    "manager": frozenset({VIEW, UPLOAD_REVIEW, ALERT_ACTION, MANAGE_RULES}),
    "tenant_admin": frozenset({VIEW, UPLOAD_REVIEW, ALERT_ACTION, MANAGE_RULES, MANAGE_USERS,
                               VIEW_AUDIT}),
    "finance_analyst": frozenset({VIEW_REVENUE}),
    "platform_admin": ALL_PERMISSIONS,
}
ROLES: Final = tuple(ROLE_PERMISSIONS)


def permissions_for(role: str) -> frozenset[str]:
    return ROLE_PERMISSIONS.get(role, frozenset())


# API keys can carry only these scopes; user and platform administration is never delegated.
KEY_SCOPES: Final = frozenset({VIEW, UPLOAD_REVIEW, ALERT_ACTION, MANAGE_RULES})
