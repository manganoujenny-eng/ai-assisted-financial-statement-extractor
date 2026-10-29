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
#: The analyst has finished and handed the case to the supervisor. Only from
#: here can a case be validated, and only from here (or once validated) can
#: the supervisor send it back with a correction request.
SUBMITTED = "SUBMITTED"
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
    # Submitting straight from EXTRACTED is allowed: correcting is a
    # right, not an obligation. A clean extraction needs no correction.
    EXTRACTED: {UNDER_REVIEW, SUBMITTED, EXTRACTING},
    UNDER_REVIEW: {SUBMITTED, EXTRACTING},
    # The supervisor's two answers to a submission: validate it, or send it
    # back to the analyst with a correction request. Nothing is validated
    # that the analyst has not first submitted (dossier §6.2: the one who
    # corrects is not the one who validates).
    SUBMITTED: {VALIDATED, UNDER_REVIEW},
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
class ExtractionRejection:
    """A Model proposal that could not be converted into an ExtractedField"""

    raw_item: object
    reason: str

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
    # Which of the case's documents this item came from. A run now spans
    # every document attached to the case, so this is what lets the review
    # screen show the right source file next to each field — and what lets
    # a field survive, as history, a later deletion of its source document
    # (the document_id is simply cleared then; see CaseService).
    document_id: str | None = None
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
        # A hand-keyed item stays KEYED when its amount is changed again:
        # it was never proposed by the extractor, and calling it CORRECTED
        # would make it look like an extraction error in the Part D figures.
        self.status = KEYED if self.is_keyed else CORRECTED
        self.corrected_by = author
        self.corrected_at = _now()

    @property
    def is_keyed(self) -> bool:
            """Entered by the analyst, never proposed by the extractor."""
            return self.proposed_amount is None

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
    """One extraction attempt on a case's WHOLE current set of documents.

    A run used to belong to a single document. It now belongs to the case:
    "extract" means read every document currently attached, structure each
    one, and merge their proposed fields into one combined run — because a
    SYSCOHADA ratio (return on equity, say) needs an item from the balance
    sheet and an item from the income statement together, and those two
    statements are routinely two separate uploaded files. ``document_ids``
    is this run's snapshot of which documents it was built from; it does not
    change later even if one of those documents is deleted afterwards.

    Engine, model and prompt version are recorded so that two runs on the
    same case are comparable (dossier §12.1) — that comparison is the
    "language-model structurer versus rule-based baseline" the thesis needs.
    """

    case_id: str
    engine: str  # LLM | RULE_BASED
    id: str = field(default_factory=_new_id)
    model: str | None = None
    prompt_version: str | None = None
    status: str = EXTRACTING
    started_at: datetime = field(default_factory=_now)
    finished_at: datetime | None = None
    cost_usd: Decimal | None = None
    failure_reason: str | None = None
    document_ids: list[str] = field(default_factory=list)
    fields: list[ExtractedField] = field(default_factory=list)
    rejections: list[ExtractionRejection] = field(default_factory=list)

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

    A frozen snapshot containing year N and, when available, N-1.
    """

    extraction_id: str
    validated_by: str
    amounts: dict[str, str]  # Year N; existing interface remains compatible
    prior_year_amounts: dict[str, str] = field(default_factory=dict)
    id: str = field(default_factory=_new_id)
    validated_at: datetime = field(default_factory=_now)

    def statement(self , year: str = "N") -> FinancialStatement:
        """Return a statement for one year from the frozen dataset."""
        if year == "N":
            return FinancialStatement.from_dict(self.amounts)
        if year == "N-1":
            return FinancialStatement.from_dict(self.prior_year_amounts)

        raise ValueError(
                f"Unsupported fiscal year label: {year}. Expected 'N' or 'N-1'."
            )



@dataclass
class AnalysisCase:
    """A client, a fiscal year, its documents, and where it has got to."""

    client: str
    fiscal_year: int
    id: str = field(default_factory=_new_id)
    status: str = CREATED
    created_at: datetime = field(default_factory=_now)
    documents: list[SourceDocument] = field(default_factory=list)
    # Who created and works the case. A plain name for now (typed once in
    # the browser); item 5 replaces it with a real user from a roles table.
    analyst: str | None = None

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



# --- AI commentary (item 4) -----------------------------------------------
AI_DRAFT = "DRAFT"
AI_APPROVED = "APPROVED"
AI_FAILED = "FAILED"


@dataclass
class AiAnalysis:
    """Language-model commentary on one validated dataset.

    BR-13 — no text freely generated by a model is displayed as an
    analytical conclusion. This entity is how that rule survives having an
    LLM write commentary at all: what the model writes is a DRAFT, and it
    only becomes part of the analysis once a named analyst has read it,
    edited it if needed, and approved it.

    ``generated_sections`` plays the role ``proposed_amount`` plays for a
    field (BR-10): written once, when the model answers, never again. The
    analyst's edits go into ``sections``. Comparing the two later measures
    how much the model's text had to be changed.

    The figures, checks and ratios stay rule-based. Nothing here feeds back
    into them.
    """

    case_id: str
    dataset_id: str
    id: str = field(default_factory=_new_id)
    status: str = AI_DRAFT
    generated_sections: dict | None = None
    sections: dict | None = None
    model: str | None = None
    prompt_version: str | None = None
    cost_usd: Decimal | None = None
    failure_reason: str | None = None
    generated_at: datetime = field(default_factory=_now)
    approved_by: str | None = None
    approved_at: datetime | None = None

    def approve(self, sections: dict, author: str) -> None:
        if self.status == AI_FAILED:
            raise DomainError(
                "there is no AI draft to approve — generation failed; generate it again"
            )
        if self.status == AI_APPROVED:
            raise DomainError("this AI analysis is already approved")
        if not author or not author.strip():
            raise DomainError("an approval needs the analyst's name")
        self.sections = sections
        self.status = AI_APPROVED
        self.approved_by = author.strip()
        self.approved_at = _now()

    @property
    def was_edited(self) -> bool:
        return (
            self.generated_sections is not None
            and self.sections is not None
            and self.sections != self.generated_sections
        )



# --- Users and roles (item 5) ---------------------------------------------
ROLE_ANALYST = "ANALYST"
ROLE_SUPERVISOR = "SUPERVISOR"
ROLE_ADMIN = "ADMIN"
#: Exactly one, created once with backend/create_superadmin.py.
ROLE_SUPERADMIN = "SUPERADMIN"
ROLES = (ROLE_ANALYST, ROLE_SUPERVISOR, ROLE_ADMIN, ROLE_SUPERADMIN)


@dataclass
class User:
    """Someone who signs in. Dossier §6.2 separates the two roles:

    * ANALYST — creates cases, uploads and deletes documents, extracts,
      corrects and keys items, submits the case for validation, approves AI
      commentary on their cases.
    * SUPERVISOR — reviews (read-only), validates a submitted case or sends
      it back to its analyst with a correction request, deletes ANALYSED
      cases, manages users and sees the cross-analyst dashboard. A
      supervisor does NOT create cases, upload, delete documents, extract
      or correct: the one who validates is not the one who prepares.
    * ADMIN — runs the system: manages every supervisor and analyst
      account, reads the whole audit log and the database (read-only),
      manages the evaluation corpus and runs the campaigns. An
      administrator neither prepares nor validates a case, so the
      separation above stays intact. Administrator accounts are created
      by the super administrator (Users page) or with
      ``backend/create_admin.py``.
    * SUPERADMIN — exactly one, created once with
      ``backend/create_superadmin.py``. Everything an administrator does,
      plus managing the administrators. Nobody manages this account from
      the screens. ``is_admin`` is true for it too: it opens the same
      administration area.

    ``full_name`` is what every record shows (validated_by, corrected_by,
    a case's analyst, audit authors). ``username`` is only for signing in.
    The password is never stored, only its salted hash (``password_hash``,
    set by UserService) — and it never leaves the backend.
    """

    username: str
    full_name: str
    role: str
    password_hash: str
    id: str = field(default_factory=_new_id)
    active: bool = True
    created_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        if self.role not in ROLES:
            raise DomainError(f"unknown role {self.role!r} — expected one of {ROLES}")

    @property
    def is_supervisor(self) -> bool:
        return self.role == ROLE_SUPERVISOR

    @property
    def is_admin(self) -> bool:
        """An administrator — the super administrator included."""
        return self.role in (ROLE_ADMIN, ROLE_SUPERADMIN)

    @property
    def is_superadmin(self) -> bool:
        return self.role == ROLE_SUPERADMIN

    @property
    def is_analyst(self) -> bool:
        return self.role == ROLE_ANALYST



# ==========================================================================
# Week 7 — a stored evaluation campaign (exercise 20)
# ==========================================================================
CAMPAIGN_CORPUS = "CORPUS"  # extraction measured against the hand readings
CAMPAIGN_SENSITIVITY = "SENSITIVITY"  # errors injected into one statement
CAMPAIGN_KINDS = (CAMPAIGN_CORPUS, CAMPAIGN_SENSITIVITY)


@dataclass
class EvaluationCampaign:
    """One run of the week 7 measurements, kept as it was produced.

    Exercise 20 — stored, because a figure quoted in the thesis must still
    be readable, months later, exactly as it was measured: the extractor,
    the checks or the corpus will have changed by then, and re-running the
    campaign would give a different answer to a question asked about the
    old one. ``inputs`` keeps the fingerprint (SHA-256) of every file the
    campaign read, so it can also be proven which files produced it.

    Written once, never edited — like ``proposed_amount`` (BR-10). A new
    measurement is a new campaign, and the old one stays comparable to it.

    ``summary``, ``inputs`` and ``packages`` are plain JSON (amounts and
    rates as strings), exactly what the API returns.
    """

    kind: str
    summary: dict
    id: str = field(default_factory=_new_id)
    run_at: datetime = field(default_factory=_now)
    author: str | None = None
    engine: str | None = None
    corpus: str | None = None
    note: str | None = None
    inputs: dict = field(default_factory=dict)
    packages: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.kind not in CAMPAIGN_KINDS:
            raise DomainError(f"unknown campaign kind {self.kind!r} — expected one of {CAMPAIGN_KINDS}")


# ==========================================================================
# The archive — every deletion, kept so the administrator can undo it
# ==========================================================================
ARCHIVE_CASE = "CASE"
ARCHIVE_DOCUMENT = "DOCUMENT"
ARCHIVE_USER = "USER"
ARCHIVE_CORPUS_FILE = "CORPUS_FILE"
ARCHIVE_CORPUS_PACKAGE = "CORPUS_PACKAGE"
ARCHIVE_CAMPAIGN = "CAMPAIGN"
ARCHIVE_KINDS = (ARCHIVE_CASE, ARCHIVE_DOCUMENT, ARCHIVE_USER, ARCHIVE_CORPUS_FILE,
                 ARCHIVE_CORPUS_PACKAGE, ARCHIVE_CAMPAIGN)


@dataclass
class ArchiveEntry:
    """Something someone deleted, kept whole.

    For the person who deleted it, it is gone. The administrator sees it in
    the archive and can restore it exactly as it was — same identifiers,
    same history — or delete it for good.

    ``payload`` is the complete copy needed to restore (entities encoded as
    plain JSON by ``services/archive_service.py``); it never leaves the
    backend. ``detail`` is a short summary for the screen (counts, file
    name, role...). ``label`` names the thing in one line.
    """

    kind: str
    entity_id: str
    label: str
    payload: dict
    detail: dict = field(default_factory=dict)
    deleted_by: str | None = None
    id: str = field(default_factory=_new_id)
    deleted_at: datetime = field(default_factory=_now)


# ==========================================================================
# Discussion between supervisors about a case
# ==========================================================================
#: A message is a suggestion, not a decision: at most this long.
MAX_COMMENT_LENGTH = 2000


@dataclass
class CaseComment:
    """One message in a case's discussion between supervisors.

    Only the supervisor a case is assigned to acts on it; the others give
    their opinion here, and that supervisor replies. Its author may edit it
    (``edited_at``) or delete it (``deleted_at``): a deleted message stays
    in the thread as "deleted", without its text. The audit log keeps what
    was written.
    """

    case_id: str
    author: str
    message: str
    id: str = field(default_factory=_new_id)
    created_at: datetime = field(default_factory=_now)
    edited_at: datetime | None = None
    deleted_at: datetime | None = None

    @property
    def deleted(self) -> bool:
        return self.deleted_at is not None

