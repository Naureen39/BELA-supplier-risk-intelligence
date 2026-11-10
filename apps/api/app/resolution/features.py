"""Pairwise features between a query record and a candidate company."""

from __future__ import annotations

from rapidfuzz import fuzz
from rapidfuzz.distance import JaroWinkler

from app.kb.normalize import normalize_name, state_code, token_sort_key
from app.resolution.catalog import CompanyRecord
from app.resolution.models import QueryRecord

FEATURE_NAMES: tuple[str, ...] = (
    "name_exact",
    "name_token_sort",
    "name_token_set",
    "name_jaro_winkler",
    "alias_best",
    "first_token_match",
    "extra_token_ratio",
    "state_agree",
    "state_disagree",
    "city_agree",
    "city_disagree",
    "industry_agree",
    "industry_disagree",
    "country_disagree",
    "retrieval_score",
    "n_sources",
    "blink_available",
    "blink_score",
)


def _best_name_scores(query_norm: str, rec: CompanyRecord) -> tuple[float, float, float, float]:
    """Best (token_sort, token_set, jaro_winkler, exact) over the canonical name and aliases."""
    best_sort = best_set = best_jw = exact = 0.0
    q_sorted = token_sort_key(query_norm)
    for name in rec.all_names():
        norm = normalize_name(name)
        if not norm:
            continue
        best_sort = max(best_sort, fuzz.ratio(q_sorted, token_sort_key(norm)) / 100.0)
        best_set = max(best_set, fuzz.token_set_ratio(query_norm, norm) / 100.0)
        best_jw = max(best_jw, JaroWinkler.similarity(query_norm, norm))
        if query_norm == norm:
            exact = 1.0
    return best_sort, best_set, best_jw, exact


def pair_features(
    query: QueryRecord,
    rec: CompanyRecord,
    retrieval_score: float,
    n_sources: int,
    blink_score: float | None,
) -> dict[str, float]:
    q_norm = normalize_name(query.name)
    sort_s, set_s, jw_s, exact = _best_name_scores(q_norm, rec)
    canon_norm = rec.normalized
    alias_best = max(
        (fuzz.ratio(q_norm, normalize_name(a)) / 100.0 for a in rec.aliases), default=0.0
    )
    q_tokens, c_tokens = q_norm.split(), canon_norm.split()
    first = 1.0 if q_tokens and c_tokens and q_tokens[0] == c_tokens[0] else 0.0
    extra = len(set(q_tokens) ^ set(c_tokens)) / max(len(set(q_tokens) | set(c_tokens)), 1)

    q_state = state_code(query.state)
    c_state = state_code(rec.hq_state)
    state_known = bool(q_state and c_state)
    q_city = normalize_name(query.city) if query.city else ""
    c_city = normalize_name(rec.hq_city) if rec.hq_city else ""
    city_known = bool(q_city and c_city)
    q_ind = (query.industry_code or "")[:2]
    c_ind = (rec.sic_code or "")[:2]
    ind_known = bool(q_ind and c_ind)
    country_known = bool(query.country and rec.hq_country)

    return {
        "name_exact": exact,
        "name_token_sort": sort_s,
        "name_token_set": set_s,
        "name_jaro_winkler": jw_s,
        "alias_best": alias_best,
        "first_token_match": first,
        "extra_token_ratio": extra,
        "state_agree": float(state_known and q_state == c_state),
        "state_disagree": float(state_known and q_state != c_state),
        "city_agree": float(city_known and q_city == c_city),
        "city_disagree": float(city_known and q_city != c_city),
        "industry_agree": float(ind_known and q_ind == c_ind),
        "industry_disagree": float(ind_known and q_ind != c_ind),
        "country_disagree": float(
            country_known and (query.country or "").upper() != (rec.hq_country or "").upper()
        ),
        "retrieval_score": retrieval_score,
        "n_sources": float(n_sources),
        "blink_available": float(blink_score is not None),
        "blink_score": blink_score if blink_score is not None else 0.0,
    }


def feature_vector(features: dict[str, float]) -> list[float]:
    return [features.get(name, 0.0) for name in FEATURE_NAMES]
