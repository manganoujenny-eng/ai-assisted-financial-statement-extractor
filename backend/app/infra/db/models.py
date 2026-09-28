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

    documents: Mapped[list["DocumentRow"]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )


class DocumentRow(Base):
    __tablename__ = "document"
    # The fingerprint is unique across the whole table, not per case: the
    # point of NFR-08 is to avoid re-extracting bytes already seen, whoever
    # uploaded them and whenever.
    __table_args__ = (UniqueConstraint("sha256", name="uq_document_sha256"),)

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
    document_id: Mapped[str] = mapped_column(ForeignKey("document.id"), nullable=False)
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
