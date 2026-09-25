from document_processing.pdf_loader import looks_like_number , clean_number_string


def normalize_number(value):
    if value is None:
        return None

    text = value.strip()

    if text == "-" or text =="":
        return 0

    try:
        return int(text)
    except ValueError:
        return None

def is_normalizable_cell(value):
    if value is None:
        return False
    stripped = value.strip()
    return stripped == "-" or looks_like_number(value)

MONETARY_HEADER_KEYWORDS = ["EXERCICE", "NET", "BRUT", "AMORT"]


def merge_header_rows(table, header_row_count=2):
    header_rows = table[:header_row_count]
    num_columns = len(table[0])
    merged = []
    for col_index in range(num_columns):
        parts = []
        for row in header_rows:
            if col_index < len(row) and row[col_index]:
                parts.append(row[col_index])
        merged.append(" ".join(parts))
    return merged


def classify_monetary_columns(merged_headers):
    monetary_columns = []
    for header_text in merged_headers:
        header_upper = header_text.upper()
        is_monetary = any(keyword in header_upper for keyword in MONETARY_HEADER_KEYWORDS)
        monetary_columns.append(is_monetary)
    return monetary_columns


def normalize_table(table, header_row_count=2):
    if not table:
        return []

    merged_headers = merge_header_rows(table, header_row_count)
    monetary_columns = classify_monetary_columns(merged_headers)
    content_guess = guess_monetary_by_content(table, header_row_count)

    for col_index, header_text in enumerate(merged_headers):
        header_says_monetary = monetary_columns[col_index]
        content_says_monetary = col_index < len(content_guess) and content_guess[col_index]
        if header_says_monetary != content_says_monetary:
            print(
                f"WARNING: column {col_index} (header: '{header_text}') "
                f"header-based classification={header_says_monetary} "
                f"but content-based guess={content_says_monetary} — check this document's header wording"
            )

    normalized_table = []
    for row_index, row in enumerate(table):
        if row_index < header_row_count:
            normalized_table.append(row)
            continue

        normalized_row = []
        for col_index, cell in enumerate(row):
            is_monetary_column = col_index < len(monetary_columns) and monetary_columns[col_index]
            if is_monetary_column and is_normalizable_cell(cell):
                normalized_row.append(normalize_number(clean_number_string(cell)))
            else:
                normalized_row.append(cell)
        normalized_table.append(normalized_row)

    return normalized_table

def guess_monetary_by_content(table, header_row_count=2):
    data_rows = table[header_row_count:]
    if not data_rows:
        return []

    num_columns = len(table[0])
    guesses = []
    for col_index in range(num_columns):
        numeric_like = 0
        total_seen = 0
        for row in data_rows:
            if col_index >= len(row):
                continue
            cell = row[col_index]
            if cell is None or cell.strip() == "":
                continue
            total_seen += 1
            if is_normalizable_cell(cell):
                numeric_like += 1
        guesses.append(total_seen > 0 and numeric_like / total_seen >= 0.6)
    return guesses


