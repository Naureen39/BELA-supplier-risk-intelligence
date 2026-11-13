"""PDF rendering with WeasyPrint. External resources are never fetched."""

from __future__ import annotations

import html
from typing import Any

CSS = """
@page { size: A4; margin: 18mm 16mm 20mm 16mm;
  @bottom-right { content: "Page " counter(page) " of " counter(pages); font: 8pt sans-serif; color: #555; } }
body { font: 10pt/1.45 sans-serif; color: #0B1B33; }
h1 { font-size: 20pt; margin: 0 0 4pt; } h2 { font-size: 13pt; margin: 16pt 0 6pt; border-bottom: 1px solid #DDE3EC; padding-bottom: 2pt; }
.meta { color: #555; font-size: 9pt; } .banner { background: #E6EFFB; padding: 6pt 8pt; margin: 8pt 0; font-size: 9pt; }
.disclaimer { border: 1px solid #C77700; padding: 6pt 8pt; margin: 10pt 0; font-size: 9pt; }
table { width: 100%; border-collapse: collapse; margin: 4pt 0; } th, td { text-align: left; padding: 3pt 4pt; border-bottom: 1px solid #DDE3EC; vertical-align: top; font-size: 9pt; }
th { background: #F6F8FB; } td { overflow-wrap: anywhere; } td.url { font-size: 7.5pt; color: #1F5FBF; } .num { text-align: right; } .lvl { font-weight: bold; }
"""
DISCLAIMER = "Risk signals are leads for human review and not statements of fault."


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def table(headers: list[str], rows: list[list[Any]], num_cols: tuple[int, ...] = (),
          widths: tuple[int, ...] = (), url_cols: tuple[int, ...] = ()) -> str:
    def cls(i: int) -> str:
        return "num" if i in num_cols else "url" if i in url_cols else ""

    head = "".join(f'<th style="width:{widths[i]}%">{esc(h)}</th>' if widths else f"<th>{esc(h)}</th>"
                   for i, h in enumerate(headers))
    body = "".join(
        "<tr>" + "".join(f'<td class="{cls(i)}">{esc(c)}</td>' for i, c in enumerate(r)) + "</tr>"
        for r in rows)
    if not rows:
        body = f'<tr><td colspan="{len(headers)}">No records.</td></tr>'
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def document(title: str, report_id: str, generated: str, sections: list[str], demo: bool) -> str:
    safe_id = "".join(ch for ch in report_id if ch.isalnum() or ch == "-")[:40]
    footer = (f'@page {{ @bottom-left {{ content: "Report {safe_id}"; font: 8pt sans-serif; '
              'color: #555; } }')
    banner = ('<div class="banner">Demo data: tenant, supplier portfolio, and business figures in this '
              "environment are synthetic and do not represent real commercial relationships.</div>"
              if demo else "")
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>{esc(title)}</title>"
            f"<style>{CSS}{footer}</style></head><body>"
            f"<h1>{esc(title)}</h1><div class='meta'>Report ID {esc(report_id)} | Generated {esc(generated)}</div>"
            f"{banner}<div class='disclaimer'>{esc(DISCLAIMER)}</div>{''.join(sections)}"
            "</body></html>")


def _deny(url: str, *args: Any, **kwargs: Any) -> Any:
    raise ValueError(f"external resources are disabled: {url[:60]}")


def render_pdf(html_text: str) -> bytes:
    from weasyprint import HTML

    data = HTML(string=html_text, url_fetcher=_deny).write_pdf()
    assert isinstance(data, bytes)
    return data
