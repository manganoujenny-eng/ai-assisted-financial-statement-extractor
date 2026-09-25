import  os
from document_processing.pdf_loader import load_pdf
from document_processing.excel_loader import load_excel

def detect_file_type(path):
    extension = os.path.splitext(path)[1].lower()
    if extension == ".pdf":
        return "PDF"
    elif extension in (".xlsx" , ".xls"):
        return "XLSX"
    else:
        return "UNSUPPORTED"

def load_document(path):
    file_type = detect_file_type(path)
    if file_type == "PDF":
        document = load_pdf(path)
    elif file_type == "XLSX":
        document = load_excel(path)
    else:
        raise ValueError(f"Unsupported file type: {path}")
    return document , file_type