"""Read downloaded regulator files, normalize them, and write events as JSONL or PostgreSQL.

    python -m app.events.ingest --source osha --path data/raw/regulators/osha/violations.json
    python -m app.events.ingest --source nhtsa --path FLAT_RCL_POST_2010.txt --out events.jsonl

CSV (EPA, OSHA archive), tab-delimited text (NHTSA, columns from RCL.txt), and JSON (CPSC, openFDA,
OSHA API) are supported. A stats summary (events, skip reasons, missing mapped fields) is printed
so a wrong field name in the rules file is visible immediately.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections.abc import Callable, Iterator, Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.events.normalizers import cpsc, epa, fda, nhtsa, osha
from app.events.normalizers.common import NormalizeStats
from app.events.rules import EventRules, load_rules
from app.events.schema import NormalizedEvent

# NHTSA RCL.txt column order (flat file has no header row). Confirm against the current RCL.txt.
NHTSA_COLUMNS = (
    "RECORD_ID CAMPNO MAKETXT MODELTXT YEARTXT MFGCAMPNO COMPNAME MFGNAME BGMAN ENDMAN RCLTYPECD "
    "POTAFF ODATE INFLUENCED_BY MFGTXT RCDATE DATEA RPNO FMVSS DESC_DEFECT CONEQUENCE_DEFECT "
    "CORRECTIVE_ACTION NOTES RCL_CMPT_ID MFR_COMP_NAME MFR_COMP_DESC MFR_COMP_PTNO"
).split()


def read_rows(path: Path, source: str) -> Iterator[Mapping[str, Any]]:
    if source == "nhtsa":
        with path.open(encoding="latin-1", newline="") as fh:
            for parts in csv.reader(fh, delimiter="\t"):
                yield dict(zip(NHTSA_COLUMNS, parts, strict=False))
    elif path.suffix.lower() == ".json":
        data = json.loads(path.read_text())
        rows: Any = data.get("results", data.get("rows", [])) if isinstance(data, dict) else data
        yield from rows or []
    else:
        with path.open(encoding="utf-8-sig", newline="") as fh:
            yield from csv.DictReader(fh)


def _normalizer(source: str, kind: str) -> Callable[[Mapping[str, Any], EventRules, NormalizeStats], list[NormalizedEvent]]:
    if source == "openfda":
        return lambda row, rules, stats: fda.normalize_row(row, rules, stats, kind)
    table = {"epa_echo": epa.normalize_row, "osha": osha.normalize_row,
             "nhtsa": nhtsa.normalize_row, "cpsc": cpsc.normalize_row}
    return table[source]


def ingest_file(path: Path, source: str, rules: EventRules, kind: str = "food"
                ) -> tuple[list[NormalizedEvent], NormalizeStats]:
    stats = NormalizeStats()
    norm = _normalizer(source, kind)
    events: list[NormalizedEvent] = []
    for row in read_rows(path, source):
        stats["rows"] += 1
        events.extend(norm(row, rules, stats))
    return events, stats


def write_jsonl(events: list[NormalizedEvent], out: Path) -> None:
    with out.open("w", encoding="utf-8") as fh:
        for ev in events:
            d = asdict(ev)
            d["reported_at"] = ev.reported_at.isoformat()
            d["occurred_at"] = ev.occurred_at.isoformat() if ev.occurred_at else None
            fh.write(json.dumps(d, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, choices=["epa_echo", "osha", "nhtsa", "cpsc", "openfda"])
    parser.add_argument("--path", type=Path, required=True)
    parser.add_argument("--kind", default="food", help="openFDA product kind: food, drug, device")
    parser.add_argument("--out", type=Path, help="write normalized events as JSONL")
    parser.add_argument("--rules", type=Path)
    args = parser.parse_args()
    rules = load_rules(args.rules) if args.rules else load_rules()
    events, stats = ingest_file(args.path, args.source, rules, args.kind)
    if args.out:
        write_jsonl(events, args.out)
    print(json.dumps({"source": args.source, "rules_version": rules.version, **dict(sorted(stats.items()))},
                     indent=2))


if __name__ == "__main__":
    main()
