"""document_processing.structure had no test coverage at all before this —
worth closing while we're here, since it is exactly the piece that failed
on a real document (SOCATRANS_2023.xlsx) rather than on a synthetic one.

Root cause: find_side_start_columns() only ever looked at table[0] for the
cells literally equal to "REF". Every fixture used so far happens to put
that header on the very first physical row, which is why the bug went
unnoticed. A real SYSCOHADA export instead opens with a title line, an
entity/ID block and a disclaimer sentence — normal front matter — before
the REF row, and that one document came back with zero extracted items and
an ExtractionFailed("no usable item found in the document"), even though
nothing was wrong with its numbers (confirmed separately: once the header
row is found, all 198 fields extract cleanly and every consistency check
passes).

The fix makes find_side_start_columns scan forward for the first row that
actually contains "REF", instead of assuming it is row 0.
"""

from __future__ import annotations

from document_processing.structure import extract_line_items, find_side_start_columns


def test_find_side_start_columns_still_works_when_ref_is_the_first_row():
    """The simple fixtures' shape must keep working unchanged."""
    table = [
        ["REF", "ACTIF", "NET 2024", "REF", "PASSIF", "NET 2024"],
        ["AD", "Immobilisations", "100", "CA", "Capital", "200"],
    ]
    assert find_side_start_columns(table) == [0, 3]


def test_find_side_start_columns_skips_leading_title_rows():
    """SOCATRANS_2023.xlsx's actual shape: a title, an entity/ID block and a
    disclaimer line sit above the REF row. The old code only ever checked
    table[0] ('BILAN AU 31 DÉCEMBRE 2023') and found nothing there, so it
    silently returned [] and every line item downstream was dropped.
    """
    table = [
        ["BILAN AU 31 DÉCEMBRE 2023", None, None, None],
        ["Désignation de l'entité : SOCATRANS LOGISTIQUE SARL", None, None, None],
        ["Numéro d'identification : M041512000873K", None, None, None],
        [None, None, None, None],
        ["REF", "ACTIF", "REF", "PASSIF"],
        ["AD", "Immobilisations incorporelles", "CA", "Capital"],
    ]
    assert find_side_start_columns(table) == [0, 2]


def test_extract_line_items_reads_a_balance_sheet_with_front_matter():
    """End-to-end through extract_line_items: the exact shape that produced
    zero items from SOCATRANS_2023.xlsx now yields the real line items on
    both sides of the balance sheet.
    """
    table = [
        ["BILAN AU 31 DÉCEMBRE 2023", None, None, None, None, None],
        ["Désignation de l'entité : SOCATRANS LOGISTIQUE SARL", None, None, None, None, None],
        [None, None, None, None, None, None],
        ["REF", "ACTIF", "NET\n2023", "REF", "PASSIF", "NET\n2023"],
        ["AD", "Immobilisations incorporelles", "19240530", "CA", "Capital", "500000000"],
        ["AE", "Frais de développement", "0", "CB", "Apporteurs capital non appelé (-)", "0"],
    ]

    items = extract_line_items(table, header_row_count=4)
    by_code = {item["code"]: item for item in items}

    assert by_code["AD"]["current_year"] == "19240530"
    assert by_code["AD"]["label"] == "Immobilisations incorporelles"
    assert by_code["CA"]["current_year"] == "500000000"
    assert by_code["CA"]["label"] == "Capital"

def test_find_side_start_columns_falls_back_to_the_code_column_when_ref_is_gone():
    """A scanned page read through OCR: "REF" itself got mangled into
    noise, but the column of two-letter codes beneath it (AD, AE, AF...)
    came through clean — a short run of capitals OCRs far more reliably
    than a whole word does. The literal-match branch finds nothing, so
    this exercises the fallback on its own.
    """
    table = [
        ["RTF", "ACTIF", "NET 2024"],  # "REF" itself OCR'd wrong
        ["AD", "Immobilisations", "100"],
        ["AE", "Frais de developpement", "0"],
        ["AF", "Brevets", "50"],
    ]
    assert find_side_start_columns(table) == [0]


def test_find_side_start_columns_fallback_ignores_a_single_coincidental_match():
    """One cell that happens to look like a two-letter code is not a
    column of codes — the same "it has to recur" rule the OCR table
    reconstruction itself uses for column boundaries. Without this, any
    stray OCR fragment ("OK", "NO"...) sitting in some column once would
    get mistaken for the side-start column.
    """
    table = [
        ["Designation", "Montant", "Note"],
        ["Terrains", "100", "NO"],  # one coincidental two-letter cell
        ["Batiments", "200", None],
        ["Materiel", "300", None],
    ]
    assert find_side_start_columns(table) == []


def test_find_side_start_columns_prefers_a_literal_ref_match_when_both_exist():
    """If "REF" did survive OCR, use it — it is the stronger, unambiguous
    signal. The fallback only ever runs when the literal search finds
    nothing at all.
    """
    table = [
        ["REF", "ACTIF", "NET 2024"],
        ["AD", "Immobilisations", "100"],
        ["AE", "Frais de developpement", "0"],
        ["AF", "Brevets", "50"],
    ]
    assert find_side_start_columns(table) == [0]