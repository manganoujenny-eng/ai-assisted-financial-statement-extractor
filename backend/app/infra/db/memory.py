"""In-memory repositories.

Same ports as the SQLAlchemy ones, no database. They exist for two reasons:

* every service test runs in microseconds and leaves nothing behind;
* the API can be started with ``STORAGE=memory`` to demonstrate the chain on
  a machine where nothing is installed.

If a test needs a database to prove a business rule, the business rule is in
the wrong layer. Use these repositories as the check: anything you cannot
test with them has leaked out of the domain.
"""

from __future__ import annotations

from ...domain import entities as E


class InMemoryCaseRepository:
    def __init__(self) -> None:
        self._cases: dict[str, E.AnalysisCase] = {}

    def add(self, case: E.AnalysisCase) -> None:
        self._cases[case.id] = case

    def get(self, case_id: str) -> E.AnalysisCase | None:
        return self._cases.get(case_id)

    def list(self) -> list[E.AnalysisCase]:
        return list(self._cases.values())

    def save(self, case: E.AnalysisCase) -> None:
        self._cases[case.id] = case


class InMemoryDocumentRepository:
    def __init__(self) -> None:
        self._documents: dict[str, E.SourceDocument] = {}

    def add(self, document: E.SourceDocument) -> None:
        self._documents[document.id] = document

    def get(self, document_id: str) -> E.SourceDocument | None:
        return self._documents.get(document_id)

    def find_by_sha256(self, sha256: str) -> E.SourceDocument | None:
        return next((d for d in self._documents.values() if d.sha256 == sha256), None)


class InMemoryExtractionRepository:
    def __init__(self) -> None:
        self._runs: dict[str, E.ExtractionRun] = {}

    def add(self, run: E.ExtractionRun) -> None:
        self._runs[run.id] = run

    def get(self, run_id: str) -> E.ExtractionRun | None:
        return self._runs.get(run_id)

    def save(self, run: E.ExtractionRun) -> None:
        self._runs[run.id] = run

    def list_for_document(self, document_id: str) -> list[E.ExtractionRun]:
        return [r for r in self._runs.values() if r.document_id == document_id]

    def find_by_field(self, field_id: str) -> E.ExtractionRun | None:
        return next(
            (r for r in self._runs.values() if any(f.id == field_id for f in r.fields)),
            None,
        )


class InMemoryDatasetRepository:
    def __init__(self) -> None:
        self._datasets: dict[str, E.ValidatedDataset] = {}

    def add(self, dataset: E.ValidatedDataset) -> None:
        self._datasets[dataset.id] = dataset

    def get(self, dataset_id: str) -> E.ValidatedDataset | None:
        return self._datasets.get(dataset_id)

    def find_by_extraction(self, extraction_id: str) -> E.ValidatedDataset | None:
        return next(
            (d for d in self._datasets.values() if d.extraction_id == extraction_id),
            None,
        )


class InMemoryAuditLog:
    """Append-only, and it shows: there is no way to remove an entry."""

    def __init__(self) -> None:
        self._entries: list[E.AuditEntry] = []

    def record(self, entry: E.AuditEntry) -> None:
        self._entries.append(entry)

    def list_for(self, entity: str, entity_id: str) -> list[E.AuditEntry]:
        return [
            e for e in self._entries if e.entity == entity and e.entity_id == entity_id
        ]

    def all(self) -> list[E.AuditEntry]:
        return list(self._entries)
