"""Spreadsheet export for the financial analysis dashboard."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo


def export_analysis(
    case: dict[str, Any],
    dataset: dict[str, Any],
    ratios: list[dict[str, Any]],
    checks: list[dict[str, Any]],
) -> BytesIO:
    """Build an Excel workbook containing the validated analysis."""

    workbook = Workbook()

    # ------------------------------------------------------------------
    # Styles
    # ------------------------------------------------------------------

    title_font = Font(
        bold=True,
        size=16,
    )

    section_font = Font(
        bold=True,
        size=12,
    )

    header_font = Font(
        bold=True,
    )

    thin_side = Side(
        style="thin",
    )

    border = Border(
        left=thin_side,
        right=thin_side,
        top=thin_side,
        bottom=thin_side,
    )

    header_fill = PatternFill(
        fill_type="solid",
        fgColor="D9EAF7",
    )

    section_fill = PatternFill(
        fill_type="solid",
        fgColor="EAF2F8",
    )

    # ------------------------------------------------------------------
    # Analysis sheet
    # ------------------------------------------------------------------

    sheet = workbook.active
    sheet.title = "Analysis"

    sheet["A1"] = "Financial Analysis"
    sheet["A1"].font = title_font

    # Case information
    sheet["A3"] = "Case Information"
    sheet["A3"].font = section_font
    sheet["A3"].fill = section_fill

    case_information = [
        ("Client", case.get("client")),
        ("Fiscal year", case.get("fiscal_year")),
        ("Case status", case.get("status")),
        ("Validated by", dataset.get("validated_by")),
        ("Validated at", dataset.get("validated_at")),
        ("Validated item count", dataset.get("item_count")),
    ]

    row = 4

    for label, value in case_information:
        sheet.cell(row=row, column=1, value=label)
        sheet.cell(row=row, column=2, value=value)

        sheet.cell(row=row, column=1).font = header_font

        row += 1

    # ------------------------------------------------------------------
    # Ratios
    # ------------------------------------------------------------------

    row += 1

    ratio_section_row = row

    sheet.cell(
        row=ratio_section_row,
        column=1,
        value="Financial Ratios",
    )

    sheet.cell(
        row=ratio_section_row,
        column=1,
    ).font = section_font

    sheet.cell(
        row=ratio_section_row,
        column=1,
    ).fill = section_fill

    row += 1

    ratio_header_row = row

    ratio_headers = [
        "Code",
        "Name",
        "Status",
        "Value",
        "Unit",
        "Reason",
        "Interpretation",
    ]

    for column, header in enumerate(ratio_headers, start=1):
        cell = sheet.cell(
            row=ratio_header_row,
            column=column,
            value=header,
        )

        cell.font = header_font
        cell.fill = header_fill
        cell.border = border
        cell.alignment = Alignment(
            horizontal="center",
            vertical="center",
            wrap_text=True,
        )

    for ratio in ratios:
        row += 1

        interpretation = ratio.get("interpretation") or {}

        values = [
            ratio.get("code"),
            ratio.get("name"),
            ratio.get("status"),
            ratio.get("value"),
            ratio.get("unit"),
            ratio.get("reason"),
            interpretation.get("text"),
        ]

        for column, value in enumerate(values, start=1):
            cell = sheet.cell(
                row=row,
                column=column,
                value=value,
            )

            cell.border = border
            cell.alignment = Alignment(
                vertical="top",
                wrap_text=True,
            )

    ratio_last_row = row

    if ratio_last_row >= ratio_header_row:
        table = Table(
            displayName="RatiosTable",
            ref=(
                f"A{ratio_header_row}:"
                f"G{ratio_last_row}"
            ),
        )

        style = TableStyleInfo(
            name="TableStyleMedium2",
            showFirstColumn=False,
            showLastColumn=False,
            showRowStripes=True,
            showColumnStripes=False,
        )

        table.tableStyleInfo = style
        sheet.add_table(table)

    # ------------------------------------------------------------------
    # Consistency checks
    # ------------------------------------------------------------------

    row += 2

    check_section_row = row

    sheet.cell(
        row=check_section_row,
        column=1,
        value="Consistency Checks",
    )

    sheet.cell(
        row=check_section_row,
        column=1,
    ).font = section_font

    sheet.cell(
        row=check_section_row,
        column=1,
    ).fill = section_fill

    row += 1

    check_header_row = row

    check_headers = [
        "Code",
        "Label",
        "Severity",
        "Passed",
        "Gap",
        "Message",
    ]

    for column, header in enumerate(check_headers, start=1):
        cell = sheet.cell(
            row=check_header_row,
            column=column,
            value=header,
        )

        cell.font = header_font
        cell.fill = header_fill
        cell.border = border
        cell.alignment = Alignment(
            horizontal="center",
            vertical="center",
            wrap_text=True,
        )

    for check in checks:
        row += 1

        values = [
            check.get("code"),
            check.get("label"),
            check.get("severity"),
            check.get("passed"),
            check.get("gap"),
            check.get("message"),
        ]

        for column, value in enumerate(values, start=1):
            cell = sheet.cell(
                row=row,
                column=column,
                value=value,
            )

            cell.border = border
            cell.alignment = Alignment(
                vertical="top",
                wrap_text=True,
            )

    check_last_row = row

    if check_last_row >= check_header_row:
        table = Table(
            displayName="ChecksTable",
            ref=(
                f"A{check_header_row}:"
                f"F{check_last_row}"
            ),
        )

        style = TableStyleInfo(
            name="TableStyleMedium4",
            showFirstColumn=False,
            showLastColumn=False,
            showRowStripes=True,
            showColumnStripes=False,
        )

        table.tableStyleInfo = style
        sheet.add_table(table)

    # ------------------------------------------------------------------
    # Validated Dataset sheet
    # ------------------------------------------------------------------

    dataset_sheet = workbook.create_sheet(
        "Validated Dataset"
    )

    dataset_sheet["A1"] = "Validated Dataset"
    dataset_sheet["A1"].font = title_font

    dataset_sheet["A3"] = "Validated by"
    dataset_sheet["B3"] = dataset.get("validated_by")

    dataset_sheet["A4"] = "Validated at"
    dataset_sheet["B4"] = dataset.get("validated_at")

    dataset_sheet["A5"] = "Item count"
    dataset_sheet["B5"] = dataset.get("item_count")

    dataset_sheet["A3"].font = header_font
    dataset_sheet["A4"].font = header_font
    dataset_sheet["A5"].font = header_font

    dataset_header_row = 7

    dataset_sheet.cell(
        row=dataset_header_row,
        column=1,
        value="Item code",
    )

    dataset_sheet.cell(
        row=dataset_header_row,
        column=2,
        value="Amount",
    )

    for column in range(1, 3):
        cell = dataset_sheet.cell(
            row=dataset_header_row,
            column=column,
        )

        cell.font = header_font
        cell.fill = header_fill
        cell.border = border
        cell.alignment = Alignment(
            horizontal="center",
            vertical="center",
        )

    amounts = dataset.get("amounts") or {}

    dataset_row = dataset_header_row

    for item_code, amount in amounts.items():
        dataset_row += 1

        dataset_sheet.cell(
            row=dataset_row,
            column=1,
            value=item_code,
        )

        amount_cell = dataset_sheet.cell(
            row=dataset_row,
            column=2,
        )

        try:
            amount_cell.value = float(
                Decimal(str(amount))
            )
        except (InvalidOperation, ValueError, TypeError):
            amount_cell.value = amount

        amount_cell.number_format = '#,##0.00'

        for column in range(1, 3):
            cell = dataset_sheet.cell(
                row=dataset_row,
                column=column,
            )

            cell.border = border
            cell.alignment = Alignment(
                vertical="top",
            )

    dataset_last_row = dataset_row

    if dataset_last_row > dataset_header_row:
        table = Table(
            displayName="ValidatedDatasetTable",
            ref=(
                f"A{dataset_header_row}:"
                f"B{dataset_last_row}"
            ),
        )

        style = TableStyleInfo(
            name="TableStyleMedium9",
            showFirstColumn=False,
            showLastColumn=False,
            showRowStripes=True,
            showColumnStripes=False,
        )

        table.tableStyleInfo = style

        dataset_sheet.add_table(table)

    # ------------------------------------------------------------------
    # General worksheet formatting
    # ------------------------------------------------------------------

    for current_sheet in workbook.worksheets:

        current_sheet.freeze_panes = "A8"

        for row_cells in current_sheet.iter_rows():
            for cell in row_cells:
                cell.alignment = Alignment(
                    vertical="top",
                    wrap_text=True,
                )

        for column_cells in current_sheet.columns:
            maximum_length = 0

            for cell in column_cells:
                value = (
                    ""
                    if cell.value is None
                    else str(cell.value)
                )

                maximum_length = max(
                    maximum_length,
                    len(value),
                )

            column_index = column_cells[0].column

            current_sheet.column_dimensions[
                get_column_letter(column_index)
            ].width = min(
                maximum_length + 2,
                60,
            )

        current_sheet.sheet_view.showGridLines = False

    # Specific useful widths
    sheet.column_dimensions["A"].width = 22
    sheet.column_dimensions["B"].width = 28
    sheet.column_dimensions["C"].width = 16
    sheet.column_dimensions["D"].width = 16
    sheet.column_dimensions["E"].width = 16
    sheet.column_dimensions["F"].width = 35
    sheet.column_dimensions["G"].width = 50

    dataset_sheet.column_dimensions["A"].width = 30
    dataset_sheet.column_dimensions["B"].width = 22

    # ------------------------------------------------------------------
    # Save workbook into memory
    # ------------------------------------------------------------------

    output = BytesIO()

    workbook.save(output)

    output.seek(0)

    return output