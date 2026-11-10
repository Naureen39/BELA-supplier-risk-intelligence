"""Name and address normalization utilities.

Pipeline for names: Unicode NFKC, case folding, ampersand to "and", punctuation removal,
legal suffix removal (cleanco), abbreviation expansion, leading article removal.
`token_sort_key` additionally sorts tokens for order-insensitive comparison.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

import usaddress
from cleanco import basename

ABBREVIATIONS: dict[str, str] = {
    "intl": "international",
    "int'l": "international",
    "mfg": "manufacturing",
    "mfr": "manufacturer",
    "mfrs": "manufacturers",
    "natl": "national",
    "assoc": "associates",
    "bros": "brothers",
    "svcs": "services",
    "svc": "service",
    "tech": "technology",
    "labs": "laboratories",
    "lab": "laboratory",
    "dist": "distribution",
    "ind": "industries",
    "inds": "industries",
    "grp": "group",
    "mgmt": "management",
    "pkg": "packaging",
    "chem": "chemical",
    "elec": "electric",
    "mtr": "motor",
    "mtrs": "motors",
}
# "co" and "corp" are legal suffixes handled by cleanco. "st" is ambiguous (saint or street)
# and is deliberately not expanded.

US_STATES: dict[str, str] = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA",
    "colorado": "CO", "connecticut": "CT", "delaware": "DE", "florida": "FL", "georgia": "GA",
    "hawaii": "HI", "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA",
    "kansas": "KS", "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV", "new hampshire": "NH",
    "new jersey": "NJ", "new mexico": "NM", "new york": "NY", "north carolina": "NC",
    "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA",
    "rhode island": "RI", "south carolina": "SC", "south dakota": "SD", "tennessee": "TN",
    "texas": "TX", "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC",
    "puerto rico": "PR", "guam": "GU",
}
VALID_STATE_CODES: frozenset[str] = frozenset(US_STATES.values()) | {"VI", "AS", "MP"}

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_SPACES = re.compile(r"\s+")


def state_code(value: str | None) -> str | None:
    """Return a two-letter US state code for a code, a name, or a GLEIF region like 'US-DE'."""
    if not value:
        return None
    text = value.strip()
    if text.upper().startswith("US-"):
        text = text[3:]
    if text.upper() in VALID_STATE_CODES:
        return text.upper()
    return US_STATES.get(text.lower())


def _strip_suffix(name: str) -> str:
    stripped = basename(name)
    return stripped if stripped else name


@lru_cache(maxsize=200_000)
def normalize_name(name: str) -> str:
    """Normalize a company name for exact comparison and indexing."""
    text = unicodedata.normalize("NFKC", name).casefold()
    text = text.replace("&", " and ")
    text = _strip_suffix(text)
    text = _PUNCT.sub(" ", text.replace("'", ""))
    tokens = _SPACES.sub(" ", text).strip().split(" ")
    if tokens and tokens[0] == "the" and len(tokens) > 1:
        tokens = tokens[1:]
    return " ".join(t for t in (ABBREVIATIONS.get(tok, tok) for tok in tokens) if t)


def token_sort_key(name: str) -> str:
    """Order-insensitive key: normalized tokens sorted alphabetically."""
    return " ".join(sorted(normalize_name(name).split()))


_FORM_PATTERN = re.compile(
    r"\b(incorporated|inc|corporation|corp|company|co|limited liability company|l\.?l\.?c|"
    r"limited|ltd|l\.?p|llp|plc|gmbh|ag|s\.?a|n\.?v|b\.?v)\b\.?\s*$",
    re.IGNORECASE,
)


def legal_form(name: str) -> str | None:
    """Return the trailing legal form token of a raw name (for example 'LLC'), if any."""
    match = _FORM_PATTERN.search(unicodedata.normalize("NFKC", name).strip().rstrip(","))
    return match[1].upper().replace(".", "") if match else None


def parse_address(text: str) -> dict[str, str]:
    """Parse a US address string into usaddress components. Returns {} on failure."""
    try:
        tagged, _kind = usaddress.tag(text)
    except usaddress.RepeatedLabelError:
        return {}
    return dict(tagged)


def normalize_street(text: str | None) -> str:
    """Normalized street line (number, directional, name, type) for address comparison."""
    if not text:
        return ""
    parts = parse_address(text)
    keys = (
        "AddressNumber", "StreetNamePreDirectional", "StreetName",
        "StreetNamePostType", "StreetNamePostDirectional",
    )
    return " ".join(parts[k].casefold().strip(".,") for k in keys if k in parts)
