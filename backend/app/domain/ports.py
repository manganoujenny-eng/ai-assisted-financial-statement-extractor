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
    AnalysisCase,
    AuditEntry,
    ExtractionRun,
    SourceDocument,
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


@runtime_checkable
class DocumentRepository(Protocol):
    def add(self, document: SourceDocument) -> None: ...
    def get(self, document_id: str) -> SourceDocument | None: ...
    def find_by_sha256(self, sha256: str) -> SourceDocument | None: ...


@runtime_checkable
class ExtractionRepository(Protocol):
    def add(self, run: ExtractionRun) -> None: ...
    def get(self, run_id: str) -> ExtractionRun | None: ...
    def save(self, run: ExtractionRun) -> None: ...
    def list_for_document(self, document_id: str) -> list[ExtractionRun]: ...
    # Added to the port on purpose: PATCH /api/fields/{id} identifies a field
    # without naming its run (dossier §17.1), so the port must be able to
    # answer "which run owns this field?". A port grows when a use case needs
    # it to — not before, and never to suit a particular database.
    def find_by_field(self, field_id: str) -> ExtractionRun | None: ...


@runtime_checkable
class DatasetRepository(Protocol):
    def add(self, dataset: ValidatedDataset) -> None: ...
    def get(self, dataset_id: str) -> ValidatedDataset | None: ...
    def find_by_extraction(self, extraction_id: str) -> ValidatedDataset | None: ...


@runtime_checkable
class AuditLog(Protocol):
    """FR-22. Append-only: there is no update and no delete in this port."""

    def record(self, entry: AuditEntry) -> None: ...
    def list_for(self, entity: str, entity_id: str) -> list[AuditEntry]: ...
