"""Upload helpers: template, mapping preview, result export, and the partial failure report.

Registered before the suppliers router so the static paths win over `/uploads/{upload_id}`.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile

from app.auth import deps
from app.auth import permissions as P
from app.auth.deps import Principal
from app.container import Container
from app.core.csvsafe import to_csv
from app.core.errors import ApiError
from app.routers.common import parse_uuid
from app.services import resolution as svc

router = APIRouter(tags=["uploads"])
viewer = deps.require(P.VIEW)
operator = deps.require(P.UPLOAD_REVIEW)

TEMPLATE_HEADER = ["supplier_name", "address", "city", "state", "country", "website", "cik", "lei",
                   "ticker", "tier"]
TEMPLATE_ROWS = [
    ["Example Supplier One Inc", "100 Example Road", "Springfield", "OH", "US", "", "", "", "", "1"],
    ["Example Supplier Two LLC", "", "Fairview", "TX", "US", "example-two.example", "", "", "", "2"],
]


@router.get("/uploads/template", summary="CSV template for supplier uploads")
def template(p: Principal = Depends(viewer)) -> Response:
    body = to_csv(TEMPLATE_HEADER, TEMPLATE_ROWS)
    return Response(body, media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="supplier_template.csv"'})


@router.post("/uploads/preview", summary="Validate a file and propose a column mapping (nothing is stored)")
async def preview(file: UploadFile = File(...), mapping: str | None = Form(default=None),
                  p: Principal = Depends(operator), c: Container = Depends(deps.get_container)
                  ) -> dict[str, Any]:
    raw = await file.read(c.settings.max_upload_bytes + 1)
    if len(raw) > c.settings.max_upload_bytes:
        raise ApiError(413, "The file is too large.", code="too-large")
    try:
        explicit = json.loads(mapping) if mapping else None
        rows, errors, used = svc.parse_csv(raw, explicit, c.settings.max_upload_rows)
    except json.JSONDecodeError as exc:
        raise ApiError(422, "The column mapping must be a JSON object.", code="validation") from exc
    except svc.UploadError as exc:
        raise ApiError(422, str(exc), code="invalid-upload") from exc
    header = raw.decode("utf-8-sig").splitlines()[0] if raw else ""
    columns: list[str] = next(csv.reader(io.StringIO(header)), [])
    return {"columns": columns, "mapping": used, "unmapped_fields": [f for f in svc.FIELD_ALIASES
                                                                    if f not in used],
            "valid_rows": len(rows), "invalid_rows": len(errors), "errors": errors[:20],
            "sample": rows[:5], "row_limit": c.settings.max_upload_rows}


def _own_upload(conn: Any, upload_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM supplier_uploads WHERE id = %s", (parse_uuid(upload_id, "upload"),)).fetchone()
    if not row:
        raise ApiError(404, "The upload was not found.", code="not-found")
    return dict(row)


@router.get("/uploads/{upload_id}/export", summary="Resolution results with canonical identifiers (CSV)")
def export(upload_id: str, p: Principal = Depends(viewer), conn: Any = deps.TENANT_DB) -> Response:
    up = _own_upload(conn, upload_id)
    rows = conn.execute(
        "SELECT s.uploaded_name, s.status, s.confidence, s.tier, s.resolution_detail, co.id AS cid, "
        "co.canonical_name, co.cik, co.lei, co.wikidata_qid, rs.level, rs.score FROM suppliers s "
        "LEFT JOIN companies co ON co.id = s.resolved_company_id "
        "LEFT JOIN LATERAL (SELECT level, score FROM risk_scores r WHERE r.supplier_id = s.id "
        "ORDER BY computed_at DESC, id DESC LIMIT 1) rs ON true WHERE s.upload_id = %s "
        "ORDER BY s.created_at, s.id", (up["id"],)).fetchall()
    header = ["supplier_name", "status", "confidence", "canonical_company_id", "canonical_name", "cik",
              "lei", "wikidata_qid", "match_method", "tier", "risk_level", "risk_score"]
    body = to_csv(header, [[r["uploaded_name"], r["status"], r["confidence"], r["cid"], r["canonical_name"],
                            r["cik"], r["lei"], r["wikidata_qid"],
                            (r["resolution_detail"] or {}).get("method"), r["tier"], r["level"], r["score"]]
                           for r in rows])
    return Response(body, media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="upload_{up["id"]}.csv"'})


@router.get("/uploads/{upload_id}/errors", summary="Rows that could not be imported (CSV)")
def errors_report(upload_id: str, p: Principal = Depends(viewer), conn: Any = deps.TENANT_DB) -> Response:
    up = _own_upload(conn, upload_id)
    body = to_csv(["row", "reason"], [[e["row"], e["reason"]] for e in up["errors"]])
    return Response(body, media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="upload_{up["id"]}_errors.csv"'})
