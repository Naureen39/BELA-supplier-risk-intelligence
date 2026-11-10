"""Load and validate the versioned event rules."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

DEFAULT_PATH = Path(__file__).parent / "config" / "event_rules_v1.yaml"


class RulesError(ValueError):
    pass


@dataclass(frozen=True)
class EventRules:
    version: str
    min_year: int
    raw: dict[str, Any]

    def section(self, source: str) -> dict[str, Any]:
        out: dict[str, Any] = self.raw[source]
        return out

    def fields(self, source: str) -> dict[str, str]:
        return {str(k): str(v) for k, v in self.raw[source]["fields"].items()}

    def band(self, source: str, key: str, value: float) -> int:
        """Severity from ascending [threshold, severity] bands: last band whose threshold <= value."""
        severity = 1
        for threshold, sev in self.raw[source][key]:
            if value >= threshold:
                severity = int(sev)
        return severity


def _validate(raw: dict[str, Any]) -> None:
    for key in ("version", "min_year", "epa_echo", "osha", "nhtsa", "cpsc", "openfda"):
        if key not in raw:
            raise RulesError(f"missing section: {key}")
    for source in ("epa_echo", "osha", "nhtsa", "cpsc", "openfda"):
        if not raw[source].get("fields"):
            raise RulesError(f"{source}: no field map")
    for source, key in (("epa_echo", "penalty_bands"), ("osha", "penalty_bands"),
                        ("nhtsa", "units_bands")):
        bands = raw[source][key]
        thresholds = [b[0] for b in bands]
        if thresholds != sorted(thresholds) or any(not 1 <= b[1] <= 4 for b in bands):
            raise RulesError(f"{source}.{key}: thresholds must ascend and severities be 1 to 4")


def load_rules(path: Path = DEFAULT_PATH) -> EventRules:
    raw = yaml.safe_load(path.read_text())
    _validate(raw)
    return EventRules(version=str(raw["version"]), min_year=int(raw["min_year"]), raw=raw)
