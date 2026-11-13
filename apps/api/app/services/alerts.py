"""Create alerts from monitoring drafts: de-duplicated in the database, then published live."""

from __future__ import annotations

from typing import Any

from app.container import Container
from app.events.monitor import AlertDraft
from app.events_bus import alert_channel


async def create_alerts(c: Container, tenant_id: str, drafts: list[tuple[str, AlertDraft]]
                        ) -> list[str]:
    """Insert alerts for (supplier uuid, draft) pairs. A repeat of the same dedup key is ignored.

    Returns the ids of alerts actually created; each one is published on the tenant channel.
    """
    created: list[dict[str, Any]] = []
    with c.db.system() as conn:
        for supplier_uuid, d in drafts:
            key = f"{d.kind}:{d.event_id}"
            row = conn.execute(
                "INSERT INTO alerts (tenant_id, supplier_id, rule_id, kind, detail, dedup_key) "
                "SELECT %s, s.id, %s, %s, %s, %s FROM suppliers s WHERE s.id = %s AND s.tenant_id = %s "
                "ON CONFLICT DO NOTHING RETURNING id, supplier_id, kind, detail, created_at",
                (tenant_id, d.rule_id, d.kind, d.detail, f"{supplier_uuid}:{key}", supplier_uuid,
                 tenant_id)).fetchone()
            if row:
                if d.event_id is not None:
                    conn.execute("INSERT INTO alert_events (alert_id, change) VALUES (%s, 'created')",
                                 (row["id"],))
                created.append(row)
    for row in created:
        await c.broker.publish(alert_channel(tenant_id), {
            "id": str(row["id"]), "supplier_id": str(row["supplier_id"]), "kind": row["kind"],
            "detail": row["detail"], "created_at": row["created_at"].isoformat()})
    return [str(r["id"]) for r in created]
