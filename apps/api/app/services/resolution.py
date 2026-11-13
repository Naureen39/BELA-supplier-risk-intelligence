"""Resolution service for the API: catalog loading, single-record resolution, upload processing."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any

from app.container import Container
from app.resolution.catalog import Catalog, load_catalog
from app.resolution.fitting import load_models
from app.resolution.models import QueryRecord, Resolution, Route
from app.resolution.structured import Resolver

FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "name": ("name", "supplier", "supplier_name", "vendor", "vendor_name", "company", "company_name"),
    "state": ("state", "province", "region"),
    "city": ("city", "town"),
    "country": ("country", "country_code"),
    "address": ("address", "street", "street_address"),
    "website": ("website", "url", "domain"),
    "cik": ("cik",), "lei": ("lei",), "ticker": ("ticker", "symbol"),
    "tax_id": ("tax_id", "ein", "tin", "vat"), "account_number": ("account_number", "account"),
    "tier": ("tier", "criticality"),
}
SENSITIVE = ("tax_id", "account_number")
MAX_CELL = 500


def get_resolver(c: Container) -> Resolver:
    """Resolver over the canonical catalog, loaded once and cached until `invalidate`."""
    cached = c.resolver_cache.get("resolver")
    if cached is not None:
        return cached  # type: ignore[no-any-return]
    with c.db.system() as conn:
        catalog = load_catalog(conn)
    models = Path(c.settings.__dict__.get("models_dir", "models/scoring")) / "scoring_models.json"
    resolver = load_models(catalog, models) if models.exists() else Resolver(catalog)
    c.resolver_cache["resolver"] = resolver
    return resolver


def invalidate(c: Container) -> None:
    c.resolver_cache.pop("resolver", None)


def detect_mapping(header: list[str], explicit: dict[str, str] | None) -> dict[str, str]:
    """Map logical fields to CSV column names. Explicit mapping wins over auto detection."""
    lowered = {h.strip().lower().replace(" ", "_"): h for h in header}
    mapping: dict[str, str] = {}
    for logical, aliases in FIELD_ALIASES.items():
        for a in aliases:
            if a in lowered:
                mapping[logical] = lowered[a]
                break
    for logical, column in (explicit or {}).items():
        if logical in FIELD_ALIASES and column in header:
            mapping[logical] = column
    return mapping


class UploadError(ValueError):
    pass


def parse_csv(raw: bytes, explicit: dict[str, str] | None, max_rows: int
              ) -> tuple[list[dict[str, str | None]], list[dict[str, Any]], dict[str, str]]:
    """Return (rows as logical fields, row errors, mapping). Raises UploadError for fatal problems."""
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise UploadError("The file is not valid UTF-8 text.") from exc
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise UploadError("The file has no header row.")
    mapping = detect_mapping(list(reader.fieldnames), explicit)
    if "name" not in mapping:
        raise UploadError("No supplier name column was found. Provide a column mapping.")
    rows: list[dict[str, str | None]] = []
    errors: list[dict[str, Any]] = []
    for i, raw_row in enumerate(reader, start=2):  # row 1 is the header
        if len(rows) + len(errors) >= max_rows:
            raise UploadError(f"The file has more than {max_rows} rows.")
        row = {k: ((raw_row.get(col) or "").strip()[:MAX_CELL] or None) for k, col in mapping.items()}
        if not row.get("name"):
            errors.append({"row": i, "reason": "missing supplier name"})
            continue
        rows.append(row)
    if not rows and not errors:
        raise UploadError("The file has no data rows.")
    return rows, errors, mapping


def to_query(row_id: str, attrs: dict[str, Any]) -> QueryRecord:
    def num(v: Any) -> int | None:
        return int(v) if isinstance(v, str) and v.strip().isdigit() else None

    return QueryRecord(id=row_id, name=str(attrs.get("name") or ""), state=attrs.get("state"),
                       city=attrs.get("city"), country=attrs.get("country"),
                       address=attrs.get("address"), website=attrs.get("website"),
                       cik=num(attrs.get("cik")), lei=attrs.get("lei"), ticker=attrs.get("ticker"))


def candidate_details(catalog: Catalog, company_id: int) -> dict[str, Any]:
    rec = catalog.by_id[company_id]
    return {"aliases": list(rec.aliases[:5]), "hq_city": rec.hq_city, "hq_state": rec.hq_state,
            "hq_country": rec.hq_country, "cik": rec.cik, "lei": rec.lei, "tickers": list(rec.tickers),
            "sic_code": rec.sic_code, "industry": rec.industry, "parent_name": rec.parent_name,
            "is_public": rec.is_public}


def resolution_view(res: Resolution, catalog: Catalog | None = None) -> dict[str, Any]:
    view = _resolution_view(res)
    if catalog is not None:
        for cand in view["candidates"]:
            cand["details"] = candidate_details(catalog, cand["company_id"])
    return view


def _resolution_view(res: Resolution) -> dict[str, Any]:
    return {
        "company_id": res.company_id, "route": res.route.value, "method": res.method,
        "probability": round(res.probability, 4), "margin": round(res.margin, 4),
        "degraded": res.degraded, "config_version": res.config_version, "notes": res.notes,
        "candidates": [{"company_id": cand.company_id, "name": cand.name,
                        "probability": round(cand.probability, 4), "sources": sorted(cand.sources),
                        "scores": {"retrieval": round(cand.retrieval_score, 4),
                                   "splink_weight": round(cand.splink_weight, 3),
                                   "blink": None if cand.blink_score is None else round(cand.blink_score, 4)},
                        "features": {k: round(v, 3) for k, v in cand.features.items()
                                     if k in ("name_token_sort", "name_exact", "state_agree",
                                              "state_disagree", "city_agree", "industry_agree")}}
                       for cand in res.candidates[:5]],
    }


def status_for(route: Route) -> str:
    return {Route.EXACT_ID: "auto_resolved", Route.ACCEPTED: "auto_resolved",
            Route.REVIEW: "needs_review", Route.NIL: "unresolved"}[route]


def process_upload(c: Container, tenant_id: str, upload_id: str) -> None:
    """Resolve every pending supplier of an upload, create reviews, and update counters."""
    resolver = get_resolver(c)
    counts = {"auto_resolved": 0, "needs_review": 0, "unresolved": 0}
    try:
        with c.db.system() as conn:
            rows = conn.execute(
                "SELECT id, attributes FROM suppliers WHERE upload_id = %s AND tenant_id = %s "
                "AND status = 'pending' ORDER BY created_at, id", (upload_id, tenant_id)).fetchall()
        for i, row in enumerate(rows, start=1):
            res = resolver.resolve(to_query(str(row["id"]), row["attributes"]))
            status = status_for(res.route)
            counts[status] += 1
            detail = {"method": res.method, "route": res.route.value, "margin": res.margin,
                      "config_version": res.config_version, "degraded": res.degraded}
            with c.db.system() as conn:
                conn.execute(
                    "UPDATE suppliers SET status = %s, resolved_company_id = %s, confidence = %s, "
                    "resolution_detail = %s::jsonb WHERE id = %s AND tenant_id = %s",
                    (status, res.company_id if status == "auto_resolved" else None,
                     min(max(res.probability, 0.0), 1.0), json.dumps(detail), row["id"], tenant_id))
                if status == "needs_review":
                    conn.execute(
                        "INSERT INTO resolution_reviews (tenant_id, supplier_id, candidates) "
                        "VALUES (%s,%s,%s::jsonb)",
                        (tenant_id, row["id"],
                         json.dumps(resolution_view(res, resolver.catalog)["candidates"], default=str)))
                if i % 100 == 0:
                    _progress(conn, upload_id, counts, "processing")
        with c.db.system() as conn:
            _progress(conn, upload_id, counts, "complete")
    except Exception:
        with c.db.system() as conn:
            conn.execute("UPDATE supplier_uploads SET status = 'failed' WHERE id = %s", (upload_id,))
        raise


def _progress(conn: Any, upload_id: str, counts: dict[str, int], status: str) -> None:
    conn.execute(
        "UPDATE supplier_uploads SET auto_resolved = %s, needs_review = %s, unresolved = %s, "
        "status = %s WHERE id = %s",
        (counts["auto_resolved"], counts["needs_review"], counts["unresolved"], status, upload_id))

