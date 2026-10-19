"""SQLAlchemy tables.

These are *rows*, not domain objects. The entities in ``domain/entities.py``
know nothing about this file, and this file imports nothing from the ratio
engine or the checks. The translation between the two happens in
``repositories.py`` — that is the Repository pattern of dossier §13, and the
reason the domain "is unaware of SQLAlchemy, which allows it to be tested in
memory".

This schema is a revision of ``financial_analysis_db.sql``. Every change is
listed and argued in ``docs/DATA-MODEL-REVIEW.md`` — read that document
before concluding that your original was wrong. Most of it was right.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AnalysisCaseRow(Base):
    __tablename__ = "analysis_case"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    client: Mapped[str] = mapped_column(String(200), nullable=False)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    # Added after the table existed: create_all() will NOT add it to your
    # existing database — run backend/add_ai_analysis_schema.py once.
    analyst: Mapped[str | None] = mapped_column(String(100), index=True)

    documents: Mapped[list["DocumentRow"]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )


class DocumentRow(Base):
    __tablename__ = "document"
    # Scoped to (case_id, sha256), not sha256 alone — the same fix as
    # DocumentRepository.find_by_sha256, at the layer that actually enforces
    # it. A global UniqueConstraint on sha256 meant the Python-level fix
    # (scoping the dedup *lookup* to case_id) only hid the bug on the
    # InMemory adapter: on the real database, a second case uploading a
    # byte-identical file (an empty template, say) still correctly got told
    # "no existing document for you", tried to insert its own row, and the
    # database rejected it with an IntegrityError on sha256 — the two
    # adapters behaving differently on the same port is exactly the bug
    # class this codebase keeps catching. NFR-08's goal (don't pay to
    # re-extract bytes this case has already seen) is unaffected: it was
    # never about bytes being unique *across clients*.
    __table_args__ = (
        UniqueConstraint("case_id", "sha256", name="uq_document_case_sha256"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("analysis_case.id"), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    doc_type: Mapped[str] = mapped_column(String(16), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    stored_path: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int | None] = mapped_column(Integer)
    is_scanned: Mapped[bool | None] = mapped_column(Boolean)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    case: Mapped[AnalysisCaseRow] = relationship(back_populates="documents")

class ExtractionRunRow(Base):
    __tablename__ = "extraction_run"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # A run now belongs to the CASE, not to one document — it is the result
    # of reading every document attached to the case at the time it was
    # started and merging their proposed fields (see ExtractionRun's
    # docstring). document_ids is that run's own snapshot of which
    # documents those were: a plain JSON list rather than a join table,
    # because nothing here needs relational integrity on it — CaseService
    # updates this list itself (via save()) when a document it names is
    # deleted, the same way it already clears ExtractedFieldRow.document_id.
    case_id: Mapped[str] = mapped_column(ForeignKey("analysis_case.id"), nullable=False)
    document_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    engine: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str | None] = mapped_column(String(100))
    prompt_version: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 4))
    failure_reason: Mapped[str | None] = mapped_column(Text)

    fields: Mapped[list["ExtractedFieldRow"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class ExtractedFieldRow(Base):
    __tablename__ = "extracted_field"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    extraction_id: Mapped[str] = mapped_column(
        ForeignKey("extraction_run.id"), nullable=False
    )
    # Which of the run's documents this one item came from — needed now
    # that a run spans several documents, so the review screen can still
    # show the right source file next to each field. SET NULL rather than
    # a hard FK the delete would have to fight: CaseService already nulls
    # this itself before deleting a document (see its docstring), and this
    # is only the database's own backstop for that same rule.
    document_id: Mapped[str | None] = mapped_column(
        ForeignKey("document.id", ondelete="SET NULL")
    )
    item_code: Mapped[str] = mapped_column(String(2), nullable=False)
    # Numeric(18, 2), never a float column: the equilibrium check tests
    # equality to the franc, and a float column would make that test
    # unreliable in a way no amount of application code can repair.
    amount: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    proposed_amount: Mapped[float | None] = mapped_column(Numeric(18, 2))
    year: Mapped[str] = mapped_column(String(8), nullable=False, default="N")
    source_page: Mapped[int | None] = mapped_column(Integer)
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 4))
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    corrected_by: Mapped[str | None] = mapped_column(String(100))
    corrected_at: Mapped[datetime | None] = mapped_column(DateTime)

    run: Mapped[ExtractionRunRow] = relationship(back_populates="fields")


class CheckResultRow(Base):
    __tablename__ = "check_result"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    extraction_id: Mapped[str] = mapped_column(
        ForeignKey("extraction_run.id"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(16), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    gap: Mapped[float | None] = mapped_column(Numeric(18, 2))
    message: Mapped[str | None] = mapped_column(Text)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class ValidatedDatasetRow(Base):
    __tablename__ = "validated_dataset"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    extraction_id: Mapped[str] = mapped_column(
        ForeignKey("extraction_run.id"), nullable=False
    )
    validated_by: Mapped[str] = mapped_column(String(100), nullable=False)
    validated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    # The frozen snapshot. Stored here rather than read back through the
    # fields, so that a later correction to a field cannot silently change
    # what was validated. "Frozen" has to be true of the bytes, not only of
    # the intention.
    amounts: Mapped[dict] = mapped_column(JSON, nullable=False)


class RatioResultRow(Base):
    __tablename__ = "ratio_result"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # Corrected against the original dump: this points at the *validated
    # dataset*, not at the extraction run. BR-01 — no ratio is computed from
    # unvalidated data, and a foreign key is a much stronger guarantee of
    # that than a comment.
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("validated_dataset.id"), nullable=False
    )
    ratio_code: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    value: Mapped[float | None] = mapped_column(Numeric(18, 4))
    unit: Mapped[str | None] = mapped_column(String(8))
    reason: Mapped[str | None] = mapped_column(Text)
    items_used: Mapped[dict | None] = mapped_column(JSON)  # BR-04
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class InterpretationRow(Base):
    __tablename__ = "interpretation"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    ratio_result_id: Mapped[str] = mapped_column(
        ForeignKey("ratio_result.id"), nullable=False
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    template_id: Mapped[str] = mapped_column(String(64), nullable=False)
    threshold_applied: Mapped[str | None] = mapped_column(String(32))
    reference_source: Mapped[str | None] = mapped_column(Text)


class AuditLogRow(Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    entity: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    author: Mapped[str] = mapped_column(String(100), nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    detail: Mapped[dict | None] = mapped_column(JSON)



class AiAnalysisRow(Base):
    """LLM commentary on one validated dataset (item 4). New table, so
    create_all() creates it by itself on the next start.

    No foreign keys on purpose: CaseService.delete_case removes these rows
    first (AiAnalysisRepository.delete_for_case), and a commentary must
    never be the reason a dataset cannot be deleted.
    """

    __tablename__ = "ai_analysis"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    dataset_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    generated_sections: Mapped[dict | None] = mapped_column(JSON)
    sections: Mapped[dict | None] = mapped_column(JSON)
    model: Mapped[str | None] = mapped_column(String(100))
    prompt_version: Mapped[str | None] = mapped_column(String(32))
    cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 4))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    approved_by: Mapped[str | None] = mapped_column(String(100))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)



class UserRow(Base):
    """Item 5 — the people who sign in, with their role.

    Named app_user, not "user": USER is a reserved word in PostgreSQL.
    New table, so create_all() creates it; add_users_schema.py also does,
    and creates the first supervisor.
    """

    __tablename__ = "app_user"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    username: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)