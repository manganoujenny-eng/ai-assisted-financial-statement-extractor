import os

# Tesseract's own internal threading (OpenMP) fights with itself badly when
# several pages are OCR'd at once — on a multi-page scan that contention can
# cost more time than the OCR. One thread per Tesseract process, and the
# parallelism comes from running several pages at once instead (read_pdf
# below). Must be set before the first tesseract process starts.
os.environ.setdefault("OMP_THREAD_LIMIT", "1")

import io
import logging
from concurrent.futures import ThreadPoolExecutor

import fitz
import pdfplumber
import pytesseract
from PIL import Image

log = logging.getLogger(__name__)
def load_pdf(path):
    document = fitz.open(path)
    return document
def detect_document_type(document):
    total_text=""
    for page in document:
        total_text += page.get_text()
    text_available = bool(total_text.strip())
    if text_available:
        document_type = "NATIVE_PDF"
        ocr_needed = "NO"
    else:
        document_type = "POSSIBLY_SCANNED"
        ocr_needed = "YES"
    return document_type, ocr_needed , text_available

def extract_text(document):
    pages_text = []
    for page in document:
        pages_text.append(page.get_text())
    return pages_text

def extract_tables(path , table_settings=None ):
    tables_by_page = []

    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables(table_settings = table_settings)
            tables_by_page.append(tables)
    return tables_by_page

def looks_like_number(value):
    if value is None:
        return False
    stripped = value.strip()
    if stripped == "":
        return False
    body = stripped[1:] if stripped.startswith("-") else stripped
    body = body.replace(" ", "")
    return body.isdigit()

def clean_number_string(raw):
    return raw.strip().replace(" ", "")

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# These statements are French (SYSCOHADA). Tesseract defaults to English
# when no lang is given, which is a second, independent reason OCR text
# used to come out mangled on a scan — not just the missing table step
# below. "fra" needs the French language pack installed alongside
# Tesseract (tesseract-ocr-fra); OCR_LANGUAGE falls back to English by
# itself if that pack isn't there, rather than crashing extraction.
OCR_LANGUAGE = "fra"


def _run_ocr(image, to_data=False):
    kwargs = {"lang": OCR_LANGUAGE}
    try:
        if to_data:
            return pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT, **kwargs)
        return pytesseract.image_to_string(image, **kwargs)
    except pytesseract.TesseractError as exc:
        print(f"WARNING: OCR language '{OCR_LANGUAGE}' unavailable ({exc}) — falling back to English")
        if to_data:
            return pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        return pytesseract.image_to_string(image)


def _page_image(document, page_number, zoom=3):
    page = document[page_number]
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    image_bytes = pix.tobytes("png")
    return Image.open(io.BytesIO(image_bytes))


def ocr_page(document, page_number):
    image = _page_image(document, page_number)
    return _run_ocr(image)


def extract_text_with_ocr_fallback(document, ocr_needed):
    pages_text = []
    for page_number in range(len(document)):
        if ocr_needed == "YES":
            text = ocr_page(document, page_number)
        else:
            text = document[page_number].get_text()
        pages_text.append(text)
    return pages_text


# --- OCR table reconstruction ------------------------------------------
# find_side_start_columns() and the rest of document_processing/structure.py
# were written against pdfplumber's output: a table is a list of rows, each
# a list of cells, columns lined up the same way in every row. pdfplumber
# gets that for free from the PDF's own vector/text layer — on a scanned
# page there is no such layer for it to read, which is the entire reason
# extract_tables() always came back empty for a scan, independent of the
# OCR above actually working for plain text. These functions rebuild a
# table of that same shape from Tesseract's word-level positions instead,
# so a scanned page can reach find_side_start_columns()/extract_line_items()
# the same way a native page always could.
def ocr_page_table(document, page_number):
    image = _page_image(document, page_number)
    data = _run_ocr(image, to_data=True)
    return words_to_table(data)


def words_to_table(data):
    """Turns pytesseract's word-level image_to_data output into a table.

    Nothing here knows about REF, LIBELLE or any SYSCOHADA column name —
    that is still find_side_start_columns()'s job, applied afterwards, the
    same as it is for a native PDF. All this does is what a person reading
    the page would do without being told the layout: words close together
    vertically are one row; a gap between two words that keeps showing up
    at roughly the same x position across many rows is a column boundary,
    not just extra space inside one long label.
    """
    words = _words_from_image_data(data)
    if not words:
        return []

    rows = _group_words_into_rows(words)
    column_starts = _detect_column_starts(rows)
    return _assemble_rows(rows, column_starts)


def _words_from_image_data(data):
    words = []
    for i in range(len(data["text"])):
        text = data["text"][i].strip()
        if not text:
            continue
        words.append(
            {
                "text": text,
                "left": data["left"][i],
                "width": data["width"][i],
                "top": data["top"][i],
                "height": data["height"][i],
            }
        )
    return words


def _group_words_into_rows(words):
    # Grouped by vertical position, not Tesseract's own block/par/line
    # numbering: on a skewed or low-resolution scan Tesseract regularly
    # splits one printed line into several differently-numbered blocks,
    # which would otherwise turn one table row into several and misalign
    # every row beneath it.
    ordered = sorted(words, key=lambda w: w["top"])
    heights = sorted(w["height"] for w in ordered)
    tolerance = max(heights[len(heights) // 2] * 0.6, 1)

    rows = []
    current = []
    row_top = None
    for word in ordered:
        if current and abs(word["top"] - row_top) > tolerance:
            rows.append(current)
            current = []
        current.append(word)
        row_top = sum(w["top"] for w in current) / len(current)
    if current:
        rows.append(current)

    for row in rows:
        row.sort(key=lambda w: w["left"])
    return rows


def _detect_column_starts(rows):
    # A real column boundary is a gap between two words that recurs at
    # roughly the same x position across many rows — a gap that appears
    # only once is as likely to be a long label with extra space in it as
    # a column edge. The character-width estimate both thresholds are
    # built from comes from the same median word height the rows were
    # grouped by, so both steps move together as scan resolution changes.
    if not rows:
        return []

    heights = sorted(word["height"] for row in rows for word in row)
    char_width = heights[len(heights) // 2] * 0.6
    gap_threshold = char_width * 4

    boundaries = []
    for row in rows:
        for left_word, right_word in zip(row, row[1:]):
            gap = right_word["left"] - (left_word["left"] + left_word["width"])
            if gap >= gap_threshold:
                boundaries.append(right_word["left"])
    boundaries.sort()

    clusters = []
    for boundary in boundaries:
        if clusters and boundary - clusters[-1][-1] <= char_width * 2:
            clusters[-1].append(boundary)
        else:
            clusters.append([boundary])

    minimum_support = max(3, round(len(rows) * 0.1))
    column_starts = {min(word["left"] for row in rows for word in row)}
    column_starts.update(
        sum(cluster) // len(cluster)
        for cluster in clusters
        if len(cluster) >= minimum_support
    )
    return sorted(column_starts)


def _assemble_rows(rows, column_starts):
    # column_starts always has at least one entry once rows is non-empty
    # (_detect_column_starts seeds it with the leftmost word position), and
    # words_to_table() already returns [] before calling this when there
    # are no words at all — so there is no "no columns found" case to
    # special-case here.
    table = []
    for row in rows:
        cells = [None] * len(column_starts)
        for word in row:
            column = _column_for(word["left"], column_starts)
            cells[column] = (
                word["text"] if cells[column] is None else f'{cells[column]} {word["text"]}'
            )
        table.append(cells)
    return table


def _column_for(left, column_starts):
    # Which bucket this x falls into: the last column boundary at or
    # before it, not whichever boundary happens to be numerically closest
    # — a word just past a boundary belongs to the column that starts
    # there, however near the previous column's words are.
    column = 0
    for index, start in enumerate(column_starts):
        if start <= left:
            column = index
        else:
            break
    return column


def extract_tables_with_ocr_fallback(document, path, ocr_needed, table_settings=None):
    if ocr_needed != "YES":
        return extract_tables(path, table_settings=table_settings)

    tables_by_page = []
    for page_number in range(len(document)):
        table = ocr_page_table(document, page_number)
        tables_by_page.append([table] if table else [])
    return tables_by_page



# --- Large documents ----------------------------------------------------
# A full SYSCOHADA package (liasse) is easily 30-100 pages, often a mix of
# native pages and scanned ones (signed pages, annexes). The functions above
# decide OCR for the whole file at once and OCR every scanned page twice
# (once for text, once for the table) — on a 20-page scan that was ~9
# minutes. read_pdf() below:
#   * decides per page: a page with a real text layer is read natively, only
#     the pages without one are OCR'd;
#   * OCRs each scanned page ONCE (image_to_data), and builds both the
#     page's text and its table from that same result;
#   * runs several pages' OCR in parallel (pytesseract starts a separate
#     tesseract process per call, so threads give real parallelism), while
#     rendering stays in one thread because PyMuPDF is not thread-safe;
#   * renders pages in small batches, so memory stays flat however many
#     pages the document has;
#   * logs progress per page, so a long extraction is visibly alive in the
#     Flask console.

#: Pages with fewer non-blank characters than this in their text layer are
#: treated as scanned. A scan with a printed page number or a stamp can carry
#: a few characters of text and still need OCR.
MIN_NATIVE_TEXT_CHARS = 20

#: Parallel tesseract processes. Each needs roughly 100-300 MB at zoom 3.
OCR_WORKERS = int(os.environ.get("OCR_WORKERS", max(1, min(4, (os.cpu_count() or 2) - 1))))


def _text_from_image_data(data):
    """Plain text from image_to_data, line by line, as image_to_string gives."""
    lines = {}
    for i, word in enumerate(data["text"]):
        word = word.strip()
        if not word:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines.setdefault(key, []).append(word)
    return "\n".join(" ".join(words) for _, words in sorted(lines.items()))


def _ocr_image(image):
    data = _run_ocr(image, to_data=True)
    return _text_from_image_data(data), words_to_table(data)


def read_pdf(path, table_settings=None):
    """Read every page of a PDF, natively or by OCR, page by page.

    Returns (document_type, ocr_used, pages_text, tables_by_page), where
    tables_by_page has one list of tables per page, in page order — the same
    shapes extract_text_with_ocr_fallback / extract_tables_with_ocr_fallback
    return, so the callers do not change what they do with them.
    """
    document = fitz.open(path)
    try:
        page_count = len(document)
        native_text = [document[i].get_text() for i in range(page_count)]
        scanned = [
            i for i in range(page_count)
            if len("".join(native_text[i].split())) < MIN_NATIVE_TEXT_CHARS
        ]
        scanned_set = set(scanned)
        log.info(
            "%s: %d page(s), %d need OCR", os.path.basename(path), page_count, len(scanned)
        )

        pages_text = list(native_text)
        tables_by_page = [[] for _ in range(page_count)]

        # Native pages: pdfplumber, only on the pages that have a text layer.
        native_pages = [i for i in range(page_count) if i not in scanned_set]
        if native_pages:
            with pdfplumber.open(path) as pdf:
                for i in native_pages:
                    tables_by_page[i] = pdf.pages[i].extract_tables(
                        table_settings=table_settings
                    )

        # Scanned pages: render in batches, OCR each batch in parallel.
        if scanned:
            batch_size = max(1, OCR_WORKERS)
            done = 0
            with ThreadPoolExecutor(max_workers=OCR_WORKERS) as pool:
                for start in range(0, len(scanned), batch_size):
                    batch = scanned[start:start + batch_size]
                    images = [_page_image(document, i) for i in batch]
                    for i, (text, table) in zip(batch, pool.map(_ocr_image, images)):
                        pages_text[i] = text
                        tables_by_page[i] = [table] if table else []
                    done += len(batch)
                    log.info(
                        "%s: OCR %d/%d page(s) done",
                        os.path.basename(path), done, len(scanned),
                    )
    finally:
        document.close()

    if not scanned:
        document_type = "NATIVE_PDF"
    elif len(scanned) == page_count:
        document_type = "POSSIBLY_SCANNED"
    else:
        document_type = "MIXED"
    return document_type, bool(scanned), pages_text, tables_by_page



def probe_pdf(path):
    """(page_count, needs_ocr) without OCR — fast enough to run at upload.

    Reads only the text layer of each page. needs_ocr is True when any page
    has (almost) no text layer, the same rule read_pdf() uses to decide
    which pages to OCR.
    """
    document = fitz.open(path)
    try:
        page_count = len(document)
        needs_ocr = any(
            len("".join(document[i].get_text().split())) < MIN_NATIVE_TEXT_CHARS
            for i in range(page_count)
        )
    finally:
        document.close()
    return page_count, needs_ocr