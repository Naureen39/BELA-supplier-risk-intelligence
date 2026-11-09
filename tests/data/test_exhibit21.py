from data.scripts.parse_exhibit21 import normalize_jurisdiction, parse_exhibit21

HTML_TABLE = """
<html><body><p>EXHIBIT 21.1 SUBSIDIARIES OF THE REGISTRANT</p>
<table>
<tr><td>Name of Subsidiary</td><td>State or Other Jurisdiction of Incorporation</td></tr>
<tr><td>Acme Foods, LLC</td><td>Delaware</td></tr>
<tr><td>Acme Foods Europe B.V.</td><td>The Netherlands</td></tr>
<tr><td>Acme Foods, LLC</td><td>Delaware</td></tr>
</table></body></html>
"""

PRE_TEXT = """
EXHIBIT 21

Subsidiaries of the Company

Northwind Holdings, Inc. ........ Delaware
Northwind Logistics GmbH ........ Germany
Northwind Pacific Pty Ltd ....... Australia
"""

PAREN_LIST = """
<div>Zenith Components Corp. (Ohio)</div>
<div>Zenith Components Mexico, S. de R.L. de C.V. (Mexico)</div>
<div>Zenith Capital LLC (Nevada)</div>
"""

NO_JURISDICTION = """
<p>Orion Industries Inc.</p><p>Orion Industries Canada Ltd.</p><p>See notes.</p>
"""


def names(rows):
    return [r.name for r in rows]


def test_html_table_with_duplicates_and_header():
    rows = parse_exhibit21(HTML_TABLE, parent_cik=123)
    assert names(rows) == ["Acme Foods, LLC", "Acme Foods Europe B.V."]
    assert rows[0].jurisdiction == "Delaware"
    assert rows[1].jurisdiction == "The Netherlands"
    assert all(r.parent_cik == 123 for r in rows)


def test_dotted_leader_text():
    rows = parse_exhibit21(PRE_TEXT)
    assert [(r.name, r.jurisdiction) for r in rows] == [
        ("Northwind Holdings, Inc.", "Delaware"),
        ("Northwind Logistics GmbH", "Germany"),
        ("Northwind Pacific Pty Ltd", "Australia"),
    ]


def test_parenthesized_jurisdiction():
    rows = parse_exhibit21(PAREN_LIST)
    assert [r.jurisdiction for r in rows] == ["Ohio", "Mexico", "Nevada"]


def test_names_without_jurisdiction_kept_only_when_entity_like():
    rows = parse_exhibit21(NO_JURISDICTION)
    assert names(rows) == ["Orion Industries Inc.", "Orion Industries Canada Ltd."]


def test_normalize_jurisdiction():
    assert normalize_jurisdiction("a Delaware corporation") == "Delaware"
    assert normalize_jurisdiction("nowhere land") is None
    assert normalize_jurisdiction(None) is None
