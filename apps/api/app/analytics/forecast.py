"""MRR forecast: exponential smoothing (ETS) with an 80 percent prediction interval.

The result is an estimate, not a commitment. A hold-out backtest on the last six observed months
is reported next to it (mean absolute percentage error and how often the interval covered the
actual value), so the reader can judge how much weight the projection deserves.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np
import pandas as pd
from statsmodels.tsa.exponential_smoothing.ets import ETSModel

from app.analytics.common import add_months
from app.core.errors import ApiError

MIN_MONTHS = 12
BACKTEST_MONTHS = 6
LEVEL = 0.80
# (error, trend, damped)
CANDIDATES: tuple[tuple[str, str | None, bool], ...] = (
    ("add", "add", True), ("add", "add", False), ("add", None, False), ("mul", "add", True),
)


@dataclass
class Fit:
    spec: tuple[str, str | None, bool]
    aicc: float
    result: Any

    @property
    def name(self) -> str:
        err, trend, damped = self.spec
        trend_name = "no trend" if trend is None else ("damped additive trend" if damped else "additive trend")
        return f"ETS({err} error, {trend_name})"


def _series(points: list[tuple[date, float]]) -> pd.Series:
    idx = pd.period_range(start=pd.Period(points[0][0], freq="M"), periods=len(points), freq="M")
    return pd.Series([float(v) for _, v in points], index=idx)


def _fit_best(y: pd.Series) -> Fit:
    best: Fit | None = None
    for spec in CANDIDATES:
        err, trend, damped = spec
        if err == "mul" and (y <= 0).any():
            continue
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                res = ETSModel(y, error=err, trend=trend, damped_trend=damped).fit(disp=False)
            if not np.isfinite(res.aicc):
                continue
        except Exception:  # nosec B112
            continue
        if best is None or res.aicc < best.aicc:
            best = Fit(spec, float(res.aicc), res)
    if best is None:
        raise ApiError(422, "The forecast model could not be fitted to this series.", code="forecast")
    return best


def _predict(fit: Fit, steps: int) -> pd.DataFrame:
    n = len(fit.result.fittedvalues)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        frame: pd.DataFrame = fit.result.get_prediction(start=n, end=n + steps - 1).summary_frame(
            alpha=1 - LEVEL)
    return frame


def forecast_mrr(points: list[tuple[date, float]], horizon: int = 6) -> dict[str, Any]:
    if len(points) < MIN_MONTHS:
        raise ApiError(422, f"At least {MIN_MONTHS} months of MRR are needed to forecast.",
                       code="insufficient-history")
    if not 1 <= horizon <= 12:
        raise ApiError(422, "The horizon must be between 1 and 12 months.", code="validation")
    y = _series(points)
    fit = _fit_best(y)
    frame = _predict(fit, horizon)
    last = points[-1][0]
    projection = [
        {"month_start": add_months(last, i + 1).isoformat(),
         "mean": round(max(0.0, float(row["mean"])), 2),
         "lower": round(max(0.0, float(row["pi_lower"])), 2),
         "upper": round(max(0.0, float(row["pi_upper"])), 2)}
        for i, (_, row) in enumerate(frame.iterrows())]

    backtest: dict[str, Any] | None = None
    if len(points) >= MIN_MONTHS + BACKTEST_MONTHS:
        train, actual = y.iloc[:-BACKTEST_MONTHS], y.iloc[-BACKTEST_MONTHS:]
        bt_fit = _fit_best(train)
        bt = _predict(bt_fit, BACKTEST_MONTHS)
        mean = bt["mean"].to_numpy()
        act = actual.to_numpy()
        ape = np.abs(mean - act) / np.where(act == 0, np.nan, act)
        covered = (act >= bt["pi_lower"].to_numpy()) & (act <= bt["pi_upper"].to_numpy())
        backtest = {"months": BACKTEST_MONTHS, "model": bt_fit.name,
                    "mape_pct": round(float(np.nanmean(ape)) * 100, 2),
                    "interval_coverage_pct": round(float(covered.mean()) * 100, 1)}
    return {
        "label": "Estimate", "model": fit.name, "aicc": round(fit.aicc, 2),
        "interval_level_pct": int(LEVEL * 100), "history_months": len(points),
        "history": [{"month_start": d.isoformat(), "mrr": round(v, 2)} for d, v in points],
        "forecast": projection, "backtest": backtest,
        "note": "A statistical projection of past MRR. It does not model pipeline, pricing changes, "
                "or churn events and is not a commitment.",
    }
