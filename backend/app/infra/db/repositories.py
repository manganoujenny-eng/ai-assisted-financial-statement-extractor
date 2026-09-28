"""SQLAlchemy repositories: the translation between rows and entities.

Every method here does the same two things — read rows, build entities, or
the reverse. It looks repetitive, and it is: that repetition is the price of
keeping the domain free of the database, and it is a price worth paying. The
alternative is entities that inherit from ``Base``, and then every unit test
needs a database and the sensitivity analysis of Part D slows down by three
orders of magnitude.

Note ``_to_entity`` / ``_to_row`` in each class. That pair is the whole
pattern. Once you have read one, you have read all five.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...domain import entities as E
from ...domain.value_objects import Amount
from .models import (
    AnalysisCaseRow,
    AuditLogRow,
    DocumentRow,
    ExtractedFieldRow,
    ExtractionRunRow,
    ValidatedDatasetRow,
)


class SqlCaseRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, case: E.AnalysisCase) -> None:
        self.session.add(_case_to_row(case))
        self.session.commit()

    def get(self, case_id: str) -> E.AnalysisCase | None:
        row = self.session.get(AnalysisCaseRow, case_id)
        return _case_to_entity(row) if row else None

    def list(self) -> list[E.AnalysisCase]:
        rows = self.session.scalars(
            select(AnalysisCaseRow).order_by(AnalysisCaseRow.created_at.desc())
        ).all()
        return [_case_to_entity(row) for row in rows]

    def save(self, case: E.AnalysisCase) -> None:
        row = self.session.get(AnalysisCaseRow, case.id)
        if row is None:
            self.session.add(_case_to_row(case))
        else:
            row.client = case.client
            row.fiscal_year = case.fiscal_year
            row.status = case.status
        self.session.commit()


class SqlDocumentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, document: E.SourceDocument) -> None:
        self.session.add(
            DocumentRow(
                id=document.id,
                case_id=document.case_id,
                file_name=document.file_name,
                doc_type=document.doc_type,
                sha256=document.sha256,
                stored_path=document.stored_path,
                page_count=document.page_count,
                is_scanned=document.is_scanned,
                uploaded_at=document.uploaded_at,
            )
        )
        self.session.commit()

    def get(self, document_id: str) -> E.SourceDocument | None:
        row = self.session.get(DocumentRow, document_id)
        return _document_to_entity(row) if row else None

    def find_by_sha256(self, sha256: str) -> E.SourceDocument | None:
        row = self.session.scalar(select(DocumentRow).where(DocumentRow.sha256 == sha256))
        return _document_to_entity(row) if row else None


class SqlExtractionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, run: E.ExtractionRun) -> None:
        self.session.add(_run_to_row(run))
        self.session.commit()

    def get(self, run_id: str) -> E.ExtractionRun | None:
        row = self.session.get(ExtractionRunRow, run_id)
        return _run_to_entity(row) if row else None

    def save(self, run: E.ExtractionRun) -> None:
        row = self.session.get(ExtractionRunRow, run.id)
        if row is None:
            self.session.add(_run_to_row(run))
            self.session.commit()
            return

        row.status = run.status
        row.model = run.model
        row.prompt_version = run.prompt_version
        row.finished_at = run.finished_at
        row.cost_usd = run.cost_usd
        row.failure_reason = run.failure_reason

        existing = {f.id: f for f in row.fields}
        for field in run.fields:
            field_row = existing.get(field.id)
            if field_row is None:
                row.fields.append(_field_to_row(field, run.id))
            else:
                # Note what is NOT updated: proposed_amount. BR-10 — the
                # originally proposed value is written once and never again.
                # If this line ever appears, Part D loses its raw material.
                field_row.amount = field.amount.value
                field_row.status = field.status
                field_row.corrected_by = field.corrected_by
                field_row.corrected_at = field.corrected_at
        self.session.commit()

    def list_for_document(self, document_id: str) -> list[E.ExtractionRun]:
        rows = self.session.scalars(
            select(ExtractionRunRow).where(ExtractionRunRow.document_id == document_id)
        ).all()
        return [_run_to_entity(row) for row in rows]

    def find_by_field(self, field_id: str) -> E.ExtractionRun | None:
        field_row = self.session.get(ExtractedFieldRow, field_id)
        if field_row is None:
            return None
        return self.get(field_row.extraction_id)


class SqlDatasetRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, dataset: E.ValidatedDataset) -> None:
        self.session.add(
            ValidatedDatasetRow(
                id=dataset.id,
                extraction_id=dataset.extraction_id,
                validated_by=dataset.validated_by,
                validated_at=dataset.validated_at,
                amounts=dataset.amounts,
            )
        )
        self.session.commit()

    def get(self, dataset_id: str) -> E.ValidatedDataset | None:
        row = self.session.get(ValidatedDatasetRow, dataset_id)
        return _dataset_to_entity(row) if row else None

    def find_by_extraction(self, extraction_id: str) -> E.ValidatedDataset | None:
        row = self.session.scalar(
            select(ValidatedDatasetRow).where(
                ValidatedDatasetRow.extraction_id == extraction_id
            )
        )
        return _dataset_to_entity(row) if row else None


class SqlAuditLog:
    def __init__(self, session: Session) -> None:
        self.session = session

    def record(self, entry: E.AuditEntry) -> None:
        self.session.add(
            AuditLogRow(
                id=entry.id,
                entity=entry.entity,
                entity_id=entry.entity_id,
                action=entry.action,
                author=entry.author,
                at=entry.at,
                detail=entry.detail,
            )
        )
        self.session.commit()

    def list_for(self, entity: str, entity_id: str) -> list[E.AuditEntry]:
        rows = self.session.scalars(
            select(AuditLogRow)
            .where(AuditLogRow.entity == entity, AuditLogRow.entity_id == entity_id)
            .order_by(AuditLogRow.at)
        ).all()
        return [
            E.AuditEntry(
                id=row.id,
                entity=row.entity,
                entity_id=row.entity_id,
                action=row.action,
                author=row.author,
                at=row.at,
                detail=row.detail,
            )
            for row in rows
        ]


# --- mappers --------------------------------------------------------------
def _case_to_row(case: E.AnalysisCase) -> AnalysisCaseRow:
    return AnalysisCaseRow(
        id=case.id,
        client=case.client,
        fiscal_year=case.fiscal_year,
        status=case.status,
        created_at=case.created_at,
    )


def _case_to_entity(row: AnalysisCaseRow) -> E.AnalysisCase:
    case = E.AnalysisCase(
        id=row.id,
        client=row.client,
        fiscal_year=row.fiscal_year,
        status=row.status,
        created_at=row.created_at,
    )
    case.documents = [_document_to_entity(d) for d in row.documents]
    return case


def _document_to_entity(row: DocumentRow) -> E.SourceDocument:
    return E.SourceDocument(
        id=row.id,
        case_id=row.case_id,
        file_name=row.file_name,
        doc_type=row.doc_type,
        sha256=row.sha256,
        stored_path=row.stored_path,
        page_count=row.page_count,
        is_scanned=row.is_scanned,
        uploaded_at=row.uploaded_at,
    )


def _field_to_row(field: E.ExtractedField, run_id: str) -> ExtractedFieldRow:
    return ExtractedFieldRow(
        id=field.id,
        extraction_id=run_id,
        item_code=field.item_code,
        amount=field.amount.value,
        proposed_amount=(
            field.proposed_amount.value if field.proposed_amount is not None else None
        ),
        year=field.year,
        source_page=field.source_page,
        confidence=field.confidence,
        status=field.status,
        corrected_by=field.corrected_by,
        corrected_at=field.corrected_at,
    )


def _field_to_entity(row: ExtractedFieldRow) -> E.ExtractedField:
    return E.ExtractedField(
        id=row.id,
        extraction_id=row.extraction_id,
        item_code=row.item_code,
        amount=Amount(Decimal(str(row.amount))),
        proposed_amount=(
            Amount(Decimal(str(row.proposed_amount)))
            if row.proposed_amount is not None
            else None
        ),
        year=row.year,
        source_page=row.source_page,
        confidence=Decimal(str(row.confidence)) if row.confidence is not None else None,
        status=row.status,
        corrected_by=row.corrected_by,
        corrected_at=row.corrected_at,
    )


def _run_to_row(run: E.ExtractionRun) -> ExtractionRunRow:
    row = ExtractionRunRow(
        id=run.id,
        document_id=run.document_id,
        engine=run.engine,
        model=run.model,
        prompt_version=run.prompt_version,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        cost_usd=run.cost_usd,
        failure_reason=run.failure_reason,
    )
    row.fields = [_field_to_row(f, run.id) for f in run.fields]
    return row


def _run_to_entity(row: ExtractionRunRow) -> E.ExtractionRun:
    run = E.ExtractionRun(
        id=row.id,
        document_id=row.document_id,
        engine=row.engine,
        model=row.model,
        prompt_version=row.prompt_version,
        status=row.status,
        started_at=row.started_at,
        finished_at=row.finished_at,
        cost_usd=Decimal(str(row.cost_usd)) if row.cost_usd is not None else None,
        failure_reason=row.failure_reason,
    )
    run.fields = [_field_to_entity(f) for f in row.fields]
    return run


def _dataset_to_entity(row: ValidatedDatasetRow) -> E.ValidatedDataset:
    return E.ValidatedDataset(
        id=row.id,
        extraction_id=row.extraction_id,
        validated_by=row.validated_by,
        validated_at=row.validated_at,
        amounts=dict(row.amounts),
    )
