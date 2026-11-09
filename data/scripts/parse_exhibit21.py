"""Parse Exhibit 21 (list of subsidiaries) documents into structured rows.

Exhibit 21 documents are free-form HTML or text. The parser handles three layouts:
HTML tables, preformatted text with aligned columns, and plain lines with a trailing
jurisdiction in parentheses or after a separator. Output rows contain the subsidiary
name, jurisdiction (when present), and the parent CIK supplied by the caller.

Usage: python -m data.scripts.parse_exhibit21 FILE --parent-cik 12345
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from bs4 import BeautifulSoup

JURISDICTIONS = {
    # US states and territories
    *"Alabama Alaska Arizona Arkansas California Colorado Connecticut Delaware Florida Georgia "
    "Hawaii Idaho Illinois Indiana Iowa Kansas Kentucky Louisiana Maine Maryland Massachusetts "
    "Michigan Minnesota Mississippi Missouri Montana Nebraska Nevada Ohio Oklahoma Oregon "
    "Pennsylvania Tennessee Texas Utah Vermont Virginia Washington Wisconsin Wyoming "
    "Guam Samoa".split(),
    "New Hampshire", "New Jersey", "New Mexico", "New York", "North Carolina", "North Dakota",
    "Rhode Island", "South Carolina", "South Dakota", "West Virginia", "Puerto Rico",
    "District of Columbia",
    # Common non-US jurisdictions
    "Argentina", "Australia", "Austria", "Bahamas", "Belgium", "Bermuda", "Brazil",
    "British Virgin Islands", "Canada", "Cayman Islands", "Chile", "China", "Colombia",
    "Costa Rica", "Cyprus", "Czech Republic", "Denmark", "Egypt", "England", "Finland",
    "France", "Germany", "Gibraltar", "Greece", "Guernsey", "Hong Kong", "Hungary", "India",
    "Indonesia", "Ireland", "Isle of Man", "Israel", "Italy", "Japan", "Jersey", "Korea",
    "Luxembourg", "Malaysia", "Mauritius", "Mexico", "Netherlands", "New Zealand", "Nigeria",
    "Norway", "Panama", "Peru", "Philippines", "Poland", "Portugal", "Romania", "Russia",
    "Saudi Arabia", "Scotland", "Singapore", "Slovakia", "South Africa", "South Korea", "Spain",
    "Sweden", "Switzerland", "Taiwan", "Thailand", "Turkey", "Ukraine", "United Arab Emirates",
    "United Kingdom", "Uruguay", "Vietnam", "The Netherlands", "People's Republic of China",
}
_JUR_LOOKUP = {j.lower(): j for j in JURISDICTIONS}

_HEADER_WORDS = re.compile(
    r"^(name|names?\s+of|subsidiar|jurisdiction|state or|place of|incorporat|organiz|"
    r"percent|ownership|exhibit|list of|\*|note|the following|omitted)",
    re.IGNORECASE,
)
_ENTITY_HINT = re.compile(
    r"\b(inc|incorporated|corp|corporation|co|company|llc|l\.l\.c|ltd|limited|lp|l\.p|llp|plc|"
    r"gmbh|ag|sa|s\.a|nv|n\.v|bv|b\.v|sarl|s\.a\.r\.l|pty|pte|kk|oy|ab|as|a/s|spa|s\.p\.a|"
    r"holdings|group|partners|trust|fund|bank|sdn bhd|de c\.v|s\. de r\.l)\b\.?",
    re.IGNORECASE,
)
_PAREN_JUR = re.compile(r"^(?P<name>.+?)\s*[\(\[](?P<jur>[^()\[\]]+)[\)\]]\s*$")
_SEP_JUR = re.compile(r"^(?P<name>.+)\s*(?:\s*\.{2,}\s*|\s-\s|\s{3,}|\t|\s*,\s)\s*(?P<jur>[A-Za-z .'\-]+)$")


@dataclass(frozen=True)
class Subsidiary:
    name: str
    jurisdiction: str | None
    parent_cik: int | None


def _clean(text: str) -> str:
    text = text.replace("\xa0", " ").replace("​", "")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*\.{2,}\s*$", "", text)  # dotted leaders
    return text.strip(" \t:;*|-").lstrip(".")


def normalize_jurisdiction(raw: str | None) -> str | None:
    if not raw:
        return None
    cleaned = _clean(raw)
    if cleaned.lower() in _JUR_LOOKUP:
        return _JUR_LOOKUP[cleaned.lower()]
    cleaned = re.sub(r"^(a|an|the)\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+(corporation|company|limited liability company|llc)$", "", cleaned, flags=re.IGNORECASE)
    return _JUR_LOOKUP.get(cleaned.lower())


def _is_candidate_name(text: str) -> bool:
    if len(text) < 3 or len(text) > 200:
        return False
    if _HEADER_WORDS.match(text):
        return False
    if re.fullmatch(r"[\d.%\s,]+", text):
        return False
    return True


def _from_cells(cells: list[str]) -> tuple[str, str | None] | None:
    cells = [c for c in (_clean(c) for c in cells) if c]
    if not cells:
        return None
    name = cells[0]
    if not _is_candidate_name(name):
        return None
    jurisdiction = None
    for cell in cells[1:]:
        jurisdiction = normalize_jurisdiction(cell)
        if jurisdiction:
            break
    if jurisdiction is None and not _ENTITY_HINT.search(name):
        return None
    return name, jurisdiction


def _from_line(line: str) -> tuple[str, str | None] | None:
    line = line.strip().lstrip("*-• ").strip()
    line = re.sub(r"^\d+[.)]\s+", "", line)
    if not line:
        return None
    match = _PAREN_JUR.match(line)
    if match and normalize_jurisdiction(match["jur"]):
        name = _clean(match["name"])
        return (name, normalize_jurisdiction(match["jur"])) if _is_candidate_name(name) else None
    match = _SEP_JUR.match(line)
    if match and normalize_jurisdiction(match["jur"]):
        name = _clean(match["name"])
        return (name, normalize_jurisdiction(match["jur"])) if _is_candidate_name(name) else None
    name = _clean(line)
    if _is_candidate_name(name) and _ENTITY_HINT.search(name):
        return name, None
    return None


def parse_exhibit21(content: str, parent_cik: int | None = None) -> list[Subsidiary]:
    """Parse the text or HTML of an Exhibit 21 document."""
    rows: list[tuple[str, str | None]] = []
    soup = BeautifulSoup(content, "lxml")
    tables = soup.find_all("table")
    if tables:
        for table in tables:
            for tr in table.find_all("tr"):
                cells = [td.get_text(" ") for td in tr.find_all(["td", "th"])]
                parsed = _from_cells(cells)
                if parsed:
                    rows.append(parsed)
    if not rows:
        for br in soup.find_all("br"):
            br.replace_with("\n")
        for block in soup.find_all(["p", "div", "li"]):
            block.append("\n")
        text = soup.get_text("\n") if soup.find() else content
        for line in text.splitlines():
            parsed = _from_line(line)
            if parsed:
                rows.append(parsed)
    seen: set[tuple[str, str | None]] = set()
    result: list[Subsidiary] = []
    for name, jurisdiction in rows:
        key = (name.lower(), jurisdiction)
        if key in seen:
            continue
        seen.add(key)
        result.append(Subsidiary(name, jurisdiction, parent_cik))
    return result


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--parent-cik", type=int)
    args = parser.parse_args(argv)
    rows = parse_exhibit21(args.file.read_text(errors="replace"), args.parent_cik)
    for row in rows:
        print(json.dumps(asdict(row)))


if __name__ == "__main__":
    main()
