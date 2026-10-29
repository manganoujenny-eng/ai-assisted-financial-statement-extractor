"""PDF report of a validated analysis (FR-19, next to the Excel export).

The content comes from ``report_content.build_report()`` — the same as the
Excel workbook — and this file only lays it out, with PyMuPDF (already
installed for reading PDFs): HTML placed on A4 pages by ``fitz.Story``,
then a footer "Page x / y" once the number of pages is known.

Order: title and case, key figures, the summary (verdict, strengths,
weaknesses, what the figures can be relied on for, points of attention),
the ratios in detail, the checks, the validated amounts, the approved AI
commentary, and how the report is built.

PyMuPDF lays out HTML tables by their content and ignores column widths,
so tables are used only where every cell is short (case, key figures,
amounts); the rest is blocks of text.
"""

from __future__ import annotations

import html
from datetime import datetime
from io import BytesIO

import fitz  # PyMuPDF

from .report_content import build_report, number, when

NAVY = "#002868"
CSS = f"""
* {{ font-family: sans-serif; }}
body {{ font-size: 9.5pt; color: #1f2124; line-height: 1.35; }}
.brand {{ font-size: 7.5pt; color: #54595f; letter-spacing: 1px; margin: 0 0 2pt 0; }}
h1 {{ font-size: 19pt; color: {NAVY}; margin: 0 0 1pt 0; }}
.subtitle {{ font-size: 11pt; color: #54595f; margin: 0 0 10pt 0; }}
h2 {{ font-size: 12pt; color: {NAVY}; margin: 16pt 0 6pt 0; padding-bottom: 3pt;
     border-bottom: 1.5px solid {NAVY}; }}
h3 {{ font-size: 10pt; margin: 10pt 0 3pt 0; }}
h3.good {{ color: #15803d; }}
h3.bad {{ color: #b91c1c; }}
h3.info {{ color: {NAVY}; }}
table {{ width: 100%; border-collapse: collapse; }}
th {{ text-align: left; font-size: 7.5pt; color: #54595f; padding: 3pt 4pt;
     border-bottom: 1px solid #c9ced6; }}
td {{ padding: 3pt 4pt; border-bottom: 1px solid #e2e5ea; vertical-align: top; }}
td.num, th.num {{ text-align: right; }}
td.code {{ color: {NAVY}; }}
.facts td {{ border-bottom: 0; padding: 1pt 4pt 1pt 0; }}
.facts .label {{ color: #54595f; }}
.kf td {{ border-bottom: 0; padding: 4pt 6pt 4pt 0; }}
.kf .label {{ font-size: 7.5pt; color: #54595f; }}
.kf .figure {{ font-size: 12.5pt; font-weight: bold; color: {NAVY}; }}
.kf .before {{ font-size: 7.5pt; color: #7a7a7a; }}
.verdict {{ font-size: 10.5pt; margin: 2pt 0 4pt 0; padding: 2pt 0 2pt 8pt;
            border-left: 3px solid {NAVY}; }}
ul {{ margin: 0 0 2pt 0; padding-left: 14pt; }}
li {{ margin: 0 0 2pt 0; }}
.ratio {{ margin: 0 0 7pt 0; padding-bottom: 5pt; border-bottom: 1px solid #e2e5ea; }}
.ratio-head {{ margin: 0; font-size: 10pt; }}
.tag {{ font-size: 8pt; font-weight: bold; }}
.good {{ color: #15803d; }}
.bad {{ color: #b91c1c; }}
.neutral {{ color: #54595f; }}
.na {{ color: #a16207; }}
.meaning {{ margin: 1pt 0; color: #54595f; font-style: italic; }}
.line {{ margin: 1pt 0; }}
.small {{ font-size: 8pt; color: #54595f; }}
.check {{ margin: 0 0 3pt 0; }}
p {{ margin: 2pt 0 4pt 0; }}
"""


def _e(value) -> str:
    return html.escape("" if value is None else str(value))


def _list(items: list[str], empty: str) -> str:
    if not items:
        return f'<p class="small">{_e(empty)}</p>'
    return "<ul>" + "".join(f"<li>{_e(item)}</li>" for item in items) + "</ul>"


def _html(r: dict) -> str:
    t, h, lang = r["t"], r["headings"], r["lang"]
    out = [f'<p class="brand">{_e(t["brand"])}</p>',
           f'<h1>{_e(r["title"])}</h1>',
           f'<p class="subtitle">{_e(r["subtitle"])}</p>']

    # The case, in two columns (label and value in one cell, so a label
    # never wraps: PyMuPDF sizes columns by their content).
    facts = r["facts"]
    out.append('<table class="facts">')
    for i in range(0, len(facts), 2):
        out.append("<tr>" + "".join(
            f'<td><span class="label">{_e(label)} :</span> <b>{_e(value)}</b></td>'
            for label, value in facts[i:i + 2]) + "</tr>")
    out.append("</table>")

    # Key figures.
    if r["key_figures"]:
        out.append(f'<h2>{_e(h["keyFigures"])} (FCFA)</h2><table class="kf"><tr>')
        for kf in r["key_figures"]:
            before = (f'<br/><span class="before">{r["previous_year"]} : {_e(kf["previous"])}</span>'
                      if kf["previous"] is not None else "")
            # Labels padded to one length: PyMuPDF sizes columns by content,
            # so this keeps the four columns even.
            label = _e(kf["label"]) + "&#160;" * max(0, 30 - len(kf["label"]))
            out.append(f'<td><span class="label">{label}</span><br/>'
                       f'<span class="figure">{_e(kf["current"])}</span>{before}</td>')
        out.append("</tr></table>")

    # The summary.
    out.append(f'<h2>{_e(h["summary"])}</h2><p class="verdict">{_e(r["verdict"])}</p>')
    out.append(f'<h3 class="good">{_e(h["strengths"])}</h3>' + _list(r["strengths"], t["none"]))
    out.append(f'<h3 class="bad">{_e(h["weaknesses"])}</h3>' + _list(r["weaknesses"], t["none"]))
    out.append(f'<h3 class="info">{_e(h["reliance"])}</h3>' + _list(r["reliance"], t["none"]))
    out.append(f'<h3 class="info">{_e(h["attention"])}</h3>' + _list(r["attention"], t["none"]))

    # The ratios in detail.
    out.append(f'<h2>{_e(h["ratiosDetail"])}</h2>')
    for ratio in r["ratios"]:
        trend = ""
        if ratio["previous"] != "—":
            trend = (f'<p class="line small">{_e(t["previous"])} : {_e(ratio["previous"])}'
                     f' · {_e(t["change"])} : {_e(ratio["change"])}</p>')
        out.append(
            f'<div class="ratio"><p class="ratio-head"><b>{_e(ratio["code"])} · {_e(ratio["name"])}'
            f' : {_e(ratio["value"])}</b> &#160; <span class="tag {ratio["reading"]}">'
            f'{_e(ratio["reading_text"])}</span></p>'
            f'<p class="meaning">{_e(ratio["meaning"])}</p>'
            f'<p class="line">{_e(ratio["interpretation"])}</p>{trend}</div>')

    # The checks.
    out.append(f'<h2>{_e(h["checks"])}</h2>')
    for check in r["checks"]:
        state = "good" if check["passed"] else "bad"
        message = f' — <span class="small">{_e(check["message"])}</span>' if check["message"] else ""
        out.append(f'<p class="check"><b>{_e(check["code"])} · {_e(check["label"])}</b>'
                   f' <span class="small">({_e(check["severity"])})</span> : '
                   f'<span class="{state}"><b>{_e(check["result"])}</b></span>{message}</p>')

    # The validated amounts.
    year = r["year"]
    out.append(f'<h2>{_e(h["amounts"])}</h2><table><tr><th>{_e(t["code"])}</th>'
               f'<th>{_e(t["item"])}</th><th class="num">{year}</th>'
               + (f'<th class="num">{year - 1}</th>' if r["has_prior"] else "") + "</tr>")
    for row in r["amounts"]:
        out.append(f'<tr><td class="code">{_e(row["code"])}</td><td>{_e(row["label"])}</td>'
                   f'<td class="num">{number(row["current"], lang, 0)}</td>'
                   + (f'<td class="num">{number(row["previous"], lang, 0)}</td>' if r["has_prior"] else "")
                   + "</tr>")
    out.append("</table>")

    # The approved AI commentary.
    if r["ai"]:
        ai = r["ai"]
        out.append(f'<h2>{_e(h["ai"])}</h2><p class="small">{_e(ai["note"])}</p>')
        for title, text in ai["paragraphs"]:
            out.append(f'<h3 class="info">{_e(title)}</h3><p>{_e(text)}</p>')
        for title, points in ai["lists"]:
            out.append(f'<h3 class="info">{_e(title)}</h3>' + _list(points, t["none"]))

    out.append(f'<h2>{_e(h["method"])}</h2><p class="small">{_e(r["method"])}</p>')
    return "".join(out)


def export_analysis_pdf(
    case: dict,
    dataset: dict,
    ratios: list[dict],
    checks: list[dict],
    year_comparison: dict | None = None,
    ai_analysis: dict | None = None,
    labels=lambda code: code,
    language: str = "en",
    generated_at: datetime | None = None,
    reliability: dict | None = None,
) -> BytesIO:
    """The report as a PDF file in memory."""
    report = build_report(case, dataset, ratios, checks, year_comparison, ai_analysis,
                          labels, language, reliability, generated_at)
    body = _html(report)

    page = fitz.paper_rect("a4")
    content = page + (46, 46, -46, -56)  # margins; room for the footer
    story = fitz.Story(html=f"<html><body>{body}</body></html>", user_css=CSS)
    buffer = BytesIO()
    writer = fitz.DocumentWriter(buffer)
    more = True
    while more:
        device = writer.begin_page(page)
        more, _ = story.place(content)
        story.draw(device)
        writer.end_page()
    writer.close()

    # The header line and the footer, now that the number of pages is known.
    stamp = when(generated_at or datetime.now(), report["lang"])
    document = fitz.open(stream=buffer.getvalue(), filetype="pdf")
    grey = (0.33, 0.35, 0.37)
    for number_, pdf_page in enumerate(document, start=1):
        pdf_page.draw_line((46, page.height - 40), (page.width - 46, page.height - 40),
                           color=(0.79, 0.81, 0.84), width=0.6)
        pdf_page.insert_text((46, page.height - 28), report["subtitle"], fontsize=7.5, color=grey)
        footer = report["t"]["footer"].format(when=stamp, page=number_, pages=document.page_count)
        width = fitz.get_text_length(footer, fontsize=7.5)
        pdf_page.insert_text((page.width - 46 - width, page.height - 28), footer,
                             fontsize=7.5, color=grey)
    result = BytesIO(document.tobytes(garbage=3, deflate=True))
    document.close()
    return result