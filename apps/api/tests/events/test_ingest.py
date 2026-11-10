from __future__ import annotations

import csv
import json
from pathlib import Path

from app.events.ingest import NHTSA_COLUMNS, ingest_file, write_jsonl
from app.events.rules import load_rules

RULES = load_rules()


def test_csv_json_and_tab_readers(tmp_path: Path) -> None:
    c = tmp_path / "osha.csv"
    with c.open("w", newline="") as fh:
        w = csv.DictWriter(fh, ["activity_nr", "estab_name", "site_state", "citation_id", "viol_type",
                                "current_penalty", "issuance_date"])
        w.writeheader()
        w.writerow({"activity_nr": "1", "estab_name": "A Co", "site_state": "OH", "citation_id": "1",
                    "viol_type": "S", "current_penalty": "20000", "issuance_date": "2025-02-01"})
        w.writerow({"activity_nr": "2", "estab_name": "B Co", "site_state": "OH", "citation_id": "1",
                    "viol_type": "O", "current_penalty": "10", "issuance_date": "2025-02-01"})
    events, stats = ingest_file(c, "osha", RULES)
    assert len(events) == 1 and stats["rows"] == 2 and stats["skipped:below_threshold"] == 1

    j = tmp_path / "fda.json"
    j.write_text(json.dumps({"results": [{"recall_number": "F-1", "recalling_firm": "A Co",
                                          "classification": "Class II", "report_date": "20250301"}]}))
    events, _ = ingest_file(j, "openfda", RULES, kind="drug")
    assert events[0].source_id == "drug:F-1"

    t = tmp_path / "rcl.txt"
    row = {k: "" for k in NHTSA_COLUMNS} | {"CAMPNO": "25V1", "MFGNAME": "A Motors", "POTAFF": "5000",
                                              "RCDATE": "20250101", "COMPNAME": "BRAKES"}
    t.write_text("\t".join(row[k] for k in NHTSA_COLUMNS) + "\n")
    events, _ = ingest_file(t, "nhtsa", RULES)
    assert events[0].severity == 2  # 5,000 units is band 1, critical component adds one

    out = tmp_path / "e.jsonl"
    write_jsonl(events, out)
    assert json.loads(out.read_text().splitlines()[0])["source"] == "nhtsa"
