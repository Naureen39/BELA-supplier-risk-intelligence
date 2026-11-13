"""Tenant risk configuration versions (stored in risk_configs, defaults from the library)."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.events.risk import DEFAULT_RISK_CONFIG, RiskConfig


def _config_from(data: dict[str, Any]) -> RiskConfig:
    fields: dict[str, Any] = {
        k: (tuple(v) if k in ("severity_weights", "level_thresholds") else v)
        for k, v in data.items() if k != "version"}
    cfg = replace(DEFAULT_RISK_CONFIG, **fields)
    return replace(cfg, version=data.get("version", cfg.version))


def current_risk_config(conn: Any) -> tuple[int, RiskConfig]:
    row = conn.execute("SELECT version, config FROM risk_configs ORDER BY version DESC LIMIT 1"
                       ).fetchone()
    if not row:
        return 1, DEFAULT_RISK_CONFIG
    return int(row["version"]), _config_from(row["config"])
