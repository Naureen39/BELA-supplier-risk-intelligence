from __future__ import annotations

from app.resolution.models import QueryRecord, Route
from app.resolution.structured import Resolver
from resolution_fixtures import catalog


def test_identifier_accepts_immediately() -> None:
    res = Resolver(catalog()).resolve(QueryRecord("r1", "totally different text", cik=1003))
    assert res.route is Route.EXACT_ID and res.company_id == 3 and res.method == "id:cik"


def test_ticker_and_domain_identifiers() -> None:
    r = Resolver(catalog())
    assert r.resolve(QueryRecord("a", "x", ticker="hlf")).company_id == 1
    assert r.resolve(QueryRecord("b", "x", website="https://www.harborline.example/about")).company_id == 1


def test_conflicting_identifiers_go_to_review() -> None:
    res = Resolver(catalog()).resolve(QueryRecord("r", "Harborline", cik=1001, lei="LEI0000000000000003"))
    assert res.route is Route.REVIEW and res.method.startswith("id_conflict")


def test_suffix_and_case_variants_resolve() -> None:
    res = Resolver(catalog()).resolve(QueryRecord("r", "NORTHGATE METALS CORP", state="PA", city="Pittsburgh"))
    assert res.company_id == 3 and res.route is Route.ACCEPTED


def test_same_name_different_state_uses_state() -> None:
    r = Resolver(catalog())
    assert r.resolve(QueryRecord("a", "Cobalt Ridge Logistics", state="NV")).company_id == 6
    assert r.resolve(QueryRecord("b", "Cobalt Ridge Logistics", state="TN")).company_id == 5


def test_same_name_no_state_is_not_auto_accepted() -> None:
    res = Resolver(catalog()).resolve(QueryRecord("r", "Cobalt Ridge Logistics Co"))
    assert res.route is not Route.ACCEPTED  # margin between the two identical names is zero


def test_unknown_company_is_nil() -> None:
    res = Resolver(catalog()).resolve(QueryRecord("r", "Zyxwv Quantum Bakery", state="CA"))
    assert res.route is Route.NIL and res.company_id is None


def test_subsidiary_not_confused_with_parent_when_state_differs() -> None:
    res = Resolver(catalog()).resolve(QueryRecord("r", "Northgate Metals of Texas", state="TX"))
    assert res.company_id == 4


def test_empty_name_is_nil() -> None:
    assert Resolver(catalog()).resolve(QueryRecord("r", "  ")).route is Route.NIL


def test_candidates_are_returned_for_transparency() -> None:
    res = Resolver(catalog()).resolve(QueryRecord("r", "Harborline Food", state="OH"))
    assert len(res.candidates) >= 2 and all(c.features for c in res.candidates)


def test_blink_outage_degrades_without_auto_accept() -> None:
    from collections.abc import Sequence

    from app.resolution.clients import RetrievedCandidate, ServiceUnavailable

    class Down:
        def retrieve(self, mention: str, context: str, k: int) -> list[RetrievedCandidate]:
            raise ServiceUnavailable("down")

        def rerank(self, mention: str, context: str, ids: Sequence[int]) -> dict[int, float]:
            raise ServiceUnavailable("down")

    from app.resolution.config import DEFAULT_CONFIG
    from app.resolution.retrievers import BlinkRetriever, TrigramRetriever

    cat = catalog()
    resolver = Resolver(cat, [TrigramRetriever(cat, DEFAULT_CONFIG), BlinkRetriever(Down())], blink=Down())
    res = resolver.resolve(QueryRecord("r", "Northgate Metals Corporation", state="PA", city="Pittsburgh"))
    assert res.degraded and res.route is Route.REVIEW and res.company_id == 3
    assert any("reduced confidence" in n for n in res.notes)
