"""Fictional company catalog generator for tests, load tests, and offline smoke runs.

Names are invented word combinations. They are not real companies and results measured on them are
not evidence about real data.
"""

from __future__ import annotations

import random

from app.resolution.catalog import Catalog, CompanyRecord

_A = ["Harbor", "Northgate", "Cobalt", "Summit", "Ridge", "Lakeview", "Ironwood", "Meridian",
      "Bluestone", "Keystone", "Redfield", "Silverline", "Oakmont", "Pinecrest", "Westbrook",
      "Granite", "Cedar", "Falcon", "Riverbend", "Stonegate", "Alder", "Beacon", "Crescent"]
_B = ["Foods", "Metals", "Logistics", "Auto Parts", "Chemicals", "Plastics", "Packaging",
      "Pharma", "Textiles", "Electric", "Paper", "Steel", "Dairy", "Freight", "Components",
      "Machinery", "Polymers", "Beverage", "Medical", "Energy"]
_C = ["Industries", "Group", "Holdings", "International", "Manufacturing", "Systems", ""]
_FORMS = ["Inc.", "LLC", "Corporation", "Co.", "Ltd."]
_STATES = [("OH", "Columbus"), ("TX", "Houston"), ("PA", "Pittsburgh"), ("CA", "Fresno"),
           ("MI", "Detroit"), ("NY", "Buffalo"), ("TN", "Memphis"), ("NV", "Reno"),
           ("IL", "Peoria"), ("GA", "Macon"), ("WI", "Madison"), ("NC", "Raleigh")]
_SIC = {"Foods": "2000", "Metals": "3310", "Logistics": "4210", "Auto Parts": "3714",
        "Chemicals": "2800", "Plastics": "3080", "Packaging": "2650", "Pharma": "2834",
        "Textiles": "2200", "Electric": "3600", "Paper": "2620", "Steel": "3312", "Dairy": "2020",
        "Freight": "4213", "Components": "3670", "Machinery": "3560", "Polymers": "2821",
        "Beverage": "2080", "Medical": "3841", "Energy": "4911"}


def generate_catalog(n: int, seed: int = 42, subsidiary_share: float = 0.15,
                     twin_share: float = 0.05) -> Catalog:
    """`n` fictional companies, with same-name twins in other states and subsidiaries."""
    rng = random.Random(seed)
    records: list[CompanyRecord] = []
    edges: list[tuple[int, int]] = []
    used: set[str] = set()
    next_id = 1
    while len(records) < n:
        b = rng.choice(_B)
        base = " ".join(p for p in (rng.choice(_A), rng.choice(_A) if rng.random() < 0.4 else "",
                                    b, rng.choice(_C)) if p)
        if base in used:
            continue
        used.add(base)
        state, city = rng.choice(_STATES)
        name = f"{base} {rng.choice(_FORMS)}"
        parent = CompanyRecord(next_id, name, hq_city=city, hq_state=state, sic_code=_SIC[b],
                               industry=b, is_public=rng.random() < 0.2,
                               cik=100000 + next_id if rng.random() < 0.2 else None)
        records.append(parent)
        next_id += 1
        if rng.random() < twin_share and len(records) < n:
            s2, c2 = rng.choice([s for s in _STATES if s[0] != state])
            records.append(CompanyRecord(next_id, name, hq_city=c2, hq_state=s2, sic_code=_SIC[b],
                                         industry=b))
            next_id += 1
        if rng.random() < subsidiary_share and len(records) < n:
            s3, c3 = rng.choice(_STATES)
            sub = CompanyRecord(next_id, f"{base} of {c3} LLC", hq_city=c3, hq_state=s3,
                                sic_code=_SIC[b], industry=b, parent_name=parent.name)
            records.append(sub)
            edges.append((parent.id, sub.id))
            next_id += 1
    return Catalog(records, edges)
