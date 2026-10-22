"""Ports: what the domain needs from the outside world, on its own terms.

A *port* is an interface the domain defines and the infrastructure obeys —
never the reverse. That is the dependency inversion of dossier §11: "the
language model, the OCR engine and the PDF reading library will change; the
accounting rules will not. The former are therefore placed behind
interfaces, the latter at the centre."

Concretely, this is the file that lets you:

* run every domain test with no network, no database and no PDF (NFR-06);
* swap Claude for another provider by writing one class (§11.1);
* compare the language-model structurer against a rule-based baseline, which
  the thesis needs — two adapters, one port, same tests.

``Protocol`` rather than ``ABC`` on purpose: an adapter does not have to
inherit anything, it only has to have the right methods. Helena's existing
``document_processing`` package becomes a valid adapter without a single
line changed inside it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol, runtime_checkable

from .entities import (
    AiAnalysis,
    AnalysisCase,
    AuditEntry,
    EvaluationCampaign,
    ExtractionRun,
    SourceDocument,
    User,
    ValidatedDataset,
)


# ==========================================================================
# Document reading
# ==========================================================================
@dataclass
class RawDocument:
    """What a reader hands back: text, tables, and how it was obtained.

    Deliberately not a PDF object and not a workbook. Once a document has
    crossed this boundary, nothing downstream can tell whether it came from
    a native PDF, an OCR pass or an Excel sheet — and nothing downstream
    should care.
    """

    file_type: str  # PDF | XLSX
    document_type: str  # NATIVE_PDF | POSSIBLY_SCANNED | SPREADSHEET
    pages_text: list[str] = field(default_factory=list)
    tables: list[list[list[object]]] = field(default_factory=list)
    ocr_used: bool = False

    @property
    def page_count(self) -> int:
        return len(self.pages_text)

    @property
    def full_text(self) -> str:
        return "\n".join(self.pages_text)


@runtime_checkable
class DocumentReader(Protocol):
    """Reads a file from disk into a RawDocument."""

    def supports(self, path: str) -> bool: ...

    def read(self, path: str) -> RawDocument: ...


# ==========================================================================
# Structuring: raw document -> code-indexed amounts
# ==========================================================================
@dataclass
class StructuredItem:
    """One proposal from a structurer. A *proposal*, not a fact.

    Everything crossing this boundary is still untrusted: it has not met the
    schema validator, the checks or a human. Dossier §11.1: "the domain never
    receives free text."
    """

    item_code: str
    amount: str  # decimal as string — never a float across a boundary
    year: str = "N"
    source_page: int | None = None
    confidence: Decimal | None = None


@dataclass
class StructuringResult:
    items: list[StructuredItem] = field(default_factory=list)
    engine: str = "UNKNOWN"
    model: str | None = None
    prompt_version: str | None = None
    cost_usd: Decimal | None = None
    raw_response: str | None = None


@runtime_checkable
class Structurer(Protocol):
    """Turns a RawDocument into proposed items.

    Two implementations are planned, and the thesis compares them:
    ``RuleBasedStructurer`` (Helena's existing table logic, deterministic and
    free) and ``ClaudeStructurer`` (language model, handles layouts the rules
    do not). Same port, same tests, different trade-offs to measure.
    """

    @property
    def engine(self) -> str: ...

    def structure(self, document: RawDocument) -> StructuringResult: ...


# ==========================================================================
# Persistence
# ==========================================================================
@runtime_checkable
class CaseRepository(Protocol):
    def add(self, case: AnalysisCase) -> None: ...
    def get(self, case_id: str) -> AnalysisCase | None: ...
    def list(self) -> list[AnalysisCase]: ...
    def save(self, case: AnalysisCase) -> None: ...
    # CaseService is the only caller, and only once it has already removed
    # every document attached to this case (each one through
    # DocumentRepository.delete, which clears its own extraction history
    # first) — so this never has to cascade anything itself. One row, one
    # method, same discipline as every other repository here.
    def delete(self, case_id: str) -> None: ...


@runtime_checkable
class DocumentRepository(Protocol):
    def add(self, document: SourceDocument) -> None: ...
    def get(self, document_id: str) -> SourceDocument | None: ...
    # Scoped to case_id on purpose (FR-02/NFR-08): the fingerprint says two
    # uploads are the same bytes, not that they are the same client's
    # document. Dropping case_id here was the bug — it let a second case
    # that happened to upload a byte-identical file (an empty template is
    # the realistic example) silently receive the FIRST case's document,
    # case_id unchanged, with nothing of its own ever attached to it.
    def find_by_sha256(self, sha256: str, case_id: str) -> SourceDocument | None: ...
    def save(self, document: SourceDocument) -> None: ...
    # Same contract as CaseRepository.delete: the caller (CaseService) has
    # already deleted every ExtractionRun for this document (and, through
    # ExtractionRepository.delete, every ValidatedDataset for each of those
    # runs) before this is ever called — a document is never deleted out
    # from under rows that still reference it.
    def delete(self, document_id: str) -> None: ...

@runtime_checkable
class ExtractionRepository(Protocol):
    def add(self, run: ExtractionRun) -> None: ...

    def get(self, run_id: str) -> ExtractionRun | None: ...

    def save(self, run: ExtractionRun) -> None: ...
    # A run now spans every document attached to the case at the time it
    # was started (see ExtractionRun's docstring) — so "the runs behind this
    # case" is the lookup every caller actually needs, not "the runs behind
    # this one document" any more.
    def list_for_case(self, case_id: str) -> list[ExtractionRun]: ...
    # Added to the port on purpose: PATCH /api/fields/{id} identifies a field
    # without naming its run (dossier §17.1), so the port must be able to
    # answer "which run owns this field?". A port grows when a use case needs
    # it to — not before, and never to suit a particular database.
    def find_by_field(self, field_id: str) -> ExtractionRun | None: ...
    # The caller deletes every ValidatedDataset for this run first (via
    # DatasetRepository.list_for_extraction + delete) — this only ever
    # removes a run with nothing left pointing at it. ExtractedFieldRow is
    # this run's own child row (cascade="all, delete-orphan" on
    # ExtractionRunRow.fields already), so nothing extra is needed for it.
    def delete(self, run_id: str) -> None: ...


@runtime_checkable
class DatasetRepository(Protocol):
    def add(self, dataset: ValidatedDataset) -> None: ...
    def get(self, dataset_id: str) -> ValidatedDataset | None: ...
    def find_by_extraction(self, extraction_id: str) -> ValidatedDataset | None: ...
    # Plural on purpose, unlike find_by_extraction: an extraction can be
    # validated more than once (reopen -> correct -> re-validate keeps the
    # earlier snapshot), so deleting "the" dataset for a run is wrong by
    # construction — CaseService needs every one of them before the run
    # itself can be deleted without leaving an orphaned row behind.
    def list_for_extraction(self, extraction_id: str) -> list[ValidatedDataset]: ...
    def list(self) -> list[ValidatedDataset]: ...
    def delete(self, dataset_id: str) -> None: ...


@dataclass
class AuditQuery:
    """What the administrator's audit page asks for. Every filter is
    optional; ``text`` looks in the action, author, entity, entity id and
    detail. ``since``/``until`` are datetimes (``until`` excluded)."""

    author: str | None = None
    action: str | None = None
    entity: str | None = None
    entity_id: str | None = None
    text: str | None = None
    since: object | None = None
    until: object | None = None
    offset: int = 0
    limit: int = 50


@runtime_checkable
class AuditLog(Protocol):
    """FR-22. Append-only: there is no update and no delete in this port."""

    def record(self, entry: AuditEntry) -> None: ...
    def list_for(self, entity: str, entity_id: str) -> list[AuditEntry]: ...
    #: Newest first: (one page of entries, how many match in total).
    def search(self, query: AuditQuery) -> tuple[list[AuditEntry], int]: ...
    #: The distinct authors, actions and entities, for the page's filters.
    def facets(self) -> dict[str, list[str]]: ...



# ==========================================================================
# AI commentary
# ==========================================================================
@dataclass
class AnalysisDraft:
    """What a commentary writer hands back. Sections only, no figures.

    sections = {"overview": str, "ratios": {code: str}, "checks": str,
                "comparison": str, "attention": [str]}
    """

    sections: dict
    model: str | None = None
    prompt_version: str | None = None
    cost_usd: Decimal | None = None


class AnalysisWriter(Protocol):
    """Writes commentary on figures that are already computed and validated.

    It receives figures only (no document, no client name) and never
    computes anything the rule-based engine has not already computed.
    """

    def write(self, payload: dict) -> AnalysisDraft: ...


class AiAnalysisRepository(Protocol):
    def add(self, analysis: AiAnalysis) -> None: ...
    def get(self, analysis_id: str) -> AiAnalysis | None: ...
    def save(self, analysis: AiAnalysis) -> None: ...
    #: The most recent one for this dataset, whatever its status.
    def latest_for_dataset(self, dataset_id: str) -> AiAnalysis | None: ...
    def list_for_case(self, case_id: str) -> list[AiAnalysis]: ...
    def delete_for_case(self, case_id: str) -> None: ...


class UserRepository(Protocol):
    def add(self, user: User) -> None: ...
    def get(self, user_id: str) -> User | None: ...
    #: Case-insensitive.
    def get_by_username(self, username: str) -> User | None: ...
    def list(self) -> list[User]: ...
    def save(self, user: User) -> None: ...
    def delete(self, user_id: str) -> None: ...


class EvaluationRepository(Protocol):
    """Week 7 campaigns (exercise 20). No save(): a measurement is written
    once and never changed, a new one is a new campaign. delete() exists for
    the administrator only (a trial run, a campaign made on a wrong corpus);
    the audit log keeps the trace of what was deleted."""

    def add(self, campaign: EvaluationCampaign) -> None: ...
    def get(self, campaign_id: str) -> EvaluationCampaign | None: ...
    #: Newest first; ``kind`` filters on CORPUS or SENSITIVITY.
    def list(self, kind: str | None = None) -> list[EvaluationCampaign]: ...
    #: True when the campaign existed (its packages go with it).
    def delete(self, campaign_id: str) -> bool: ...