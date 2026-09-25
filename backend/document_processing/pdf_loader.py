import fitz
import pdfplumber
import pytesseract
from PIL import Image
import io
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

def ocr_page(document, page_number):
    page = document[page_number]
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
    image_bytes = pix.tobytes("png")
    image = Image.open(io.BytesIO(image_bytes))
    text = pytesseract.image_to_string(image)
    return text

def extract_text_with_ocr_fallback(document, ocr_needed):
    pages_text = []
    for page_number in range(len(document)):
        if ocr_needed == "YES":
            text = ocr_page(document, page_number)
        else:
            text = document[page_number].get_text()
        pages_text.append(text)
    return pages_text