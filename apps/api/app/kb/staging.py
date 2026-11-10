"""Source loaders: read raw files into `SourceCompany`, `SourceEdge`, `SourceFacility` records.

Column and layout assumptions are isolated here so they can be adjusted after inspecting the
real downloads (EDGAR JSON layout, GLEIF Golden Copy CSV headers, EPA FRS headers).
"""

from __future__ import annotations

import csv
import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from app.kb.normalize import legal_form, state_code


@dataclass
class SourceCompany:
    source: str
    source_key: str
    name: str
    cik: int | None = None
    lei: str | None = None
    qid: str | None = None
    state: str | None = None  # US state code of incorporation or headquarters
    country: str | None = None
    city: str | None = None
    tickers: list[str] = field(default_factory=list)
    sic: str | None = None
    is_public: bool = False
    status: str = "active"
    description: str | None = None
    aliases: list[tuple[str, str]] = field(default_factory=list)  # (alias, alias_type)


@dataclass(frozen=True)
class SourceEdge:
    source: str
    parent_key: tuple[str, str]  # (source, source_key) of the parent record
    child_key: tuple[str, str]
    rel_type: str
    share: float | None = None
    as_of: str | None = None


@dataclass(frozen=True)
class SourceFacility:
    registry_id: str
    name: str
    address: str | None
    city: str | None
    state: str | None
    postal_code: str | None
    latitude: float | None
    longitude: float | None
    industry_code: str | None
    source: str = "epa_frs"


# EDGAR -----------------------------------------------------------------------------------
def load_edgar_tickers(path: Path) -> list[SourceCompany]:
    """company_tickers_exchange.json: {"fields": [cik, name, ticker, exchange], "data": [...]}."""
    payload = json.loads(path.read_text())
    by_cik: dict[int, SourceCompany] = {}
    for cik, name, ticker, _exchange in payload["data"]:
        record = by_cik.setdefault(
            int(cik),
            SourceCompany("edgar", str(int(cik)), name, cik=int(cik), is_public=True),
        )
        if ticker and ticker not in record.tickers:
            record.tickers.append(ticker)
    return list(by_cik.values())


def load_edgar_cik_lookup(path: Path) -> dict[int, list[str]]:
    """cik-lookup-data.txt: lines of 'NAME:0000001234:'. Returns names per CIK."""
    names: dict[int, list[str]] = {}
    for raw in path.read_text(errors="replace").splitlines():
        parts = raw.rsplit(":", 2)
        if len(parts) != 3 or not parts[1].strip().isdigit():
            continue
        names.setdefault(int(parts[1]), []).append(parts[0].strip())
    return names


def apply_submissions(record: SourceCompany, submissions: dict[str, object]) -> None:
    """Enrich an EDGAR record from a data.sec.gov submissions payload."""
    sic = submissions.get("sic")
    if sic:
        record.sic = str(sic)
    incorp = submissions.get("stateOfIncorporation")
    if isinstance(incorp, str):
        record.state = state_code(incorp)
    former = submissions.get("formerNames")
    if isinstance(former, list):
        for item in former:
            if isinstance(item, dict) and item.get("name"):
                record.aliases.append((str(item["name"]), "former"))


# GLEIF -----------------------------------------------------------------------------------
def load_gleif_level1(path: Path, us_only: bool = True) -> Iterator[SourceCompany]:
    """Level 1 LEI-CDF CSV. Keeps active records, US entities only when us_only is set."""
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("Entity.EntityStatus") != "ACTIVE":
                continue
            country = row.get("Entity.LegalAddress.Country", "")
            if us_only and country != "US":
                continue
            lei = row["LEI"]
            record = SourceCompany(
                "gleif",
                lei,
                row["Entity.LegalName"],
                lei=lei,
                state=state_code(row.get("Entity.LegalAddress.Region")),
                country=country,
                city=row.get("Entity.LegalAddress.City") or None,
            )
            other = row.get("Entity.OtherEntityNames.OtherEntityName.1")
            if other:
                record.aliases.append((other, "dba"))
            yield record


_GLEIF_REL = {
    "IS_DIRECTLY_CONSOLIDATED_BY": "direct_parent",
    "IS_ULTIMATELY_CONSOLIDATED_BY": "ultimate_parent",
}


def load_gleif_level2(path: Path) -> Iterator[SourceEdge]:
    """Level 2 relationship CSV: start node is the child, end node is the parent."""
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            rel = _GLEIF_REL.get(row.get("Relationship.RelationshipType", ""))
            if not rel or row.get("Relationship.RelationshipStatus") != "ACTIVE":
                continue
            yield SourceEdge(
                "gleif",
                ("gleif", row["Relationship.EndNode.NodeID"]),
                ("gleif", row["Relationship.StartNode.NodeID"]),
                rel,
            )


# Wikidata --------------------------------------------------------------------------------
def load_wikidata(directory: Path) -> list[SourceCompany]:
    """Read the parquet subset written by build_wikidata_subset."""
    import pandas as pd

    companies = pd.read_parquet(directory / "companies.parquet")
    ids = pd.read_parquet(directory / "identifiers.parquet").set_index("qid")
    aliases = pd.read_parquet(directory / "aliases.parquet")
    alias_map = aliases[aliases["lang"] == "en"].groupby("qid")["alias"].apply(list).to_dict()
    records = []
    for row in companies.itertuples(index=False):
        if not row.label_en:
            continue
        ident = ids.loc[row.qid] if row.qid in ids.index else None
        cik = ident["cik"] if ident is not None else None
        records.append(
            SourceCompany(
                "wikidata",
                row.qid,
                row.label_en,
                qid=row.qid,
                lei=(ident["lei"] if ident is not None and ident["lei"] else None),
                cik=int(cik) if cik not in (None, "") and str(cik).isdigit() else None,
                tickers=[ident["ticker"]] if ident is not None and ident["ticker"] else [],
                description=row.description_en,
                aliases=[(a, "dba") for a in alias_map.get(row.qid, [])],
            )
        )
    return records


# Exhibit 21 ------------------------------------------------------------------------------
def load_exhibit21(directory: Path) -> tuple[list[SourceCompany], list[SourceEdge]]:
    """Parse every downloaded Exhibit 21 into subsidiary records and parent edges."""
    from data.scripts.parse_exhibit21 import parse_exhibit21

    companies: list[SourceCompany] = []
    edges: list[SourceEdge] = []
    for path in sorted(directory.glob("*.htm")):
        parent_cik = int(path.name.split("_")[0])
        for sub in parse_exhibit21(path.read_text(errors="replace"), parent_cik):
            key = f"{parent_cik}:{sub.name}"
            code = state_code(sub.jurisdiction)
            companies.append(
                SourceCompany(
                    "exhibit21",
                    key,
                    sub.name,
                    state=code,
                    country="US" if code else None,
                    aliases=[(sub.name, "subsidiary")],
                )
            )
            edges.append(
                SourceEdge("exhibit21", ("edgar", str(parent_cik)), ("exhibit21", key), "subsidiary")
            )
    return companies, edges


# EPA Facility Registry Service -----------------------------------------------------------
def load_frs(path: Path) -> Iterator[SourceFacility]:
    """FRS national combined CSV (headers: REGISTRY_ID, PRIMARY_NAME, ...)."""
    with path.open(newline="", encoding="latin-1") as handle:
        for row in csv.DictReader(handle):
            if not row.get("REGISTRY_ID") or not row.get("PRIMARY_NAME"):
                continue

            def num(value: str | None) -> float | None:
                try:
                    return float(value) if value else None
                except ValueError:
                    return None

            yield SourceFacility(
                registry_id=row["REGISTRY_ID"],
                name=row["PRIMARY_NAME"].strip(),
                address=row.get("LOCATION_ADDRESS") or None,
                city=row.get("CITY_NAME") or None,
                state=state_code(row.get("STATE_CODE")),
                postal_code=row.get("POSTAL_CODE") or None,
                latitude=num(row.get("LATITUDE83")),
                longitude=num(row.get("LONGITUDE83")),
                industry_code=(row.get("NAICS_CODES") or row.get("SIC_CODES") or "").split(",")[0]
                or None,
            )


def form_of(name: str) -> str | None:
    return legal_form(name)
