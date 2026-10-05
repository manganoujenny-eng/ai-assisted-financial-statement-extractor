import pytest

from app.domain import entities as E
from app.infra.db.memory import InMemoryAuditLog, InMemoryDatasetRepository, InMemoryExtractionRepository
from app.services.analysis_service import AnalysisService
from app.services.validation_service import ValidationService


def test_reopening_an_analysed_case_invalidates_current_analysis():
    extractions = InMemoryExtractionRepository()
    datasets = InMemoryDatasetRepository()
    audit = InMemoryAuditLog()

    validation = ValidationService(extractions, datasets, audit)
    analysis = AnalysisService(audit)

    case = E.AnalysisCase(
        client="ACME SARL",
        fiscal_year=2024,
        status=E.ANALYSED,
    )

    validation.reopen(
        case,
        author="helena",
        reason="Correction required",
    )

    assert case.status == E.UNDER_REVIEW

    entries = audit.list_for("AnalysisCase", case.id)

    assert len(entries) == 1
    assert entries[0].action == "REOPENED"
    assert entries[0].author == "helena"
    assert entries[0].detail["reason"] == "Correction required"

    with pytest.raises(E.DomainError, match="analysis is not available"):
        analysis.analyse(
            case,
            E.ValidatedDataset(
                extraction_id="run-1",
                validated_by="supervisor",
                amounts={},
            ),
        )