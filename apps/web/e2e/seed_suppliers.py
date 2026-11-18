"""Upload a messy supplier list through the running API as the demo manager, then score it.

Usage: python apps/web/e2e/seed_suppliers.py http://127.0.0.1:8000
"""

from __future__ import annotations

import sys
import time

import httpx

PASSWORD = "Violet-Harbor-Quartz-7421"
CSV = """name,city,state,tier
NORTHGATE METALS CORP,Pittsburgh,PA,tier_1
Northgate Metals of Texas,Houston,TX,tier_2
Northgate Alloys Ohio,Toledo,OH,tier_2
HARBORLINE FOODS INC,Columbus,OH,tier_1
Harborline Packaging,Columbus,OH,tier_3
Cobalt Ridge Logistics,Memphis,TN,tier_2
Summit Chemicals Corp.,Houston,TX,tier_1
Summit Plastics,Detroit,MI,tier_3
Ironwood Motors,Detroit,MI,tier_1
Lantern Pharma Labs,Newark,NJ,tier_2
Willow Textile Co,Charlotte,NC,tier_3
Quartz Energy Grp,Fresno,CA,tier_2
Harborline Fods Inc,Columbus,OH,tier_3
Acme Industrial Supply Co,Dayton,OH,tier_3
Bluebird Fasteners LLC,Akron,OH,tier_3
Summit,,,tier_3
"""


def main(base: str) -> None:
    with httpx.Client(base_url=f"{base}/api/v1", timeout=30) as c:
        r = c.post("/auth/login", json={"email": "manager@demo.example", "password": PASSWORD})
        r.raise_for_status()
        csrf = c.cookies.get("pr_csrf") or ""
        h = {"X-CSRF-Token": csrf}
        up = c.post("/uploads", headers=h, files={"file": ("suppliers.csv", CSV.encode(), "text/csv")})
        up.raise_for_status()
        uid = up.json()["id"]
        for _ in range(60):
            s = c.get(f"/uploads/{uid}").json()
            if s["status"] in ("complete", "completed", "failed", "done"):
                break
            time.sleep(0.5)
        print("upload", s["status"], {k: s.get(k) for k in ("auto_resolved", "needs_review", "unresolved")})
        rec = c.post("/monitoring/recompute", headers=h)
        print("recompute", rec.status_code, rec.text[:120])


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000")
