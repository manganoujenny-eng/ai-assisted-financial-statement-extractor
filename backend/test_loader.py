import os
from document_processing.document_loader import load_document
from document_processing.excel_loader import extract_excel_text, excel_sheet_to_table
from document_processing.normarlize import  normalize_table
from document_processing.pdf_loader import detect_document_type ,  extract_tables ,  extract_text_with_ocr_fallback
from document_processing.structure import extract_line_items, find_side_start_columns, detect_header_row_count, build_statement_index
from document_processing.output_writer import build_extraction_result, save_extraction_result
test_paths = [
    "../data/test_documents/PKG001/ETAT FINANCIER TEST1.xlsx",
    "../data/test_documents/PKG001/ETAT FINANCIER TEST1.pdf",
     "../data/test_documents/PKG001/ETAT FINANCIER TEST2.pdf" ,
    "../data/test_documents/PKG001/DATA ANALYTICS.docx"
]
EXTRACTED_DIR = "../data/extracted"
for path in test_paths:
     print("Testing " + path)
     try:
         document,file_type = load_document(path)
         print(f"Detected file type: {file_type}")

         if file_type == "PDF":
             document_type, ocr_needed , text_available = detect_document_type(document)
             print("PDF loaded successfully")
             print(f"File Name : {os.path.basename(document.name)}")
             print(f"Number of pages: {len(document)}")
             print("Text available:", "YES" if text_available else "NO")
             print("Document type :" , document_type )
             print("OCR required:", ocr_needed)

             pages_text = extract_text_with_ocr_fallback(document, ocr_needed)
             print("Number of pages extracted:", len(pages_text))
             for i , page_text in enumerate(pages_text , start=1):
                 print(f"-----Page {i}-----")
                 print(page_text)

             tables_by_page = extract_tables(path , table_settings={"text_x_tolerance": 15})
             print("Tables found per page:" , [len(t) for t in tables_by_page])
             all_line_items = []
             for i, tables in enumerate(tables_by_page, start=1):
                 print(f"--- Page {i}: {len(tables)} table(s) ---")
                 for t_index, table in enumerate(tables, start=1):
                     print(f"Table {t_index}:")
                     normalized_table = normalize_table(table)
                     line_items = extract_line_items(normalized_table)
                     print(f"Extracted {len(line_items)} line items:")
                     for item in line_items:
                         print(item)
                     all_line_items.extend(line_items)
             line_items_index = build_statement_index(all_line_items)
             result = build_extraction_result(path, file_type, line_items_index, raw_text=pages_text)
             output_path = save_extraction_result(result, EXTRACTED_DIR)
             print(f"Saved extraction result to: {output_path}")
             document.close()

         elif file_type == "XLSX":
             print("Excel loaded successfully")
             print(f"Sheets Name: {document.sheetnames}")
             print(f"Number of Sheets: {len(document.sheetnames)}")

             sheets_data = extract_excel_text(document)
             all_line_items = []
             for sheet_name, rows in sheets_data.items():
                 print(f"---------Sheet Name: {sheet_name}----------")
                 print(f"Number of rows: {len(rows)}")
                 for row in rows:
                     print(row)

                 table = excel_sheet_to_table(rows)
                 side_starts = find_side_start_columns(table)
                 header_count = detect_header_row_count(table, side_starts)
                 print(f"Detected header row count: {header_count}")
                 normalized_table = normalize_table(table, header_row_count=header_count)
                 line_items = extract_line_items(normalized_table, header_row_count=header_count)
                 print(f"Extracted {len(line_items)} line items:")
                 for item in line_items:
                     print(item)
                 all_line_items.extend(line_items)
             line_items_index = build_statement_index(all_line_items)
             result = build_extraction_result(path, file_type, line_items_index)
             output_path = save_extraction_result(result, EXTRACTED_DIR)
             print(f"Saved extraction result to: {output_path}")


     except ValueError as e:
         print("  Error:", e)
     print()
















