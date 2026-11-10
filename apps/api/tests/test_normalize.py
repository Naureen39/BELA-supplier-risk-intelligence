import pytest
from app.kb.normalize import (
    legal_form,
    normalize_name,
    normalize_street,
    state_code,
    token_sort_key,
)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Acme Foods, LLC", "acme foods"),
        ("ACME FOODS INC.", "acme foods"),
        ("The Boeing Company", "boeing"),
        ("Johnson & Johnson", "johnson and johnson"),
        ("Acme Intl Mfg Corp", "acme international manufacturing"),
        ("Ｓｉｅｍｅｎｓ AG", "siemens"),
        ("O'Brien Brothers Inc", "obrien brothers"),
        ("St. Louis Steel Co", "st louis steel"),
    ],
)
def test_normalize_name(raw, expected):
    assert normalize_name(raw) == expected


def test_suffix_variants_collapse():
    variants = ["Acme Foods Inc", "ACME FOODS, INC.", "Acme Foods Incorporated", "Acme Foods LLC"]
    assert len({normalize_name(v) for v in variants}) == 1


def test_token_sort_key_ignores_order():
    assert token_sort_key("Steel Acme") == token_sort_key("Acme Steel")


def test_legal_form():
    assert legal_form("Acme Foods, LLC") == "LLC"
    assert legal_form("Acme Foods Inc.") == "INC"
    assert legal_form("Acme") is None


def test_state_code():
    assert state_code("US-DE") == "DE"
    assert state_code("Delaware") == "DE"
    assert state_code("oh") == "OH"
    assert state_code("Narnia") is None
    assert state_code(None) is None


def test_normalize_street():
    assert normalize_street("123 N Main St Suite 4, Dayton, OH 45402") == "123 n main st"
    assert normalize_street(None) == ""
