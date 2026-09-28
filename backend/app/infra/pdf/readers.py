"""Adapters over the extraction code Helena already wrote.

``backend/document_processing/`` is not rewritten and not moved. It is wrapped.
Each class below implements the ``DocumentReader`` port and translates the
existing functions into the ``RawDocument`` the domain expects.

That is the Adapter pattern of dossier §13 doing exactly what it promises: an
existing, working, tested piece of code keeps its shape and gains a stable
interface. If ``pdfplumber`` is ever replaced by something else, only this
file changes — the services, the checks and the ratios never learn about it.

The imports are deliberately *inside* the methods. ``fitz``, ``pdfplumber``
and ``pytesseract`` are heavy and, in the case of Tesseract, need a binary
installed on the machine. Importing them lazily means the API starts, the
tests run and the Excel path works on a workstation where OCR was never set
up — the prototype degrades instead of refusing to boot.
"""

from __future__ import annotations

import os

from ...domain.ports import RawDocument


class PdfReader:
    """Native PDF, with OCR fallback for scans (FR-03, FR-04, FR-05)."""

    def supports(self, path: str) -> bool:
        return os.path.splitext(path)[1].lower() == ".pdf"

    def read(self, path: str) -> RawDocument:
        from document_processing.pdf_loader import (  # noqa: PLC0415 - lazy on purpose
            detect_document_type,
            extract_tables,
            extract_text_with_ocr_fallback,
            load_pdf,
        )

        document = load_pdf(path)
        try:
            document_type, ocr_needed, _ = detect_document_type(document)
            pages_text = extract_text_with_ocr_fallback(document, ocr_needed)
        finally:
            document.close()

        # The text tolerance was found empirically on the test corpus; it is
        # kept here, at the adapter boundary, rather than buried in the
        # extractor, because it is a property of *how we read these
        # documents*, not of what a PDF is.
        tables_by_page = extract_tables(path, table_settings={"text_x_tolerance": 15})
        tables = [table for page_tables in tables_by_page for table in page_tables]

        return RawDocument(
            file_type="PDF",
            document_type=document_type,
            pages_text=pages_text,
            tables=tables,
            ocr_used=(ocr_needed == "YES"),
        )


class ExcelReader:
    """Excel workbooks (README: formulas resolved via ``data_only=True``)."""

    def supports(self, path: str) -> bool:
        return os.path.splitext(path)[1].lower() in (".xlsx", ".xls")

    def read(self, path: str) -> RawDocument:
        from document_processing.excel_loader import (  # noqa: PLC0415
            excel_sheet_to_table,
            extract_excel_text,
            load_excel,
        )

        workbook = load_excel(path)
        sheets = extract_excel_text(workbook)

        tables = []
        pages_text = []
        for rows in sheets.values():
            table = excel_sheet_to_table(rows)
            tables.append(table)
            pages_text.append(
                "\n".join(
                    "\t".join("" if cell is None else str(cell) for cell in row)
                    for row in table
                )
            )

        return RawDocument(
            file_type="XLSX",
            document_type="SPREADSHEET",
            pages_text=pages_text,
            tables=tables,
            ocr_used=False,
        )


def default_readers() -> list:
    return [PdfReader(), ExcelReader()]
