from __future__ import annotations

import pytest
from app.events.normalizers import cpsc, epa, fda, nhtsa, osha
from app.events.normalizers.common import NormalizeStats
from app.events.rules import RulesError, load_rules

RULES = load_rules()
FAULT_WORDS = ("violated", "guilty", "illegal", "negligent", "caused", "liable", "broke the law")


def test_rules_load_and_validate(tmp_path) -> None:  # type: ignore[no-untyped-def]
    assert RULES.version == "event_rules_v1" and RULES.band("osha", "penalty_bands", 80000) == 3
    bad = tmp_path / "bad.yaml"
    bad.write_text("version: x\nmin_year: 2015\n")
    with pytest.raises(RulesError):
        load_rules(bad)


def test_osha_threshold_severity_and_idempotent_id() -> None:
    row = {"activity_nr": "1001", "estab_name": "Harborline Foods Inc", "site_city": "Columbus",
           "site_state": "OH", "citation_id": "01001", "viol_type": "W", "current_penalty": "80000",
           "issuance_date": "2025-03-04", "open_date": "2024-12-01"}
    stats = NormalizeStats()
    ev = osha.normalize_row(row, RULES, stats)[0]
    assert ev.event_type == "workplace_safety" and ev.severity == 4  # band 3 plus willful bump
    assert ev.source_id == "1001:01001" and ev.state == "OH"
    assert osha.normalize_row({**row, "current_penalty": "1200"}, RULES, stats) == []
    assert stats["skipped:below_threshold"] == 1


def test_epa_rules() -> None:
    row = {"FAC_REGISTRY_ID": "110000", "FAC_NAME": "NORTHGATE METALS PITTSBURGH", "FAC_CITY": "Pittsburgh",
           "FAC_STATE": "PA", "FAC_SNC_FLG": "Y", "FAC_FORMAL_ACTION_COUNT": "2",
           "FAC_TOTAL_PENALTIES": "60000", "FAC_DATE_LAST_FORMAL_ACTION": "07/15/2025",
           "FAC_LAT": "40.4", "FAC_LONG": "-80.0"}
    ev = epa.normalize_row(row, RULES)[0]
    assert ev.event_type == "environmental" and ev.severity == 2 and ev.latitude == 40.4
    assert "$60,000" in ev.title
    assert epa.normalize_row({**row, "FAC_SNC_FLG": "N", "FAC_FORMAL_ACTION_COUNT": "0",
                              "FAC_TOTAL_PENALTIES": "0"}, RULES) == []
    assert epa.normalize_row({**row, "FAC_DATE_LAST_FORMAL_ACTION": "01/01/2009"}, RULES) == []


def test_fda_classes() -> None:
    base = {"recall_number": "F-1-2025", "recalling_firm": "Harborline Foods, Inc.",
            "report_date": "20250512", "state": "OH", "city": "Columbus"}
    sev = {c: fda.normalize_row({**base, "classification": c}, RULES)[0].severity
           for c in ("Class I", "Class II", "Class III")}
    assert sev == {"Class I": 4, "Class II": 3, "Class III": 2}


def test_cpsc_roles_hazard_and_units() -> None:
    row = {"RecallNumber": "25-100", "RecallDate": "2025-06-01", "Title": "Space heaters recalled",
           "URL": "https://www.cpsc.gov/Recalls/2025/x", "Hazards": [{"Name": "Fire hazard"}],
           "Products": [{"NumberOfUnits": "about 150,000"}],
           "Manufacturers": [{"Name": "Summit Auto Parts International"}],
           "Retailers": [{"Name": "Big Box Stores"}]}
    ev = cpsc.normalize_row(row, RULES)[0]
    assert ev.severity == 4 and {e.role for e in ev.entities} == {"manufacturer", "retailer"}


def test_nhtsa_units_and_component() -> None:
    row = {"CAMPNO": "25V123", "MFGNAME": "Summit Auto Parts International", "COMPNAME": "AIR BAGS",
           "POTAFF": "250000", "RCDATE": "20250801", "DESC_DEFECT": "Inflator may rupture."}
    ev = nhtsa.normalize_row(row, RULES)[0]
    assert ev.severity == 4 and ev.source_id == "25V123"


def test_missing_mapped_field_is_reported_not_silent() -> None:
    stats = NormalizeStats()
    assert osha.normalize_row({"activity_nr": "1"}, RULES, stats) == []
    assert stats["missing_field:name"] >= 1


def test_titles_state_records_not_fault() -> None:
    rows = [
        osha.normalize_row({"activity_nr": "1", "estab_name": "A Co", "citation_id": "1", "viol_type": "S",
                            "current_penalty": "20000", "issuance_date": "2025-01-01"}, RULES),
        fda.normalize_row({"recall_number": "1", "recalling_firm": "A Co", "classification": "Class I",
                           "report_date": "20250101"}, RULES),
    ]
    for events in rows:
        for e in events:
            assert not any(w in (e.title + (e.summary or "")).lower() for w in FAULT_WORDS)
