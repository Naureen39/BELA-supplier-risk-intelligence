"""Confidence routing for structured resolution."""

from __future__ import annotations

from app.resolution.config import ResolutionConfig
from app.resolution.models import Route


def route_probabilities(
    top: float, runner_up: float, cfg: ResolutionConfig, degraded: bool = False
) -> Route:
    """Accept, review, or NIL from calibrated probabilities.

    Accept needs the accept threshold and a clear margin over the runner-up. A high top score with
    a small margin goes to review. When a model service was unavailable (`degraded`), automatic
    acceptance is withheld and the record goes to review instead.
    """
    if top < cfg.review_threshold:
        return Route.NIL
    if top >= cfg.accept_threshold and (top - runner_up) >= cfg.min_margin and not degraded:
        return Route.ACCEPTED
    return Route.REVIEW
