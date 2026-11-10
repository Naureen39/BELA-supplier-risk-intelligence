"""Small fictional-name catalog for resolution tests."""

from __future__ import annotations

from app.resolution.catalog import Catalog, CompanyRecord

RECORDS = [
    CompanyRecord(1, "Harborline Foods, Inc.", aliases=("Harborline Food Service",), cik=1001,
                  tickers=("HLF",), hq_city="Columbus", hq_state="OH", sic_code="2000",
                  qid="Q1001", is_public=True, domain="harborline.example"),
    CompanyRecord(2, "Harborline Food Service LLC", hq_city="Dayton", hq_state="OH", sic_code="5140",
                  qid="Q1002"),
    CompanyRecord(3, "Northgate Metals Corporation", aliases=("Northgate Metal Works",), cik=1003,
                  hq_city="Pittsburgh", hq_state="PA", sic_code="3310", qid="Q1003", is_public=True,
                  lei="LEI0000000000000003"),
    CompanyRecord(4, "Northgate Metals of Texas LLC", hq_city="Houston", hq_state="TX",
                  sic_code="3310", parent_name="Northgate Metals Corporation"),
    CompanyRecord(5, "Cobalt Ridge Logistics Co.", hq_city="Memphis", hq_state="TN", sic_code="4210"),
    CompanyRecord(6, "Cobalt Ridge Logistics Co.", hq_city="Reno", hq_state="NV", sic_code="4210"),
    CompanyRecord(7, "Summit Auto Parts International", aliases=("Summit Auto",), hq_city="Detroit",
                  hq_state="MI", sic_code="3714", qid="Q1007"),
]
EDGES = [(3, 4), (1, 2)]


def catalog() -> Catalog:
    return Catalog(RECORDS, EDGES)
