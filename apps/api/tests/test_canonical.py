from app.kb.canonical import CanonicalBuilder
from app.kb.staging import SourceCompany, SourceEdge


def rec(source, key, name, **kw):
    return SourceCompany(source, key, name, **kw)


def test_identifier_first_merge():
    b = CanonicalBuilder()
    a = b.add(rec("edgar", "1", "Acme Foods Inc", cik=1, state="OH", tickers=["ACME"]))
    c = b.add(rec("wikidata", "Q1", "Acme Foods", qid="Q1", cik=1))
    d = b.add(rec("gleif", "L1", "ACME FOODS INCORPORATED", lei="L1", state="OH"))
    assert a == c == d  # CIK match, then exact name plus state
    company = b.companies[a]
    assert (company.cik, company.qid, company.lei) == (1, "Q1", "L1")
    methods = {k.source: k.method for k in b.links}
    assert methods == {"edgar": "new", "wikidata": "identifier", "gleif": "exact_name_state"}


def test_same_name_different_state_not_merged():
    b = CanonicalBuilder()
    a = b.add(rec("gleif", "L1", "Summit Plastics LLC", state="OH"))
    c = b.add(rec("gleif", "L2", "Summit Plastics LLC", state="TX"))
    assert a != c


def test_fuzzy_match_is_flagged_not_merged():
    b = CanonicalBuilder()
    a = b.add(rec("edgar", "1", "Northwind Logistics Holdings", cik=1, state="OH"))
    c = b.add(rec("gleif", "L2", "Northwind Logistic Holdings", lei="L2", state="OH"))
    assert a != c
    assert [x.kind for x in b.conflicts] == ["fuzzy_candidate"]


def test_identifier_conflict_recorded():
    b = CanonicalBuilder()
    a = b.add(rec("edgar", "1", "Alpha Corp", cik=1))
    c = b.add(rec("gleif", "L1", "Beta Corp", lei="L1"))
    b.add(rec("wikidata", "Q9", "Gamma", qid="Q9", cik=1, lei="L1"))
    kinds = [x.kind for x in b.conflicts]
    assert "identifier_conflict" in kinds
    assert {a, c} == set(next(x for x in b.conflicts if x.kind == "identifier_conflict").canonical)


def test_relationship_cycles_and_parent_conflicts():
    b = CanonicalBuilder()
    for i, name in enumerate(["Alpha Holdings", "Bravo Systems", "Charlie Works"], start=1):
        b.add(rec("edgar", str(i), name, cik=i))
    edges = [
        SourceEdge("x", ("edgar", "1"), ("edgar", "2"), "direct_parent"),
        SourceEdge("x", ("edgar", "2"), ("edgar", "1"), "direct_parent"),  # cycle
        SourceEdge("y", ("edgar", "3"), ("edgar", "2"), "direct_parent"),  # second parent for 2
        SourceEdge("y", ("edgar", "3"), ("edgar", "3"), "direct_parent"),  # self edge dropped
    ]
    rels = b.resolve_edges(edges)
    assert len(rels) == 3
    kinds = {c.kind for c in b.check_relationships(rels)}
    assert kinds == {"relationship_cycle", "parent_conflict"}
