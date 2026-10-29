# The extraction pipeline (`backend/document_processing/`)

*This is the extraction work of weeks 1–3, first described in the original
README. Moved here on 22 October 2026 when the README became the front page
of the whole application, and updated with what changed since (OCR tables,
REF fallback, header search).*

## What it is

The code that reads a real SYSCOHADA financial statement (balance sheet and
income statement) as **PDF or Excel** and turns it into structured,
code-indexed data: for each line item, its SYSCOHADA code, label, year N and
year N-1 amounts.

**Scope:** PDF and Excel only. Word/DOCX is refused as an unsupported file
type by design, not by omission.

## Why it exists

SYSCOHADA statements follow a standard structure (fixed line codes like
`BK`, `CP`, `XB`; a two-sided ACTIF/PASSIF balance sheet; a single-sided
income statement) but arrive as unstructured documents: native or scanned
PDFs, or Excel workbooks with no consistent column layout. This pipeline
extracts the underlying data whatever the format or exact layout, so it can
be checked and fed into the ratios without re-keying.

## How the application uses it

The application does not call these files directly. Two adapters wrap them
without changing them:

- `backend/app/infra/pdf/readers.py`: `PdfReader` and `ExcelReader` call the
  loaders and return the text, the tables, the page count and whether the
  file is scanned;
- `backend/app/infra/llm/rule_based.py`: `RuleBasedStructurer` uses
  `structure.py` to turn those tables into the proposed items the analyst
  reviews.

`backend/test_loader.py` is the original stand-alone harness: it runs the
seven stages on the PKG001 test files and prints every stage.

## The seven stages

Both PDF and Excel go through an equivalent version of each stage.

1. **Ingestion**: `document_loader.py` picks the loader from the extension
   (`pdf_loader.load_pdf` or `excel_loader.load_excel`).
2. **Document type detection**: for a PDF, whether it has a real text layer
   (`NATIVE_PDF`) or is image-only (`POSSIBLY_SCANNED`), which decides
   whether OCR is needed. Excel is always machine-readable.
3. **Text extraction**: the text of every page (PDF) or every cell (Excel).
4. **Table extraction**: for a native PDF, `pdfplumber` extracts the tables.
   For Excel, each sheet's rows already are a table.
5. **OCR fallback**: for scanned pages, Tesseract reads the page image.
   **Since October 2026** the OCR also returns the position of every word,
   and `ocr_page_table()` / `words_to_table()` rebuild a row/column table
   from those positions, the same shape `pdfplumber` returns. A scanned page
   can therefore reach the structuring stage at all. Pages are OCR'd in
   parallel (`OCR_WORKERS`).
6. **Normalisation** (`normarlize.py`): SYSCOHADA-formatted numbers (spaces
   as thousands separators, `"-"` for nil) become real numbers; the columns
   holding money are told apart from metadata (note references, operator
   symbols).
7. **Structured output** (`structure.py`): each row is split into its
   ACTIF/PASSIF (or single) side, a line item is built per code with its
   year N and N-1 values, and everything is indexed by code.
   `output_writer.py` writes the JSON used by `test_loader.py`.

## Key design decisions

**Money columns found by header, not by position.** Which columns hold
amounts is decided by matching the merged header text against keywords
(`EXERCICE`, `NET`, `BRUT`, `AMORT`), not by a fixed index, because
documents lay out columns differently. A content-based cross-check (what
share of a column's values look numeric) runs alongside and prints a warning
when the two disagree, so an unfamiliar header fails loudly instead of
silently normalising the wrong columns.

**Sides split on the `REF` columns.** Rather than hardcoding where each side
starts, the code finds every column labelled `REF` and splits there. This
works for both statement shapes. **Since October 2026**, the header row is
searched for (real exports such as SOCATRANS open with a title, an entity
block and a disclaimer before it), and when OCR has lost the word `REF` the
code falls back to the column where the two-letter codes themselves recur.

**Year N and N-1 by position, not by header text.** Header text for the
current and prior year can merge inconsistently (a bare `NET` versus
`EXERCICE AU 31/12/N-1 NET`), but the order is stable: the last money column
of a side is N-1, the one before it is N.

**Header row count detected, not assumed.** It differs between statement
types and between the PDF and Excel versions of the same document. Data is
taken to start at the first row whose `REF` column holds a valid
two-uppercase-letter code.

**Excel formulas resolved with `data_only=True`.** A workbook can hold
`=SUM(K15:K16)` instead of a value; openpyxl then returns Excel's last
computed result.

## Known limitations (documented, not extraction bugs)

- **AZ (fixed assets).** The first ground-truth file annotated AZ from the
  BRUT (gross) column, while BZ/DZ were annotated from NET. The extraction
  always reports NET, and R3 uses NET AZ so that it agrees with BZ, which
  CHK001 balances (decision recorded in `r03_stable_funding.py`). A hand
  reading that uses gross AZ fails CHK002, and the corpus campaign rejects
  it as a reference and says so.
- **XI / XG sign.** The income statement's own `+`/`-` operator column is
  still not interpreted, so a loss could arrive as a positive number. CHK003
  (XI = CJ) catches a mismatch when CJ is present; R4 and R5 depend on XI.
- **CA / CF prior-year values in the Excel test file** differ from the
  ground truth by 13 and 14. This comes from the workbook's own cached
  formula results, not from the pipeline. No ratio uses these codes.
- **Badly scanned PDFs.** On `ETAT_FINANCIER_TEST2.pdf` the OCR word
  positions are too scrambled (skew, resolution) for any column to survive,
  so the rule-based structurer finds nothing. The analyst can key the items
  in by hand (`AddItemForm`), or, since 27 October 2026, press **Read with
  AI**: `infra/llm/claude_vision.py` bypasses this pipeline entirely, renders
  each page as an image (PyMuPDF, long side 1568 px, at most
  `VISION_MAX_PAGES` pages) and has Claude read the items off the images
  (prompt `vision_v1.md`, engine `LLM_VISION`). The result is reviewed and
  validated like any other run. These are the documents where the language
  model is meant to earn its place, and a good place to measure it.

## Output format of `test_loader.py`

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