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

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...domain import entities as E
from ...domain.value_objects import Amount
from .models import (
    AiAnalysisRow,
    AnalysisCaseRow,
    AuditLogRow,
    DocumentRow,
    ExtractedFieldRow,
    ExtractionRunRow,
    UserRow,
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
                row.analyst = case.analyst
            self.session.commit()

    # CaseService only calls this once every document attached to the case
    # has already gone through DocumentRepository.delete (see that method's
    # own comment) — so by the time this runs, nothing in the database still
    # points at this case, and dropping the one row is all there is to do.
    def delete(self, case_id: str) -> None:
            row = self.session.get(AnalysisCaseRow, case_id)
            if row is not None:
                self.session.delete(row)
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

    def find_by_sha256(self, sha256: str, case_id: str) -> E.SourceDocument | None:
        row = self.session.scalar(
            select(DocumentRow).where(
                DocumentRow.sha256 == sha256 , DocumentRow.case_id == case_id
            )
        )
        return _document_to_entity(row) if row else None

    def save(self, document: E.SourceDocument) -> None:
        # ExtractionService.run_extraction() learns page_count and is_scanned
        # only once the reader has actually opened the file (register_document
        # cannot know either before that). Without this, those two fields are
        # mutated on the in-memory SourceDocument and never written back —
        # every document looks like page_count=null, is_scanned=null forever,
        # even after a successful extraction.
        row = self.session.get(DocumentRow, document.id)
        if row is None:
            self.add(document)
            return
        row.page_count = document.page_count
        row.is_scanned = document.is_scanned
        self.session.commit()

    # CaseService calls this only after it has already removed this
    # document's id from every ExtractionRun.document_ids that named it,
    # and cleared document_id on every ExtractedField that came from it
    # (see CaseService's docstring) — so no row is left pointing at the
    # document by the time it is actually deleted. ondelete="SET NULL" on
    # ExtractedFieldRow.document_id is only this rule's backstop at the
    # database layer, not the primary mechanism.
    def delete(self, document_id: str) -> None:
            row = self.session.get(DocumentRow, document_id)
            if row is not None:
                self.session.delete(row)
                self.session.commit()


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
            # document_ids is this run's own list, not derived from anything
            # else — CaseService rewrites it directly (via this same save())
            # when a document it names is deleted, so the run's history still
            # reflects which documents it actually drew on.
            row.document_ids = list(run.document_ids)

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
                    # document_id DOES get updated here: it is how CaseService
                    # clears a field's provenance once its source document is
                    # deleted (see DocumentRepository.delete's comment).
                    field_row.document_id = field.document_id
            self.session.commit()

    def list_for_case(self, case_id: str) -> list[E.ExtractionRun]:
            # Oldest first, explicitly. Without ORDER BY, Postgres returns rows
            # in physical order, and an UPDATE (a correction, or CaseService
            # rewriting document_ids after a delete) moves an old run to the
            # end — so the frontend's "last run = latest run" silently opened
            # a stale run. id breaks ties between runs started together.
            rows = self.session.scalars(
                select(ExtractionRunRow)
                .where(ExtractionRunRow.case_id == case_id)
                .order_by(ExtractionRunRow.started_at, ExtractionRunRow.id)
            ).all()
            return [_run_to_entity(row) for row in rows]

    def find_by_field(self, field_id: str) -> E.ExtractionRun | None:
            field_row = self.session.get(ExtractedFieldRow, field_id)
            if field_row is None:
                return None
            return self.get(field_row.extraction_id)

        # The caller deletes every ValidatedDataset for this run first (via
        # DatasetRepository.list_for_extraction + delete) — this only ever
        # removes a run with nothing left pointing at it. ExtractedFieldRow is
        # this run's own child row (cascade="all, delete-orphan" on
        # ExtractionRunRow.fields already), so nothing extra is needed for it.
    def delete(self, run_id: str) -> None:
            row = self.session.get(ExtractionRunRow, run_id)
            if row is not None:
                self.session.delete(row)
                self.session.commit()


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
                amounts={
                    "N": dataset.amounts,
                    "N-1": dataset.prior_year_amounts,
                },
            )
        )
        self.session.commit()

    def get(self, dataset_id: str) -> E.ValidatedDataset | None:
        row = self.session.get(ValidatedDatasetRow, dataset_id)
        return _dataset_to_entity(row) if row else None

    def find_by_extraction(self, extraction_id: str) -> E.ValidatedDataset | None:
        # An extraction can be validated more than once over its life
        # (reopen -> correct -> re-validate keeps the earlier snapshot rather
        # than deleting it, per ValidationService.reopen). Without this
        # ordering, "the" dataset for an extraction is whichever row the
        # database happens to return first, which is not reliably the most
        # recent one -- and the dashboard would silently show stale results
        # after a case was reopened and re-validated.
        row = self.session.scalar(
            select(ValidatedDatasetRow)
            .where(ValidatedDatasetRow.extraction_id == extraction_id)
            .order_by(ValidatedDatasetRow.validated_at.desc())
            .limit(1)
        )
        return _dataset_to_entity(row) if row else None

    def list(self) -> list[E.ValidatedDataset]:
            rows = self.session.scalars(
                select(ValidatedDatasetRow)
            ).all()
            return [_dataset_to_entity(row) for row in rows]

        # Plural on purpose, unlike find_by_extraction: an extraction can be
        # validated more than once (reopen -> correct -> re-validate keeps the
        # earlier snapshot), so deleting "the" dataset for a run is wrong by
        # construction — CaseService needs every one of them before the run
        # itself can be deleted without leaving an orphaned row behind.

    def list_for_extraction(self, extraction_id: str) -> list[E.ValidatedDataset]:
            rows = self.session.scalars(
                select(ValidatedDatasetRow).where(
                    ValidatedDatasetRow.extraction_id == extraction_id
                )
            ).all()
            return [_dataset_to_entity(row) for row in rows]

    def delete(self, dataset_id: str) -> None:
            row = self.session.get(ValidatedDatasetRow, dataset_id)
            if row is not None:
                self.session.delete(row)
                self.session.commit()

class SqlAiAnalysisRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, analysis: E.AiAnalysis) -> None:
        self.session.add(
            AiAnalysisRow(
                id=analysis.id,
                case_id=analysis.case_id,
                dataset_id=analysis.dataset_id,
                status=analysis.status,
                generated_sections=analysis.generated_sections,
                sections=analysis.sections,
                model=analysis.model,
                prompt_version=analysis.prompt_version,
                cost_usd=analysis.cost_usd,
                failure_reason=analysis.failure_reason,
                generated_at=analysis.generated_at,
                approved_by=analysis.approved_by,
                approved_at=analysis.approved_at,
            )
        )
        self.session.commit()

    def get(self, analysis_id: str) -> E.AiAnalysis | None:
        row = self.session.get(AiAnalysisRow, analysis_id)
        return _ai_to_entity(row) if row else None

    def save(self, analysis: E.AiAnalysis) -> None:
        row = self.session.get(AiAnalysisRow, analysis.id)
        if row is None:
            self.add(analysis)
            return
        # generated_sections is NOT updated: written once (see AiAnalysis).
        row.status = analysis.status
        row.sections = analysis.sections
        row.approved_by = analysis.approved_by
        row.approved_at = analysis.approved_at
        self.session.commit()

    def latest_for_dataset(self, dataset_id: str) -> E.AiAnalysis | None:
        row = self.session.scalar(
            select(AiAnalysisRow)
            .where(AiAnalysisRow.dataset_id == dataset_id)
            .order_by(AiAnalysisRow.generated_at.desc())
            .limit(1)
        )
        return _ai_to_entity(row) if row else None

    def list_for_case(self, case_id: str) -> list[E.AiAnalysis]:
        rows = self.session.scalars(
            select(AiAnalysisRow)
            .where(AiAnalysisRow.case_id == case_id)
            .order_by(AiAnalysisRow.generated_at)
        ).all()
        return [_ai_to_entity(row) for row in rows]

    def delete_for_case(self, case_id: str) -> None:
        for row in self.session.scalars(
            select(AiAnalysisRow).where(AiAnalysisRow.case_id == case_id)
        ).all():
            self.session.delete(row)
        self.session.commit()

class SqlUserRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, user: E.User) -> None:
        self.session.add(
            UserRow(
                id=user.id,
                username=user.username,
                full_name=user.full_name,
                role=user.role,
                password_hash=user.password_hash,
                active=user.active,
                created_at=user.created_at,
            )
        )
        self.session.commit()

    def get(self, user_id: str) -> E.User | None:
        row = self.session.get(UserRow, user_id)
        return _user_to_entity(row) if row else None

    def get_by_username(self, username: str) -> E.User | None:
        row = self.session.scalar(
            select(UserRow).where(func.lower(UserRow.username) == (username or "").strip().lower())
        )
        return _user_to_entity(row) if row else None

    def list(self) -> list[E.User]:
        rows = self.session.scalars(select(UserRow).order_by(UserRow.full_name)).all()
        return [_user_to_entity(row) for row in rows]

    def save(self, user: E.User) -> None:
        row = self.session.get(UserRow, user.id)
        if row is None:
            self.add(user)
            return
        row.full_name = user.full_name
        row.role = user.role
        row.password_hash = user.password_hash
        row.active = user.active
        self.session.commit()


    def delete(self, user_id: str) -> None:
        row = self.session.get(UserRow, user_id)
        if row is not None:
            self.session.delete(row)
            self.session.commit()

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
        analyst=case.analyst,
    )


def _case_to_entity(row: AnalysisCaseRow) -> E.AnalysisCase:
    case = E.AnalysisCase(
        id=row.id,
        client=row.client,
        fiscal_year=row.fiscal_year,
        status=row.status,
        created_at=row.created_at,
        analyst=row.analyst,
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
        document_id=field.document_id,
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
        document_id=row.document_id,
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
            case_id=run.case_id,
            document_ids=list(run.document_ids),
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
        case_id=row.case_id,
        document_ids=list(row.document_ids or []),
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
    stored_amounts = row.amounts or {}

    # New format: both fiscal years are stored in the existing JSON column.
    if "N" in stored_amounts or "N-1" in stored_amounts:
        current_amounts = stored_amounts.get("N", {})
        prior_year_amounts = stored_amounts.get("N-1", {})
    else:
        # Backward compatibilty: older database rows contains Year N directly.
        current_amounts = stored_amounts
        prior_year_amounts = {}


    return E.ValidatedDataset(
        id=row.id,
        extraction_id=row.extraction_id,
        validated_by=row.validated_by,
        validated_at=row.validated_at,
        amounts=dict(current_amounts),
        prior_year_amounts=dict(prior_year_amounts),
    )



def _ai_to_entity(row: AiAnalysisRow) -> E.AiAnalysis:
    return E.AiAnalysis(
        id=row.id,
        case_id=row.case_id,
        dataset_id=row.dataset_id,
        status=row.status,
        generated_sections=row.generated_sections,
        sections=row.sections,
        model=row.model,
        prompt_version=row.prompt_version,
        cost_usd=Decimal(str(row.cost_usd)) if row.cost_usd is not None else None,
        failure_reason=row.failure_reason,
        generated_at=row.generated_at,
        approved_by=row.approved_by,
        approved_at=row.approved_at,
    )



def _user_to_entity(row: UserRow) -> E.User:
    return E.User(
        id=row.id,
        username=row.username,
        full_name=row.full_name,
        role=row.role,
        password_hash=row.password_hash,
        active=row.active,
        created_at=row.created_at,
    )