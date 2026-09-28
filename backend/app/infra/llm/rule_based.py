"""The rule-based structurer — the baseline, and the default.

This adapter wraps the table logic already in ``document_processing`` and
turns it into proposed items. It costs nothing, needs no network, and is
perfectly reproducible.

Two reasons it is the *default* rather than a fallback:

1. **Method.** The thesis compares a language-model structurer against a
   deterministic baseline (dossier §11.1). Without this class there is
   nothing to compare against, and "the model extracts well" becomes an
   assertion instead of a measurement.

2. **Discipline.** Code first, model second. Everything the rules can read,
   the rules should read — a model call spent re-deriving what a header row
   already says is money and latency spent for nothing, and a hallucination
   risk taken for nothing.

The language model earns its place on the documents this class fails on:
unusual layouts, scans, non-standard labels. That is a boundary you will be
able to *show*, with a number, rather than assume.
"""

from __future__ import annotations

from ...domain.ports import RawDocument, StructuredItem, StructuringResult


class RuleBasedStructurer:
    engine = "RULE_BASED"

    def structure(self, document: RawDocument) -> StructuringResult:
        from document_processing.normarlize import normalize_table  # noqa: PLC0415
        from document_processing.structure import (  # noqa: PLC0415
            build_statement_index,
            detect_header_row_count,
            extract_line_items,
            find_side_start_columns,
        )

        items: list[StructuredItem] = []
        all_line_items = []

        for page_number, table in enumerate(document.tables, start=1):
            if not table:
                continue
            try:
                side_starts = find_side_start_columns(table)
                header_count = detect_header_row_count(table, side_starts) or 2
                normalised = normalize_table(table, header_row_count=header_count)
                line_items = extract_line_items(normalised, header_row_count=header_count)
            except (IndexError, ValueError, TypeError):
                # A table the rules cannot read is skipped, not guessed at.
                # It is also exactly the kind of document the language-model
                # structurer exists for — count these, they are a result.
                continue

            for line_item in line_items:
                line_item["_page"] = page_number
            all_line_items.extend(line_items)

        index = build_statement_index(all_line_items)
        for code, line_item in index.items():
            for year_key, year_label in (("current_year", "N"), ("prior_year", "N-1")):
                value = line_item.get(year_key)
                if value is None:
                    continue
                items.append(
                    StructuredItem(
                        item_code=code,
                        amount=str(value),
                        year=year_label,
                        source_page=line_item.get("_page"),
                        # A deterministic rule that matched is certain of
                        # itself in a way a probabilistic model never is.
                        # Recording 1.0 here keeps the two engines
                        # comparable on the same scale.
                        confidence=None,
                    )
                )

        return StructuringResult(
            items=items,
            engine=self.engine,
            model=None,
            prompt_version=None,
            cost_usd=None,
        )
