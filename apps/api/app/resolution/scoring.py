"""Scoring models: Fellegi-Sunter match weights, a logistic combiner, and calibration.

The Fellegi-Sunter scorer follows the model family used by Splink (comparison levels with m and u
probabilities, log2 match weights summed with a prior). It is implemented here with supervised
estimation of m and u from labeled pairs, so the engine runs without the Splink dependency. Splink
itself remains the planned baseline for the evaluation harness; see docs/resolution.md.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from app.resolution.features import FEATURE_NAMES, feature_vector

# --------------------------------------------------------------------- Fellegi-Sunter


def _name_level(f: dict[str, float]) -> int:
    if f["name_exact"] == 1.0:
        return 0
    if f["name_jaro_winkler"] >= 0.95 or f["name_token_sort"] >= 0.95:
        return 1
    if f["name_jaro_winkler"] >= 0.88 or f["name_token_sort"] >= 0.85:
        return 2
    if f["name_token_set"] >= 0.9:
        return 3
    return 4


def _state_level(f: dict[str, float]) -> int:
    return 0 if f["state_agree"] else 1 if f["state_disagree"] else 2


def _city_level(f: dict[str, float]) -> int:
    return 0 if f["city_agree"] else 1 if f["city_disagree"] else 2


def _industry_level(f: dict[str, float]) -> int:
    return 0 if f["industry_agree"] else 1 if f["industry_disagree"] else 2


COMPARISONS: dict[str, tuple[Callable[[dict[str, float]], int], int]] = {
    "name": (_name_level, 5),
    "state": (_state_level, 3),
    "city": (_city_level, 3),
    "industry": (_industry_level, 3),
}

# Priors used before estimation. Estimated values from `FellegiSunter.fit` replace them.
_DEFAULT_M = {
    "name": [0.55, 0.20, 0.12, 0.08, 0.05],
    "state": [0.80, 0.05, 0.15],
    "city": [0.60, 0.10, 0.30],
    "industry": [0.55, 0.15, 0.30],
}
_DEFAULT_U = {
    "name": [0.0005, 0.002, 0.01, 0.03, 0.9575],
    "state": [0.06, 0.64, 0.30],
    "city": [0.01, 0.59, 0.40],
    "industry": [0.10, 0.60, 0.30],
}


@dataclass
class FellegiSunter:
    m: dict[str, list[float]] = field(default_factory=lambda: {k: list(v) for k, v in _DEFAULT_M.items()})
    u: dict[str, list[float]] = field(default_factory=lambda: {k: list(v) for k, v in _DEFAULT_U.items()})
    prior_odds: float = 1 / 50

    def weight(self, features: dict[str, float]) -> float:
        total = math.log2(self.prior_odds)
        for key, (fn, _n) in COMPARISONS.items():
            level = fn(features)
            total += math.log2(self.m[key][level] / self.u[key][level])
        return total

    def probability(self, features: dict[str, float]) -> float:
        w = self.weight(features)
        return float(1.0 / (1.0 + 2.0 ** (-w)))

    def fit(self, pairs: Sequence[tuple[dict[str, float], bool]], smoothing: float = 1.0) -> None:
        """Estimate m (among matches) and u (among non-matches) from labeled candidate pairs."""
        pos = [f for f, y in pairs if y]
        neg = [f for f, y in pairs if not y]
        if not pos or not neg:
            raise ValueError("fit needs both matching and non-matching pairs")
        for key, (fn, n_levels) in COMPARISONS.items():
            for target, rows in ((self.m, pos), (self.u, neg)):
                counts = [smoothing] * n_levels
                for f in rows:
                    counts[fn(f)] += 1
                total = sum(counts)
                target[key] = [c / total for c in counts]
        self.prior_odds = len(pos) / len(neg)

    def to_dict(self) -> dict[str, Any]:
        return {"m": self.m, "u": self.u, "prior_odds": self.prior_odds}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FellegiSunter:
        return cls(m=data["m"], u=data["u"], prior_odds=data["prior_odds"])


# --------------------------------------------------------------------- logistic combiner


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return np.asarray(1.0 / (1.0 + np.exp(-np.clip(z, -35, 35))))


@dataclass
class LogisticCombiner:
    """L2-regularized logistic regression fitted by Newton iterations (IRLS)."""

    names: tuple[str, ...] = FEATURE_NAMES + ("splink_weight",)
    coef: list[float] | None = None
    intercept: float = 0.0
    mean: list[float] | None = None
    scale: list[float] | None = None

    @property
    def fitted(self) -> bool:
        return self.coef is not None

    def fit(self, X: np.ndarray, y: np.ndarray, l2: float = 1.0, iters: int = 50) -> None:
        mean = X.mean(axis=0)
        scale = X.std(axis=0)
        scale[scale < 1e-9] = 1.0
        Z = (X - mean) / scale
        n, d = Z.shape
        w = np.zeros(d)
        b = 0.0
        for _ in range(iters):
            p = _sigmoid(Z @ w + b)
            r = p * (1 - p) + 1e-6
            grad_w = Z.T @ (p - y) + l2 * w
            grad_b = float(np.sum(p - y))
            H = (Z.T * r) @ Z + l2 * np.eye(d)
            hb = float(np.sum(r))
            hwb = Z.T @ r
            full = np.block([[H, hwb[:, None]], [hwb[None, :], np.array([[hb]])]])
            step = np.linalg.solve(full + 1e-9 * np.eye(d + 1), np.concatenate([grad_w, [grad_b]]))
            w -= step[:d]
            b -= float(step[d])
            if np.max(np.abs(step)) < 1e-6:
                break
        self.coef = w.tolist()
        self.intercept = b
        self.mean = mean.tolist()
        self.scale = scale.tolist()

    def predict(self, X: np.ndarray) -> np.ndarray:
        if self.coef is None or self.mean is None or self.scale is None:
            raise RuntimeError("LogisticCombiner is not fitted")
        Z = (X - np.array(self.mean)) / np.array(self.scale)
        return _sigmoid(Z @ np.array(self.coef) + self.intercept)

    def to_dict(self) -> dict[str, Any]:
        return {
            "names": list(self.names), "coef": self.coef, "intercept": self.intercept,
            "mean": self.mean, "scale": self.scale,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LogisticCombiner:
        return cls(
            names=tuple(data["names"]), coef=data["coef"], intercept=data["intercept"],
            mean=data["mean"], scale=data["scale"],
        )


# --------------------------------------------------------------------- calibration


@dataclass
class IsotonicCalibrator:
    """Monotone calibration by pool-adjacent-violators with linear interpolation."""

    xs: list[float] = field(default_factory=list)
    ys: list[float] = field(default_factory=list)

    def fit(self, scores: Sequence[float], labels: Sequence[float]) -> None:
        order = np.argsort(scores)
        s = np.asarray(scores, dtype=float)[order]
        y = np.asarray(labels, dtype=float)[order]
        blocks: list[list[float]] = []  # [sum_y, weight, x_min, x_max]
        for xi, yi in zip(s, y, strict=True):
            blocks.append([yi, 1.0, xi, xi])
            while len(blocks) > 1 and blocks[-2][0] / blocks[-2][1] >= blocks[-1][0] / blocks[-1][1]:
                top = blocks.pop()
                blocks[-1][0] += top[0]
                blocks[-1][1] += top[1]
                blocks[-1][3] = top[3]
        xs: list[float] = []
        ys: list[float] = []
        for sum_y, wgt, lo, hi in blocks:
            val = sum_y / wgt
            xs.extend([lo, hi])
            ys.extend([val, val])
        self.xs, self.ys = xs, ys

    def apply(self, score: float) -> float:
        if not self.xs:
            return score
        return float(np.interp(score, self.xs, self.ys))

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "isotonic", "xs": self.xs, "ys": self.ys}


@dataclass
class PlattCalibrator:
    a: float = 1.0
    b: float = 0.0

    def fit(self, scores: Sequence[float], labels: Sequence[float]) -> None:
        eps = 1e-6
        z = np.log(np.clip(np.asarray(scores), eps, 1 - eps) / (1 - np.clip(np.asarray(scores), eps, 1 - eps)))
        y = np.asarray(labels, dtype=float)
        a, b = 1.0, 0.0
        for _ in range(100):
            p = _sigmoid(a * z + b)
            r = p * (1 - p) + 1e-9
            g = np.array([np.sum((p - y) * z), np.sum(p - y)])
            H = np.array([[np.sum(r * z * z), np.sum(r * z)], [np.sum(r * z), np.sum(r)]])
            step = np.linalg.solve(H + 1e-9 * np.eye(2), g)
            a -= step[0]
            b -= step[1]
            if np.max(np.abs(step)) < 1e-8:
                break
        self.a, self.b = float(a), float(b)

    def apply(self, score: float) -> float:
        s = min(max(score, 1e-6), 1 - 1e-6)
        return float(_sigmoid(np.array([self.a * math.log(s / (1 - s)) + self.b]))[0])

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "platt", "a": self.a, "b": self.b}


Calibrator = IsotonicCalibrator | PlattCalibrator


def calibrator_from_dict(data: dict[str, Any]) -> Calibrator:
    if data["kind"] == "isotonic":
        return IsotonicCalibrator(xs=data["xs"], ys=data["ys"])
    return PlattCalibrator(a=data["a"], b=data["b"])


def expected_calibration_error(
    probs: Sequence[float], labels: Sequence[float], bins: int = 10
) -> float:
    p = np.asarray(probs, dtype=float)
    y = np.asarray(labels, dtype=float)
    edges = np.linspace(0, 1, bins + 1)
    total = 0.0
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        mask = (p >= lo) & (p < hi if hi < 1 else p <= hi)
        if mask.any():
            total += mask.mean() * abs(p[mask].mean() - y[mask].mean())
    return float(total)


def reliability_table(
    probs: Sequence[float], labels: Sequence[float], bins: int = 10
) -> list[dict[str, float]]:
    """Data for reliability plots: per-bin mean predicted probability, observed rate, count."""
    p = np.asarray(probs, dtype=float)
    y = np.asarray(labels, dtype=float)
    edges = np.linspace(0, 1, bins + 1)
    rows = []
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        mask = (p >= lo) & (p < hi if hi < 1 else p <= hi)
        if mask.any():
            rows.append(
                {"bin_low": float(lo), "bin_high": float(hi), "mean_predicted": float(p[mask].mean()),
                 "observed_rate": float(y[mask].mean()), "count": float(mask.sum())}
            )
    return rows


def matrix(rows: Sequence[tuple[dict[str, float], float]]) -> np.ndarray:
    """Stack (features, splink_weight) into the combiner design matrix."""
    return np.array([feature_vector(f) + [w] for f, w in rows], dtype=float)


def dump_json(obj: dict[str, Any]) -> str:
    return json.dumps(obj, indent=2, sort_keys=True)
