"""Database tests: migrations, ETL on fixture files, quality report, vector search."""

from __future__ import annotations

import csv
import json
import random
from pathlib import Path

import pandas as pd
import psycopg
import pytest
from app.kb import pipeline
from app.kb.canonical import CanonicalBuilder
from app.kb.embeddings import HashedNgramEmbedder, embed_entities, search
from app.kb.quality import build_report
from app.kb.staging import SourceCompany
from app.kb.writer import (
    connect,
    reset_knowledge,
    write_companies,
    write_conflicts,
    write_facilities,
    write_relationships,
)

EXHIBIT = "<table><tr><td>Acme Foods Europe B.V.</td><td>The Netherlands</td></tr>" \
          "<tr><td>Acme Snacks LLC</td><td>Ohio</td></tr></table>"


def make_raw(root: Path) -> Path:
    (root / "edgar" / "exhibit21").mkdir(parents=True)
    (root / "registry" / "gleif").mkdir(parents=True)
    (root / "knowledge_base" / "wikidata").mkdir(parents=True)
    (root / "regulators" / "epa_echo").mkdir(parents=True)
    (root / "edgar" / "company_tickers_exchange.json").write_text(
        json.dumps(
            {
                "fields": ["cik", "name", "ticker", "exchange"],
                "data": [[1001, "Acme Foods Inc", "ACME", "NYSE"], [1002, "Zenith Corp", "ZEN", "Nasdaq"]],
            }
        )
    )
    (root / "edgar" / "cik-lookup-data.txt").write_text(
        "ACME FOODS INC:0000001001:\nACME BAKERY INC:0000001001:\nZENITH CORP:0000001002:\n"
    )
    (root / "edgar" / "exhibit21" / "1001_0001001-25-000001.htm").write_text(EXHIBIT)
    pd.DataFrame({"qid": ["Q1"], "label_en": ["Acme Foods"], "description_en": ["food maker"]}).to_parquet(
        root / "knowledge_base/wikidata/companies.parquet"
    )
    pd.DataFrame({"qid": ["Q1"], "lang": ["en"], "alias": ["Acme"]}).to_parquet(
        root / "knowledge_base/wikidata/aliases.parquet"
    )
    pd.DataFrame(
        {"qid": ["Q1"], "lei": ["LEI0001"], "cik": ["1001"], "ticker": ["ACME"]}
    ).to_parquet(root / "knowledge_base/wikidata/identifiers.parquet")
    with (root / "registry/gleif/golden_lei2.csv").open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            ["LEI", "Entity.LegalName", "Entity.EntityStatus", "Entity.LegalAddress.Country",
             "Entity.LegalAddress.Region", "Entity.LegalAddress.City"],
        )
        w.writeheader()
        w.writerow({"LEI": "LEI0001", "Entity.LegalName": "ACME FOODS INC", "Entity.EntityStatus": "ACTIVE",
                    "Entity.LegalAddress.Country": "US", "Entity.LegalAddress.Region": "US-OH",
                    "Entity.LegalAddress.City": "Dayton"})
        w.writerow({"LEI": "LEI0002", "Entity.LegalName": "Acme Snacks LLC", "Entity.EntityStatus": "ACTIVE",
                    "Entity.LegalAddress.Country": "US", "Entity.LegalAddress.Region": "US-OH",
                    "Entity.LegalAddress.City": "Dayton"})
        w.writerow({"LEI": "LEI0003", "Entity.LegalName": "Foreign Co", "Entity.EntityStatus": "ACTIVE",
                    "Entity.LegalAddress.Country": "DE", "Entity.LegalAddress.Region": "DE-BY",
                    "Entity.LegalAddress.City": "Munich"})
    with (root / "registry/gleif/golden_rr.csv").open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            ["Relationship.StartNode.NodeID", "Relationship.EndNode.NodeID",
             "Relationship.RelationshipType", "Relationship.RelationshipStatus"],
        )
        w.writeheader()
        w.writerow({"Relationship.StartNode.NodeID": "LEI0002", "Relationship.EndNode.NodeID": "LEI0001",
                    "Relationship.RelationshipType": "IS_DIRECTLY_CONSOLIDATED_BY",
                    "Relationship.RelationshipStatus": "ACTIVE"})
    with (root / "regulators/epa_echo/frs_national.csv").open("w", newline="") as f:
        w = csv.DictWriter(
            f, ["REGISTRY_ID", "PRIMARY_NAME", "LOCATION_ADDRESS", "CITY_NAME", "STATE_CODE",
                "POSTAL_CODE", "LATITUDE83", "LONGITUDE83", "NAICS_CODES"],
        )
        w.writeheader()
        w.writerow({"REGISTRY_ID": "110001", "PRIMARY_NAME": "ACME FOODS INC", "LOCATION_ADDRESS": "1 Mill Rd",
                    "CITY_NAME": "Dayton", "STATE_CODE": "OH", "POSTAL_CODE": "45402",
                    "LATITUDE83": "39.76", "LONGITUDE83": "-84.19", "NAICS_CODES": "311999"})
        w.writerow({"REGISTRY_ID": "110002", "PRIMARY_NAME": "UNKNOWN PLANT 7", "LOCATION_ADDRESS": "",
                    "CITY_NAME": "Reno", "STATE_CODE": "NV", "POSTAL_CODE": "",
                    "LATITUDE83": "39.5", "LONGITUDE83": "-119.8", "NAICS_CODES": ""})
    return root


def load(url: str, raw: Path, embed: bool = True) -> None:
    builder, edges, facilities = pipeline.build(raw)
    rels = builder.resolve_edges(edges)
    builder.check_relationships(rels)
    with connect(url) as conn:
        reset_knowledge(conn)
        ids = write_companies(conn, builder)
        write_relationships(conn, rels, ids)
        write_facilities(conn, builder, facilities, ids)
        write_conflicts(conn, builder.conflicts, ids)
        if embed:
            embed_entities(conn, HashedNgramEmbedder())


def test_etl_on_fixtures(db_url, tmp_path):
    load(db_url, make_raw(tmp_path))
    with psycopg.connect(db_url.replace("+psycopg", "")) as conn:
        report = build_report(conn)
        assert report.passed, report
        cov = report.coverage
        # Acme merges across EDGAR, Wikidata, GLEIF; Zenith; two Exhibit 21 rows (one is Acme Snacks)
        names = [r[0] for r in conn.execute("SELECT canonical_name FROM companies ORDER BY id")]
        assert "Acme Foods Inc" in names and len([n for n in names if "Acme Foods" in n]) <= 2
        acme = conn.execute(
            "SELECT cik, lei, wikidata_qid, tickers FROM companies WHERE cik = 1001"
        ).fetchone()
        assert acme == (1001, "LEI0001", "Q1", ["ACME"])
        assert conn.execute("SELECT count(*) FROM companies WHERE lei = 'LEI0003'").fetchone()[0] == 0
        # Former names and Wikidata alias landed as aliases
        aliases = {r[0] for r in conn.execute(
            "SELECT normalized FROM company_aliases a JOIN companies c ON c.id=a.company_id "
            "WHERE c.cik = 1001")}
        assert {"acme bakery", "acme"} <= aliases
        # GLEIF edge and Exhibit 21 edge produced relationships; Snacks resolved to one company
        assert cov["relationships"] >= 2
        assert conn.execute("SELECT count(*) FROM companies WHERE normalized_name='acme snacks'").fetchone()[0] == 1
        # Facility linked by exact name plus state only
        assert cov["facilities"] == 2 and cov["facilities_linked_exact"] == 1
        assert conn.execute("SELECT company_id FROM facilities WHERE registry_id='110002'").fetchone()[0] is None


def test_rebuild_refused_when_dependents_exist(db_url, tmp_path):
    load(db_url, make_raw(tmp_path), embed=False)
    with psycopg.connect(db_url.replace("+psycopg", ""), autocommit=True) as conn:
        conn.execute("INSERT INTO events (source, source_id, event_type, severity, reported_at, title)"
                     " VALUES ('t','1','recall',2,now(),'x')")
        conn.execute("INSERT INTO event_entities (event_id, company_id, role, method, score, route)"
                     " SELECT 1, id, 'subject', 'm', 0.9, 'accepted' FROM companies LIMIT 1")
    with connect(db_url) as conn, pytest.raises(RuntimeError):
        reset_knowledge(conn)


def test_audit_log_is_append_only(db_url):
    with psycopg.connect(db_url.replace("+psycopg", ""), autocommit=True) as conn:
        conn.execute("INSERT INTO audit_log (action, prev_hash, row_hash) VALUES ('x','0','1')")
        with pytest.raises(psycopg.errors.RaiseException):
            conn.execute("UPDATE audit_log SET action = 'y'")
        with pytest.raises(psycopg.errors.RaiseException):
            conn.execute("DELETE FROM audit_log")


def test_business_views_refresh(db_url):
    with psycopg.connect(db_url.replace("+psycopg", ""), autocommit=True) as conn:
        conn.execute("INSERT INTO plans VALUES ('starter','Starter',499,250,10)")
        tid = conn.execute("INSERT INTO tenants (name) VALUES ('Fictional Tenant') RETURNING id").fetchone()[0]
        conn.execute("INSERT INTO subscriptions (tenant_id, plan_code, billing_cycle, price, started_on)"
                     " VALUES (%s,'starter','annual',5389.20,'2024-01-15')", (tid,))
        conn.execute("REFRESH MATERIALIZED VIEW mrr_monthly")
        conn.execute("REFRESH MATERIALIZED VIEW cohort_retention")
        mrr = conn.execute("SELECT mrr FROM mrr_monthly WHERE month_start='2024-02-01'").fetchone()[0]
        assert float(mrr) == pytest.approx(449.10)
        assert conn.execute("SELECT count(*) FROM mrr_monthly WHERE month_start='2023-12-01'").fetchone()[0] == 0
        assert conn.execute("SELECT retention_pct FROM cohort_retention WHERE months_since_signup=0").fetchone()[0] == 100


WORDS = ["Apex", "Birch", "Cobalt", "Delta", "Ember", "Falcon", "Granite", "Harbor", "Iron",
         "Juniper", "Keystone", "Lumen", "Meridian", "Nimbus", "Orchid", "Pioneer", "Quartz",
         "Ridge", "Summit", "Tundra", "Union", "Vertex", "Willow", "Zephyr"]
KINDS = ["Foods", "Steel", "Plastics", "Logistics", "Chemicals", "Motors", "Textiles", "Energy"]


def test_vector_search_recall_at_5(db_url):
    rng = random.Random(42)
    names = sorted({f"{rng.choice(WORDS)} {rng.choice(WORDS)} {rng.choice(KINDS)}" for _ in range(3000)})
    names = names[:2000]
    builder = CanonicalBuilder()
    for i, n in enumerate(names):
        builder.add(SourceCompany("t", str(i), f"{n} Inc", state=None))
    with connect(db_url) as conn:
        ids = write_companies(conn, builder)
        embedder = HashedNgramEmbedder()
        embed_entities(conn, embedder)
        conn.commit()
        queries = rng.sample(range(len(names)), 1000)
        hits = 0
        for q in queries:
            noisy = names[q].upper().replace(" ", "  ", 1)
            noisy = noisy[:-1] if len(noisy) > 12 and q % 2 else noisy  # truncation noise
            hits += ids[q] in search(conn, embedder, noisy, k=5)
        rate = hits / len(queries)
    print(f"stand-in embedder recall@5 = {rate:.3f}")
    assert rate >= 0.90


def test_query_plans_use_indexes(db_url):
    """With sequential scans disabled, key lookups must be answerable from their indexes."""
    with psycopg.connect(db_url.replace("+psycopg", ""), autocommit=True) as conn:
        conn.execute(
            "INSERT INTO companies (canonical_name, normalized_name, hq_state, cik) "
            "SELECT 'Co ' || g, w1 || ' ' || w2 || ' ' || w3 || ' ' || g, 'OH', g "
            "FROM generate_series(1, 5000) g, LATERAL (SELECT "
            "(ARRAY['apex','birch','cobalt','delta','ember','falcon','granite','harbor'])[1 + g % 8] w1, "
            "(ARRAY['iron','juniper','keystone','lumen','meridian','nimbus','orchid'])[1 + g % 7] w2, "
            "(ARRAY['foods','steel','plastics','logistics','chemicals'])[1 + g % 5] w3) t"
        )
        conn.execute(
            "INSERT INTO company_aliases (company_id, alias, alias_type, normalized, source) "
            "SELECT id, 'a' || id, 'dba', reverse(normalized_name), 't' FROM companies"
        )
        conn.execute("ANALYZE")
        conn.execute("SET enable_seqscan = off")
        vec = "[" + ",".join(["0.1"] * 1024) + "]"
        plans = {
            "trigram_company": "EXPLAIN SELECT id FROM companies WHERE normalized_name % 'apex iron foods 9'",
            "exact_name_state": "EXPLAIN SELECT id FROM companies WHERE normalized_name='acme' AND hq_state='OH'",
            "cik": "EXPLAIN SELECT id FROM companies WHERE cik = 1",
            "family_children": "EXPLAIN SELECT child_id FROM company_relationships WHERE parent_id = 1",
            "hnsw": f"EXPLAIN SELECT company_id FROM entity_embeddings ORDER BY embedding <=> '{vec}'::vector LIMIT 5",
        }
        expect = {
            "trigram_company": "companies_norm_trgm",
            "exact_name_state": "companies_norm_state",
            "cik": "companies_cik_key",
            "family_children": "company_relationships_parent_id_child_id_rel_type_source_key",
            "hnsw": "entity_embeddings_hnsw",
        }
        for name, sql in plans.items():
            plan = "\n".join(r[0] for r in conn.execute(sql))
            assert expect[name] in plan, f"{name}: {plan}"


def test_pipeline_cli_end_to_end(db_url, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(pipeline, "RAW", make_raw(tmp_path))
    assert pipeline.main(["--embedder", "hashed"]) == 0
    out = capsys.readouterr().out
    assert "RESULT: pass" in out and "facility_link_rate" in out
    # Re-running is idempotent: the knowledge base is rebuilt to the same state.
    assert pipeline.main(["--embedder", "hashed"]) == 0
