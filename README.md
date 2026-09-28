# SYSCOHADA Financial Statement Extraction & Structuring Pipeline

> **A full-chain scaffold has been added on top of this pipeline** (branch
> `base/scaffold`). The extraction work described below is unchanged and still
> lives in `backend/document_processing/`; everything around it — domain layer,
> ratio engine, checks, Flask API, React interface, tests — is new.
>
> **Start here: [`docs/LEARNING-PATH.md`](docs/LEARNING-PATH.md).** It lists
> what is built, what is left to you, in which order, and with which test.
>
> | Document | What it answers |
> |---|---|
> | [`docs/LEARNING-PATH.md`](docs/LEARNING-PATH.md) | What do I do next, week by week |
> | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Why is the code arranged this way |
> | [`docs/DATA-MODEL-REVIEW.md`](docs/DATA-MODEL-REVIEW.md) | What changed in the database schema, and why |
>
> Running it:
>
> ```bash
> python -m venv .venv && .venv\Scripts\activate
> pip install -r requirements.txt
> cd backend && python wsgi.py        # http://127.0.0.1:5000/api/health
> ```
> ```bash
> cd frontend && npm install && npm run dev    # http://localhost:5173
> ```
> ```bash
> pytest                               # 52 passed, 18 skipped — the 18 are the exercises
> ```


## What this is

A prototype that ingests real SYSCOHADA financial statements (balance sheet and
income statement) in either PDF or Excel format, and turns them into
structured, code-indexed data suitable for downstream ratio analysis and
consistency checking. Built as part of an internship/thesis project at EB
Audit & Advisory, Douala.

**Scope:** PDF and Excel input only. Word/DOCX is explicitly out of scope and
is rejected as an unsupported file type by design, not by omission.

## Why this exists

SYSCOHADA financial statements follow a standard structural layout (fixed
line-item codes like `BK`, `CP`, `XB`, a two-sided ACTIF/PASSIF layout for the
balance sheet, a single-sided layout for the income statement) but arrive as
unstructured documents — scanned or native PDFs, or Excel workbooks with no
consistent column layout between documents. This pipeline extracts the
underlying structured data regardless of which format or exact layout a given
document uses, so it can be validated and fed into ratio formulas and
consistency checks without manual re-keying.

## Pipeline stages

The pipeline is organized around seven stages, and both PDF and Excel input
go through an equivalent version of all seven:

1. **Ingestion** — load the raw file (`document_loader.py` dispatches by file
   extension to either `pdf_loader.load_pdf` or `excel_loader.load_excel`).
2. **Document type detection** — for PDF, determine whether the file has a
   real text layer (`NATIVE_PDF`) or is image-only (`POSSIBLY_SCANNED`), which
   decides whether OCR is needed. Excel files don't need this step; they're
   always machine-readable.
3. **Text extraction** — pull raw text from every page (PDF) or every cell
   (Excel).
4. **Table extraction** — for PDF, `pdfplumber` extracts structured tables
   from pages with a real text layer. For Excel, each sheet's rows are
   already cell-separated, so this step is a straightforward conversion
   rather than a detection problem.
5. **OCR fallback** — for scanned PDFs with no text layer, Tesseract OCR runs
   page-by-page instead of native text extraction. This is a real, accepted
   limitation for scanned documents: OCR recovers readable text, but
   `pdfplumber` cannot recover table *structure* from a scanned page (no
   vector/text layer to read positions from), so scanned PDFs currently
   produce 0 structured tables. Excel never needs this step.
6. **Normalization** — convert SYSCOHADA-formatted numbers (space-separated
   thousands, `"-"` as a nil placeholder) into real integers, and classify
   which columns are monetary versus which are metadata (Note references,
   operator symbols).
7. **Structured output** — split each row into its ACTIF/PASSIF (or single)
   side, build a line item per SYSCOHADA code with `current_year` and
   `prior_year` values, and combine everything into one code-indexed
   dictionary per document, written out as JSON.

## Project structure

```
backend/
├── test_loader.py                 # test harness — runs the full pipeline
│                                   # against real documents and reports output
│
└── document_processing/
    ├── document_loader.py         # entry point: detects file type, dispatches
    │                               # to the right loader
    ├── pdf_loader.py               # PDF ingestion, native/scanned detection,
    │                               # text extraction, OCR fallback, table
    │                               # extraction
    ├── excel_loader.py             # Excel ingestion and cell-to-text
    │                               # conversion
    ├── normarlize.py               # number normalization and monetary-column
    │                               # classification (filename intentionally
    │                               # spelled this way on disk)
    ├── structure.py                # side-splitting, line-item building,
    │                               # year-value extraction, code indexing
    └── output_writer.py            # writes the final structured result to
                                    # data/extracted/ as JSON

data/
├── test_documents/
│   └── PKG_001/                   # real test documents: native PDF, scanned
│                                   # PDF, Excel version of the same
│                                   # statement, ground-truth annotation file
└── extracted/                     # JSON output, one file per processed
                                    # document
```

## Key design decisions

**Header-driven monetary column classification, not hardcoded positions.**
Which columns hold monetary values is decided by matching merged header text
against a keyword list (`EXERCICE`, `NET`, `BRUT`, `AMORT`), not by assuming a
fixed column index — different documents lay out columns differently. A
content-based cross-check (what fraction of a column's actual values look
numeric) runs alongside the header-based classification and prints a warning
on disagreement, so a document with unfamiliar header wording fails loudly
with a specific warning rather than silently normalizing the wrong columns.

**Side-splitting by locating `REF` columns generically.** A SYSCOHADA balance
sheet row has two sides (ACTIF and PASSIF); an income statement row has one.
Rather than hardcoding which column index starts each side, the code scans
the header row for every column literally labeled `REF` and splits on those
positions — this works for both statement shapes without special-casing
either one.

**Current/prior year extracted by position, not by header text.** PDF header
text for the current-year vs. prior-year columns can be textually
inconsistent (a bare `NET` vs. a fully year-qualified `EXERCICE AU
31/12/N-1 NET` for what's structurally the same kind of column), but the
column order is structurally consistent: the last monetary column in a side
is always the prior year, the one before it is always the current year. Year
values are extracted by that position, independent of exactly how the header
text merged.

**Header row count detected dynamically, not assumed.** The number of header
rows before real data starts differs between statement types and even
between the PDF and Excel versions of the same document (the PDF's income
statement table has 2 header rows due to how the layout splits across lines;
the Excel version of the same statement has only 1). The pipeline detects
where real data starts by scanning for the first row where a `REF` column
holds a value matching the two-uppercase-letter pattern every real SYSCOHADA
code follows, rather than assuming a fixed count.

**Excel formula cells resolved via `data_only=True`.** Real Excel financial
statements can contain formulas (e.g., `=SUM(K15:K16)`) instead of literal
values. The workbook is loaded with `data_only=True` so openpyxl returns
Excel's last-calculated cached value instead of the formula text.

## Known limitations (found and documented, not fixed, because they aren't
## extraction bugs)

- **`AZ` (Fixed Assets) ground-truth value matches the BRUT (gross,
  pre-depreciation) column, not either NET column** — inconsistent with how
  `BZ`/`DZ` (Total Assets) were annotated using NET. Extraction is internally
  consistent (always reports NET); this looks like a data-entry
  inconsistency in the reference annotation dataset itself.
- **`XI`/`XG` (Net Income / Operating Income) sign ambiguity** — the income
  statement's own `+`/`-` operator column isn't yet interpreted, and the
  reference annotation dataset itself already flags this row as
  "Ambiguous"/"DISCREPANCY". Needs resolution before ratio formulas use these
  values.
- **`CA`/`CF` prior-year values in the Excel test file are off by a small,
  specific amount (13 and 14) from ground truth**, despite resolving to real
  numbers via `data_only=True`. This traces to the source workbook's own
  cached formula results, not to anything the pipeline does — likely a stale
  calculation cache or a data-entry issue in the underlying summed cells.
  Neither code is used by any of the five ratio formulas, so this doesn't
  block downstream work.

## Running it

From `backend/`, run `test_loader.py`. It processes every file listed in its
`test_paths`, printing detailed output at each stage, and writes one JSON
file per processed document to `data/extracted/`.

## Output format

Each JSON file in `data/extracted/` looks like:

```json
{
  "source_file": "ETAT FINANCIER TEST1.pdf",
  "file_type": "PDF",
  "line_items": {
    "BK": {
      "code": "BK",
      "label": "TOTAL ACTIF CIRCULANT",
      "current_year": 6746235223,
      "prior_year": 4855220024,
      "fields": { "...": "..." }
    }
  }
}
```

## Status

All seven pipeline stages are built and validated against real documents for
both PDF and Excel input, cross-checked against an independent ground-truth
annotation dataset and, for the test document that exists in both formats,
against each other.

Not yet built: the ratio formula engine (`R001`–`R005`) and consistency
checks (`CHK001`–`CHK005`) that will consume this structured output.
