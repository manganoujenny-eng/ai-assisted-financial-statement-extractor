"""The case lifecycle, the correction rules, and one architecture test.

The last test in this file is unusual and worth your attention: it does not
test behaviour, it tests *structure*. It fails if anyone — including you in
week 6, in a hurry — imports Flask or SQLAlchemy into the domain layer.

A rule nobody enforces is a rule that erodes. This one enforces itself.
"""

import ast
from pathlib import Path

import pytest

from app.domain import entities as E
from app.domain.interpretation import interpret
from app.domain.ratios import compute_one, definition_of
from app.domain.value_objects import Amount


class TestCaseLifecycle:
    def test_a_new_case_starts_at_created(self):
        case = E.AnalysisCase(client="ACME SARL", fiscal_year=2024)
        assert case.status == E.CREATED

    def test_a_forbidden_transition_is_refused_by_the_domain(self):
        # Not by a hidden button, not by a controller: here, where an HTTP
        # client, a script and a test all meet the same answer.
        case = E.AnalysisCase(client="ACME SARL", fiscal_year=2024)
        with pytest.raises(E.DomainError, match="not allowed"):
            case.transition_to(E.VALIDATED)

    def test_the_normal_path_runs_through(self):
        case = E.AnalysisCase(client="ACME SARL", fiscal_year=2024)
        for state in (E.EXTRACTING, E.EXTRACTED, E.UNDER_REVIEW, E.VALIDATED, E.ANALYSED):
            case.transition_to(state)
        assert case.status == E.ANALYSED

    def test_an_analysed_case_can_be_reopened(self):
        case = E.AnalysisCase(client="ACME SARL", fiscal_year=2024, status=E.ANALYSED)
        case.transition_to(E.UNDER_REVIEW)
        assert case.status == E.UNDER_REVIEW

    def test_the_same_document_cannot_be_attached_twice(self):
        # Same bytes, same fingerprint, nothing to re-extract (NFR-08).
        case = E.AnalysisCase(client="ACME SARL", fiscal_year=2024)
        case.attach(E.SourceDocument(file_name="a.pdf", doc_type="PDF", sha256="abc"))
        with pytest.raises(E.DomainError, match="already attached"):
            case.attach(E.SourceDocument(file_name="b.pdf", doc_type="PDF", sha256="abc"))


class TestCorrection:
    def test_a_correction_keeps_what_the_extractor_proposed(self):
        # BR-10, and the raw material of the whole of Part D. If this test
        # ever fails, the evaluation of the internship loses its yardstick.
        field = E.ExtractedField(item_code="BK", amount=Amount(100))
        field.correct(Amount(120), author="helena")

        assert field.amount == Amount(120)
        assert field.proposed_amount == Amount(100)
        assert field.was_corrected
        assert field.correction_gap == 20
        assert field.corrected_by == "helena"
        assert field.corrected_at is not None

    def test_a_validated_field_cannot_be_corrected_silently(self):
        # UC-04 exception E1: reopen the case first, and leave a trace.
        field = E.ExtractedField(
            item_code="BK", amount=Amount(100), status=E.VALIDATED_FIELD
        )
        with pytest.raises(E.DomainError, match="reopen"):
            field.correct(Amount(120), author="helena")


class TestInterpretation:
    def test_a_ratio_with_a_reference_is_compared_to_it(self, balanced):
        result = compute_one(definition_of("R1"), balanced)
        interpretation = interpret(result)
        assert interpretation.template_id == "T_COMPARED_TO_THRESHOLD"
        assert interpretation.reference_source  # BR-14: the source is cited

    def test_a_ratio_without_a_reference_gets_no_judgement(self, balanced):
        # BR-14 in action. R2 has no documented threshold yet, so the
        # sentence states the value and stops. That is the correct behaviour,
        # not a missing feature.
        result = compute_one(definition_of("R2"), balanced)
        interpretation = interpret(result)
        assert "no judgement" in interpretation.text.lower() or (
            interpretation.template_id == "T_NOT_COMPUTABLE"
        )

    def test_nothing_is_ever_generated_freely(self, balanced):
        # BR-13. Every sentence the system can produce comes from one of
        # three templates — there is no fourth path out of interpret().
        for code in ("R1", "R2", "R3", "R4", "R5"):
            interpretation = interpret(compute_one(definition_of(code), balanced))
            assert interpretation.template_id in {
                "T_COMPARED_TO_THRESHOLD",
                "T_FACTUAL_NO_REFERENCE",
                "T_NOT_COMPUTABLE",
            }


# ==========================================================================
FORBIDDEN_IN_DOMAIN = {
    "flask",
    "sqlalchemy",
    "pdfplumber",
    "fitz",
    "pymupdf",
    "openpyxl",
    "pytesseract",
    "PIL",
    "requests",
    "anthropic",
    "document_processing",
}


def test_the_domain_layer_depends_on_nothing_external():
    """NFR-06, enforced rather than promised.

    Walks every module under ``app/domain`` and reads its imports. If one of
    them reaches for a web framework, a database or a PDF library, the
    layering has been breached — and the sensitivity analysis of Part D, which
    is only fast because this layer needs nothing to run, is at risk.

    When this test fails, do not add the module to the allowed list. Move the
    code to ``infra/`` and define a port for it.
    """
    domain = Path(__file__).resolve().parents[3] / "backend" / "app" / "domain"
    offenders = []

    for module in domain.rglob("*.py"):
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                root = name.split(".")[0]
                if root in FORBIDDEN_IN_DOMAIN:
                    offenders.append(f"{module.name} imports {name}")

    assert not offenders, "the domain layer must stay pure:\n" + "\n".join(offenders)
