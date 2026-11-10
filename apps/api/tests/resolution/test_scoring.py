from __future__ import annotations

import numpy as np
from app.resolution.config import ResolutionConfig
from app.resolution.models import Route
from app.resolution.routing import route_probabilities
from app.resolution.scoring import (
    FellegiSunter,
    IsotonicCalibrator,
    LogisticCombiner,
    PlattCalibrator,
    calibrator_from_dict,
    expected_calibration_error,
)


def test_isotonic_is_monotone_and_reduces_error() -> None:
    rng = np.random.default_rng(0)
    scores = rng.uniform(0, 1, 2000)
    labels = (rng.uniform(0, 1, 2000) < scores**2).astype(float)  # over-confident scores
    cal = IsotonicCalibrator()
    cal.fit(scores, labels)
    mapped = [cal.apply(s) for s in np.sort(scores)]
    assert all(b >= a - 1e-12 for a, b in zip(mapped, mapped[1:], strict=False))
    assert expected_calibration_error(mapped, labels[np.argsort(scores)]) < expected_calibration_error(scores, labels)


def test_platt_roundtrip() -> None:
    rng = np.random.default_rng(1)
    s = rng.uniform(0.05, 0.95, 1500)
    y = (rng.uniform(0, 1, 1500) < s**2).astype(float)
    cal = PlattCalibrator()
    cal.fit(s, y)
    again = calibrator_from_dict(cal.to_dict())
    assert abs(again.apply(0.7) - cal.apply(0.7)) < 1e-12


def test_logistic_separates_linearly_separable_data() -> None:
    rng = np.random.default_rng(2)
    X = rng.normal(size=(400, 3))
    y = (X[:, 0] + 0.5 * X[:, 1] > 0).astype(float)
    m = LogisticCombiner(names=("a", "b", "c"))
    m.fit(X, y)
    assert ((m.predict(X) > 0.5) == (y > 0.5)).mean() > 0.95


def test_fellegi_sunter_fit_prefers_agreeing_pairs() -> None:
    base = {"name_exact": 0.0, "name_jaro_winkler": 0.0, "name_token_sort": 0.0, "name_token_set": 0.0,
            "state_agree": 0.0, "state_disagree": 0.0, "city_agree": 0.0, "city_disagree": 0.0,
            "industry_agree": 0.0, "industry_disagree": 0.0}
    match = {**base, "name_exact": 1.0, "state_agree": 1.0}
    other = {**base, "state_disagree": 1.0}
    fs = FellegiSunter()
    fs.fit([(match, True)] * 50 + [(other, False)] * 200)
    assert fs.probability(match) > 0.9 > 0.1 > fs.probability(other)


def test_routing_thresholds() -> None:
    cfg = ResolutionConfig()
    assert route_probabilities(0.95, 0.30, cfg) is Route.ACCEPTED
    assert route_probabilities(0.95, 0.90, cfg) is Route.REVIEW  # small margin
    assert route_probabilities(0.70, 0.10, cfg) is Route.REVIEW
    assert route_probabilities(0.20, 0.10, cfg) is Route.NIL
    assert route_probabilities(0.99, 0.10, cfg, degraded=True) is Route.REVIEW
