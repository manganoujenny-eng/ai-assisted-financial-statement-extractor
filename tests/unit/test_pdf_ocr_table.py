"""words_to_table() turns pytesseract's word-level image_to_data output into
the same shape pdfplumber.extract_tables() hands back: a list of rows, each
a list of cells, columns lined up consistently across rows.

These tests build that image_to_data dict by hand instead of running
Tesseract against a real image. That keeps them independent of Tesseract
being installed and of any particular scan's OCR quality (which — see the
real client4 document — can be bad enough that even the text itself is
wrong). What's under test here is purely the geometry: given word boxes at
given pixel positions, does the row/column reconstruction come out right.
"""

from __future__ import annotations

from document_processing.pdf_loader import words_to_table


def _image_data(rows_of_words, height=20):
    """rows_of_words: list of rows, each a list of (text, left) tuples.

    Every word gets the same height (so the row-grouping tolerance and the
    column char-width estimate are both driven by one known number) and a
    width derived from its own text length, which is all the real
    pytesseract output is used for downstream.
    """
    text, left, top, width, ht = [], [], [], [], []
    for row_index, words in enumerate(rows_of_words):
        row_top = row_index * (height + 5)
        for word_text, word_left in words:
            text.append(word_text)
            left.append(word_left)
            top.append(row_top)
            width.append(len(word_text) * 8)
            ht.append(height)
    return {"text": text, "left": left, "top": top, "width": width, "height": ht}


def test_empty_input_produces_no_rows():
    assert words_to_table({"text": [], "left": [], "top": [], "width": [], "height": []}) == []


def test_blank_tokens_are_ignored_like_pytesseract_blanks_are():
    data = _image_data([[("", 0), ("REF", 100)]])
    table = words_to_table(data)
    assert table == [["REF"]]


def test_recurring_gaps_become_column_boundaries():
    # Three columns, four rows, the same column start positions in every
    # row — a real, repeated column edge, not an accident of one long
    # label having extra space in it. Columns are spaced 200px apart so
    # that no word's own width (the longest here is 9 chars, 72px) can
    # eat far enough into the gap to hide the boundary.
    rows = [
        [("REF", 0), ("LIBELLE", 200), ("NET", 400)],
        [("AA", 0), ("Terrains", 200), ("1500", 400)],
        [("AB", 0), ("Batiments", 200), ("2500", 400)],
        [("AC", 0), ("Materiel", 200), ("3200", 400)],
    ]
    data = _image_data(rows)
    table = words_to_table(data)

    assert len(table) == 4
    assert all(len(row) == 3 for row in table)
    assert table[0] == ["REF", "LIBELLE", "NET"]
    assert table[1] == ["AA", "Terrains", "1500"]
    assert table[3] == ["AC", "Materiel", "3200"]


def test_a_gap_seen_only_once_is_not_treated_as_a_column():
    # Three rows that line up on one real column boundary (200px, recurs
    # three times) plus one row with an extra, one-off wide gap inside its
    # own label — a long line's internal spacing, not a second column.
    rows = [
        [("REF", 0), ("LIBELLE", 200)],
        [("AA", 0), ("Terrains", 200)],
        [("AB", 0), ("Long", 200), ("label", 350)],  # same cell, wide internal gap
    ]
    data = _image_data(rows)
    table = words_to_table(data)

    # Still two columns: the one-off gap inside row 3 didn't create a third.
    assert all(len(row) == 2 for row in table)
    assert table[2] == ["AB", "Long label"]


def test_multi_word_cell_is_rejoined_with_a_space():
    rows = [
        [("REF", 0), ("LIBELLE", 200)],
        [("AA", 0), ("Terrains", 200), ("batis", 270)],
        [("AB", 0), ("Materiel", 200)],
    ]
    data = _image_data(rows)
    table = words_to_table(data)

    assert table[1][0] == "AA"
    assert table[1][1] == "Terrains batis"


def test_words_on_the_same_visual_line_stay_one_row_even_with_jitter():
    # Real OCR rarely reports the exact same top for every word on one
    # printed line. A few pixels of jitter should not split one row into
    # two. Three rows so the REF/LIBELLE gap clears the minimum-support
    # bar and is treated as a real column rather than being merged away.
    rows = [
        [("REF", 0), ("LIBELLE", 200)],
        [("AA", 0), ("Terrains", 200)],
        [("AB", 0), ("Materiel", 200)],
    ]
    data = _image_data(rows)
    # Nudge one word's top by a few pixels directly, bypassing the
    # helper's one-top-per-row convenience, to simulate OCR jitter.
    data["top"][1] = data["top"][1] + 3

    table = words_to_table(data)
    assert len(table) == 3
    assert table[0] == ["REF", "LIBELLE"]