"""Review decisions: side-by-side comparison, decision application, and opt-in training feedback."""

from __future__ import annotations

import json
from typing import Any

from rapidfuzz import fuzz

from app.container import Container
from app.core.errors import ApiError
from app.kb.normalize import normalize_name, state_code

ACTIONS = ("accept", "reject", "choose_other", "mark_unresolved", "not_in_database")


def _agree(a: Any, b: Any) -> str:
    if a in (None, "") or b in (None, "", []):
        return "unknown"
    return "match" if a == b else "mismatch"


def compare(attrs: dict[str, Any], name: str, cand: dict[str, Any]) -> dict[str, Any]:
    """Field-by-field agreement between the uploaded record and one candidate."""
    d = cand.get("details") or {}
    up_state, c_state = state_code(attrs.get("state")), state_code(d.get("hq_state"))
    up_city, c_city = attrs.get("city"), d.get("hq_city")
    return {
        "name": {"uploaded": name, "candidate": cand["name"],
                 "similarity": round(fuzz.token_sort_ratio(normalize_name(name), normalize_name(cand["name"])) / 100, 3)},
        "state": {"uploaded": attrs.get("state"), "candidate": d.get("hq_state"),
                  "agreement": _agree(up_state, c_state)},
        "city": {"uploaded": up_city, "candidate": c_city,
                 "agreement": _agree(normalize_name(up_city) if up_city else None,
                                     normalize_name(c_city) if c_city else None)},
        "country": {"uploaded": attrs.get("country"), "candidate": d.get("hq_country"),
                    "agreement": _agree((attrs.get("country") or "").upper() or None,
                                        (d.get("hq_country") or "").upper() or None)},
        "cik": {"uploaded": attrs.get("cik"), "candidate": d.get("cik"),
                "agreement": _agree(str(attrs.get("cik") or "") or None, str(d.get("cik") or "") or None)},
        "lei": {"uploaded": attrs.get("lei"), "candidate": d.get("lei"),
                "agreement": _agree((attrs.get("lei") or "").upper() or None, (d.get("lei") or "").upper() or None)},
        "ticker": {"uploaded": attrs.get("ticker"), "candidate": d.get("tickers"),
                   "agreement": "unknown" if not attrs.get("ticker") or not d.get("tickers")
                   else ("match" if attrs["ticker"].upper() in [t.upper() for t in d["tickers"]] else "mismatch")},
        "parent": {"candidate": d.get("parent_name")},
        "industry": {"candidate": d.get("industry") or d.get("sic_code")},
    }


def apply_decision(conn: Any, c: Container, tenant_id: str, user_id: str | None, review: dict[str, Any],
                   action: str, company_id: int | None) -> int | None:
    """Apply one decision inside the caller's transaction. Returns the chosen company id."""
    if review["status"] != "open":
        raise ApiError(409, "This review has already been decided.", code="conflict")
    cands = review["candidates"] or []
    chosen: int | None = None
    if action == "accept":
        if not cands:
            raise ApiError(409, "There is no candidate to accept.", code="conflict")
        chosen = int(cands[0]["company_id"])
    elif action == "choose_other":
        if company_id is None or not conn.execute("SELECT 1 FROM companies WHERE id = %s",
                                                  (company_id,)).fetchone():
            raise ApiError(422, "Choose an existing company.", code="validation")
        chosen = company_id
    status = {"accept": "accepted", "choose_other": "chose_other", "reject": "rejected",
              "mark_unresolved": "unresolved", "not_in_database": "unresolved"}[action]
    conn.execute("UPDATE resolution_reviews SET status = %s, chosen_company_id = %s, reviewer_id = %s, "
                 "decided_at = now() WHERE id = %s", (status, chosen, user_id, review["id"]))
    conn.execute(
        "UPDATE suppliers SET status = %s, resolved_company_id = %s, confidence = %s, "
        "resolution_detail = resolution_detail || %s::jsonb WHERE id = %s",
        ("resolved" if chosen else "unresolved", chosen, 1.0 if chosen else 0.0,
         json.dumps({"human_decision": action, "not_in_database": action == "not_in_database"}),
         review["supplier_id"]))
    _feedback(conn, c, tenant_id, review, action, chosen)
    return chosen


def _feedback(conn: Any, c: Container, tenant_id: str, review: dict[str, Any], action: str,
              chosen: int | None) -> None:
    """Store a labeled example only when the tenant opted in, without any tenant identifier."""
    row = conn.execute("SELECT share_feedback_for_training AS opt FROM tenants WHERE id = %s",
                       (tenant_id,)).fetchone()
    if not row or not row["opt"]:
        return
    sup = conn.execute("SELECT uploaded_name, attributes FROM suppliers WHERE id = %s",
                       (review["supplier_id"],)).fetchone()
    attrs = {k: v for k, v in (sup["attributes"] or {}).items()
             if k in ("state", "city", "country", "address", "website")}
    label = "match" if chosen else ("nil" if action in ("reject", "not_in_database") else "unsure")
    cands = [{"company_id": x["company_id"], "name": x["name"], "probability": x["probability"]}
             for x in (review["candidates"] or [])]
    with c.db.system() as sconn:
        sconn.execute("INSERT INTO training_feedback (query, candidates, label, label_company_id) "
                      "VALUES (%s::jsonb,%s::jsonb,%s,%s)",
                      (json.dumps({"name": sup["uploaded_name"], **attrs}), json.dumps(cands), label, chosen))
