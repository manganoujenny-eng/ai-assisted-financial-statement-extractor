from document_processing.normarlize import merge_header_rows, classify_monetary_columns
import re

def extract_year_values(side_values, side_headers):
    monetary_flags = classify_monetary_columns(side_headers)
    monetary_positions = [i for i, is_monetary in enumerate(monetary_flags) if is_monetary]

    if len(monetary_positions) >= 2:
        current_year = side_values[monetary_positions[-2]]
        prior_year = side_values[monetary_positions[-1]]
    elif len(monetary_positions) == 1:
        current_year = side_values[monetary_positions[0]]
        prior_year = None
    else:
        current_year = None
        prior_year = None

    return current_year, prior_year

def find_side_start_columns(table):
    header_row = table[0]
    return [i for i, cell in enumerate(header_row) if cell == "REF"]


def split_row_into_sides(row, side_starts):
    sides = []
    for i, start in enumerate(side_starts):
        end = side_starts[i + 1] if i + 1 < len(side_starts) else len(row)
        sides.append(row[start:end])
    return sides


def build_line_item(side_values, side_headers):
    code = side_values[0]
    if code is None or str(code).strip() == "":
        return None

    label = side_values[1]
    fields = {}
    for header_name, value in zip(side_headers[2:], side_values[2:]):
        if header_name:
            fields[header_name] = value

    current_year, prior_year = extract_year_values(side_values, side_headers)

    return {
        "code": code,
        "label": label,
        "current_year": current_year,
        "prior_year": prior_year,
        "fields": fields,
    }

def extract_line_items(table, header_row_count=2):
    merged_headers = merge_header_rows(table, header_row_count)
    starts = find_side_start_columns(table)
    header_sides = split_row_into_sides(merged_headers, starts)

    line_items = []
    for row in table[header_row_count:]:
        row_sides = split_row_into_sides(row, starts)
        for values, headers in zip(row_sides, header_sides):
            item = build_line_item(values, headers)
            if item is not None:
                line_items.append(item)

    return line_items

CODE_PATTERN = re.compile(r"^[A-Z]{2}$")

def detect_header_row_count(table, side_starts):
    for row_index, row in enumerate(table):
        for start in side_starts:
            if start < len(row) and row[start] and CODE_PATTERN.match(str(row[start]).strip()):
                return row_index
    return 0


def build_statement_index(all_line_items):
    index = {}
    for item in all_line_items:
        code = item["code"]
        if code in index:
            print(f"WARNING: duplicate code '{code}' found — keeping first occurrence, check source document")
            continue
        index[code] = item
    return index