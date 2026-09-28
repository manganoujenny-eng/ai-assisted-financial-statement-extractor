"""Domain entities and the case lifecycle.

An *entity* has identity: two ExtractedFields holding the same amount are
still two different fields, because they were extracted from two different
places by two different runs. Contrast with the value objects in
``value_objects.py``, which are interchangeable when equal.

These classes carry no persistence: no SQLAlchemy import, no session, no
``save()``. Turning them into database rows is the repository's job
(``infra/db/repositories.py``), which is what lets the whole business core be
tested in memory (NFR-06).

Dossier: §12 (class diagram), §15 (lifecycle), BR-01, BR-10 to BR-12.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from .statement import FinancialStatement
from .value_objects import Amount

# --- case states (dossier §15) --------------------------------------------
CREATED = "CREATED"
EXTRACTING = "EXTRACTING"
EXTRACTED = "EXTRACTED"
EXTRACTION_FAILED = "EXTRACTION_FAILED"
UNDER_REVIEW = "UNDER_REVIEW"
VALIDATED = "VALIDATED"
ANALYSED = "ANALYSED"

#: Which transitions the model permits. Everything absent from this table is
#: refused — and refused *by the domain*, not by a controller or by the
#: interface hiding a button. An HTTP client, a script or a test that tries a
#: forbidden move gets the same answer.
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    CREATED: {EXTRACTING},
    EXTRACTING: {EXTRACTED, EXTRACTION_FAILED},
    # A failed extraction can be retried; the previous run is kept, which is
    # what makes two prompt versions comparable on the same document (§15).
    EXTRACTION_FAILED: {EXTRACTING},
    # Validating straight from EXTRACTED is allowed: correcting is a
    # right, not an obligation. A clean extraction needs no correction.
    EXTRACTED: {UNDER_REVIEW, VALIDATED, EXTRACTING},
    UNDER_REVIEW: {VALIDATED, EXTRACTING},
    VALIDATED: {ANALYSED, UNDER_REVIEW},  # reopening is permitted but traced
    ANALYSED: {UNDER_REVIEW},  # reopening invalidates the computed results
}

# --- field statuses (dossier §7, UC-04) -----------------------------------
PROPOSED = "PROPOSED"
CORRECTED = "CORRECTED"
VALIDATED_FIELD = "VALIDATED"
KEYED = "KEYED"  # entered by hand, never proposed by the extractor


class DomainError(Exception):
    """A business rule was violated. Never a technical failure."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


@dataclass
class SourceDocument:
    """An uploaded file, its type and its fingerprint.

    The SHA-256 is not decoration. Dossier §16: it "avoids paying to
    re-extract a file already processed" — it is the cache key of NFR-08, and
    it is also what proves, months later, that the document analysed is
    byte-for-byte the document filed.
    """

    file_name: str
    doc_type: str  # PDF | XLSX
    sha256: str
    id: str = field(default_factory=_new_id)
    case_id: str | None = None
    stored_path: str | None = None
    page_count: int | None = None
    is_scanned: bool | None = None
    uploaded_at: datetime = field(default_factory=_now)


@dataclass
class ExtractedField:
    """One item, one amount, and everything needed to justify it later.

    ``proposed_amount`` is the field the dossier singles out (§12.1): "it is
    that field which makes it possible, after the fact, to measure what the
    model proposed and what the human had to correct". Overwrite it and the
    whole evaluation of Part D becomes impossible. It is written once, at
    extraction, and never again.
    """

    item_code: str
    amount: Amount
    id: str = field(default_factory=_new_id)
    extraction_id: str | None = None
    proposed_amount: Amount | None = None
    year: str = "N"
    source_page: int | None = None
    confidence: Decimal | None = None
    status: str = PROPOSED
    corrected_by: str | None = None
    corrected_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.proposed_amount is None and self.status == PROPOSED:
            self.proposed_amount = self.amount

    def correct(self, new_amount: Amount, author: str) -> None:
        """BR-10 — a correction keeps the proposed value, its author and its time.

        The original proposal is deliberately not touched here. If you ever
        find yourself needing to change it, the answer is a new extraction
        run, not a rewritten history.
        """
        if self.status == VALIDATED_FIELD:
            raise DomainError(
                "field already validated — reopen the case before correcting it"
            )
        self.amount = new_amount
        self.status = CORRECTED
        self.corrected_by = author
        self.corrected_at = _now()

    @property
    def was_corrected(self) -> bool:
        return self.proposed_amount is not None and self.proposed_amount != self.amount

    @property
    def correction_gap(self) -> Decimal | None:
        """How far the extractor was, in francs. Raw material for Part D."""
        if self.proposed_amount is None:
            return None
        return (self.amount - self.proposed_amount).value


@dataclass
class ExtractionRun:
    """One extraction attempt on one document.

    Engine, model and prompt version are recorded so that two runs on the
    same document are comparable (dossier §12.1) — that comparison is the
    "language-model structurer versus rule-based baseline" the thesis needs.
    """

    document_id: str
    engine: str  # LLM | RULE_BASED
    id: str = field(default_factory=_new_id)
    model: str | None = None
    prompt_version: str | None = None
    status: str = EXTRACTING
    started_at: datetime = field(default_factory=_now)
    finished_at: datetime | None = None
    cost_usd: Decimal | None = None
    failure_reason: str | None = None
    fields: list[ExtractedField] = field(default_factory=list)

    def statement(self, year: str = "N") -> FinancialStatement:
        """The domain-facing view of this run: code -> Amount, nothing else."""
        return FinancialStatement.from_dict(
            {f.item_code: f.amount for f in self.fields if f.year == year}
        )


@dataclass
class ValidatedDataset:
    """A frozen, signed snapshot. The only lawful entry point for ratios.

    BR-01: no ratio is computed from data a human has not validated. The way
    that rule is *enforced* rather than merely stated is that
    ``AnalysisService`` accepts a ValidatedDataset and nothing else — there is
    no code path from a raw ExtractionRun to a RatioResult.
    """

    extraction_id: str
    validated_by: str
    amounts: dict[str, str]  # code -> decimal as string, frozen at validation
    id: str = field(default_factory=_new_id)
    validated_at: datetime = field(default_factory=_now)

    def statement(self) -> FinancialStatement:
        return FinancialStatement.from_dict(self.amounts)


@dataclass
class AnalysisCase:
    """A client, a fiscal year, its documents, and where it has got to."""

    client: str
    fiscal_year: int
    id: str = field(default_factory=_new_id)
    status: str = CREATED
    created_at: datetime = field(default_factory=_now)
    documents: list[SourceDocument] = field(default_factory=list)

    def can_transition_to(self, target: str) -> bool:
        return target in ALLOWED_TRANSITIONS.get(self.status, set())

    def transition_to(self, target: str) -> None:
        if not self.can_transition_to(target):
            raise DomainError(
                f"case {self.id}: transition {self.status} -> {target} is not allowed"
            )
        self.status = target

    def attach(self, document: SourceDocument) -> None:
        if any(d.sha256 == document.sha256 for d in self.documents):
            raise DomainError(
                f"document {document.file_name} already attached to this case "
                f"(same SHA-256) — nothing to re-extract"
            )
        document.case_id = self.id
        self.documents.append(document)


@dataclass
class AuditEntry:
    """FR-22 — every action that modifies a financial figure is logged.

    Append-only. Nothing in this codebase should ever update or delete an
    audit row; if you find code that does, that is a defect.
    """

    entity: str
    entity_id: str
    action: str
    author: str
    id: str = field(default_factory=_new_id)
    at: datetime = field(default_factory=_now)
    detail: dict | None = None
