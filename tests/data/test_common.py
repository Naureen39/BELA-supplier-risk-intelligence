import time

import pytest

from data.scripts.build_wikidata_subset import subclass_closure_sql
from data.scripts.common import RateLimiter, sha256_file, user_agent
from data.scripts.download_exhibit21 import find_exhibit21_link, list_10k_filings
from data.scripts.download_gleif import csv_urls
from data.scripts.fetch_article_text import is_public_host, make_snippet
from data.scripts.harvest_gdelt import build_queries, load_seen


def test_sec_user_agent_requires_contact(monkeypatch):
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    with pytest.raises(RuntimeError):
        user_agent(sec=True)
    monkeypatch.setenv("SEC_USER_AGENT", "Example Org ops@example.org")
    assert user_agent(sec=True) == "Example Org ops@example.org"


def test_rate_limiter_spaces_calls():
    limiter = RateLimiter(0.05)
    start = time.monotonic()
    limiter.wait("a")
    limiter.wait("a")
    assert time.monotonic() - start >= 0.05
    start = time.monotonic()
    limiter.wait("b")
    assert time.monotonic() - start < 0.05


def test_sha256_file(tmp_path):
    path = tmp_path / "x.txt"
    path.write_bytes(b"abc")
    assert sha256_file(path) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_snippet_limit():
    assert len(make_snippet("word " * 200)) <= 300
    assert make_snippet("a  b\n c") == "a b c"


def test_ssrf_blocks_private_hosts():
    assert not is_public_host("127.0.0.1")
    assert not is_public_host("10.0.0.5")
    assert not is_public_host("169.254.169.254")
    assert not is_public_host("localhost")


def test_gdelt_queries_and_seen(tmp_path):
    queries = build_queries(["plant fire"], ["Acme Foods"])
    assert queries == [("topic", '"plant fire" sourcelang:english'), ("supplier", '"Acme Foods"')]
    path = tmp_path / "d.jsonl"
    path.write_text('{"url": "u1"}\n{"url": "u2"}\n')
    assert load_seen(path) == {"u1", "u2"}
    assert load_seen(tmp_path / "none.jsonl") == set()


def test_wikidata_closure_sql_lists_roots():
    sql = subclass_closure_sql(["Q1", "Q2"], "triples")
    assert "('Q1'), ('Q2')" in sql and "P279" in sql


def test_gleif_csv_urls():
    payload = {"lei2": {"full_file": {"csv": {"url": "https://x/l1.zip"}}}, "rr": {}}
    assert csv_urls(payload) == {"lei2": "https://x/l1.zip"}


def test_form_index_and_exhibit_link(tmp_path):
    idx = tmp_path / "form.idx"
    idx.write_text(
        "10-K   ACME CORP   1234   2025-02-14   edgar/data/1234/0001234-25-000001.txt\n"
        "8-K    ACME CORP   1234   2025-02-15   edgar/data/1234/0001234-25-000002.txt\n"
    )
    assert list_10k_filings(idx) == [(1234, "edgar/data/1234/0001234-25-000001.txt")]
    html = (
        "<table><tr><td>1</td><td>10-K</td><td><a href='/a/b.htm'>b.htm</a></td></tr>"
        "<tr><td>2</td><td>EX-21.1</td><td><a href='/a/ex21.htm'>ex21.htm</a></td></tr></table>"
    )
    assert find_exhibit21_link(html) == "/a/ex21.htm"


def test_cohens_kappa():
    from data.scripts.gold_agreement import cohens_kappa

    a = {"1": "x", "2": "y", "3": "x", "4": "y"}
    assert cohens_kappa(a, dict(a)) == 1.0
    b = {"1": "x", "2": "x", "3": "y", "4": "y"}
    assert cohens_kappa(a, b) == 0.0
