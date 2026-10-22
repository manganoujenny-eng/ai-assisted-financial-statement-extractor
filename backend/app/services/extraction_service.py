"""ExtractionService — the fixed sequence, the variable steps.

Template method (dossier §13): "the sequence detect -> extract -> structure
-> validate is fixed; only its steps vary". The order below is the order of
UC-03 in the dossier, step for step. Read them side by side once — a service
that mirrors its own specification is a service you can defend.

The service owns *orchestration and state*. It owns no accounting rule: every
business decision it makes is delegated to the domain (checks, entities) or
to an adapter behind a port.
"""

from __future__ import annotations

import hashlib
import os
from decimal import Decimal

from ..domain import entities as E
from ..domain.checks import run_all
from ..domain.ports import (
    AuditLog,
    DocumentReader,
    DocumentRepository,
    ExtractionRepository,
    Structurer,
)
from ..domain.value_objects import Amount


def sha256_of(path: str) -> str:
    """FR-02 — the document fingerprint.

    Read in chunks: a 40-page scanned PDF is tens of megabytes, and loading
    it whole to hash it would work fine on your laptop and fall over on the
    corpus. Habits taken on small inputs are the ones that break on large
    ones.
    """
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ExtractionFailed(Exception):
    """UC-03 exception E1 — the document could not be read at all."""


class ExtractionService:
    def __init__(
        self,
        readers: list[DocumentReader],
        structurer: Structurer,
        documents: DocumentRepository,
        extractions: ExtractionRepository,
        audit: AuditLog,
    ) -> None:
        # Everything this service needs arrives through the constructor, and
        # every parameter is a port, not a concrete class. That is what makes
        # it testable with fakes — and what makes swapping Claude for another
        # provider a one-line change in the composition root (app/__init__.py).
        self.readers = readers
        self.structurer = structurer
        self.documents = documents
        self.extractions = extractions
        self.audit = audit

    # --- FR-02 ----------------------------------------------------------
    def register_document(
        self, case: E.AnalysisCase, path: str, author: str = "system"
    ) -> E.SourceDocument:
        fingerprint = sha256_of(path)
        # Scoped to case.id on purpose (FR-02/NFR-08): the port requires
        # (sha256, case_id), and this call site used to pass only the
        # fingerprint, which is a TypeError on every adapter.
        already = self.documents.find_by_sha256(fingerprint, case.id)
        if already is not None:
            # NFR-08 — do not pay to extract the same bytes twice.
            return already

        extension = os.path.splitext(path)[1].lower()
        document = E.SourceDocument(
            file_name=os.path.basename(path),
            doc_type="PDF" if extension == ".pdf" else "XLSX",
            sha256=fingerprint,
            stored_path=path,
        )
        self._probe(document)
        case.attach(document)
        self.documents.add(document)
        self.audit.record(
            E.AuditEntry(
                entity="SourceDocument",
                entity_id=document.id,
                action="UPLOADED",
                author=author,
                detail={"file_name": document.file_name, "sha256": fingerprint},
            )
        )
        return document

    # --- UC-03 ----------------------------------------------------------
    def run_extraction(
        self, case: E.AnalysisCase, author: str = "system"
    ) -> E.ExtractionRun:
        """Extract every document currently attached to the case, together.

        This used to take one document. It now reads the case's whole set:
        an analyst uploads the balance sheet and the income statement as two
        separate files, and only one combined run — one review screen, one
        validation — makes sense of both at once (a ratio like return on
        equity needs an item from each). Re-running this later (after
        deleting a wrong document and attaching the right one, say) always
        starts a brand-new run over whatever the case's documents are at
        that moment — the old run is kept, never edited, same as before.
        """
        if not case.documents:
            raise ExtractionFailed("the case has no documents to extract")

        case.transition_to(E.EXTRACTING)
        run = E.ExtractionRun(
            case_id=case.id,
            engine=self.structurer.engine,
            status=E.EXTRACTING,
            document_ids=[d.id for d in case.documents],
        )
        self.extractions.add(run)

        try:
            all_fields: list[E.ExtractedField] = []
            all_rejections: list[E.ExtractionRejection] = []
            # Which document first proposed each (item_code, year) — so a
            # collision reported below can name both documents, not just
            # the code. A collision is refused rather than silently resolved
            # (last-document-wins, say): SYSCOHADA codes are supposed to be
            # disjoint across statements, and a document that duplicates one
            # is far more likely a mistake (the same page scanned twice
            # across two files, an income statement that also repeats a
            # balance-sheet subtotal) than a figure to average away.
            seen_by: dict[tuple[str, str], str] = {}

            for document in case.documents:
                # 1-2. detect the type, extract text and tables (the reader
                #      decides internally whether OCR is needed — A1).
                reader = self._reader_for(document.stored_path or document.file_name)
                raw = reader.read(document.stored_path or document.file_name)
                document.page_count = raw.page_count
                document.is_scanned = raw.ocr_used
                # Without this, page_count/is_scanned are set on this
                # in-memory object and never written back — every document,
                # including ones that extract successfully, reports
                # page_count=null and is_scanned=null forever.
                self.documents.save(document)

                # 3. submit to the structurer (LLM or rule-based: same port).
                structured = self.structurer.structure(raw)
                run.model = run.model or structured.model
                run.prompt_version = run.prompt_version or structured.prompt_version
                if structured.cost_usd is not None:
                    run.cost_usd = (run.cost_usd or Decimal(0)) + structured.cost_usd

                # 4. validate against the schema. Anything the structurer
                #    proposes that is not a real SYSCOHADA code or a real
                #    amount is dropped here, at the boundary — §11.1, "the
                #    domain never receives free text".
                doc_fields, doc_rejections = self._to_fields(
                    run.id, structured, document.id
                )

                for item in doc_fields:
                    key = (item.item_code, item.year)
                    earlier = seen_by.get(key)
                    if earlier is not None:
                        raise ExtractionFailed(
                            f"item {item.item_code} (year {item.year}) was "
                            f'found in both "{earlier}" and '
                            f'"{document.file_name}" — remove the duplicate '
                            "from one of the two documents and extract again"
                        )
                    seen_by[key] = document.file_name

                all_fields.extend(doc_fields)
                all_rejections.extend(doc_rejections)

            run.fields = all_fields
            run.rejections = all_rejections

            if not run.fields:
                raise ExtractionFailed("no usable item found in any document")

            # 5. run the consistency checks, before any human intervention.
            outcomes = run_all(run.statement())

            # 6-7. persist and move the case on.
            run.status = E.EXTRACTED
            run.finished_at = _utcnow()
            self.extractions.save(run)
            case.transition_to(E.EXTRACTED)

            self.audit.record(
                E.AuditEntry(
                    entity="ExtractionRun",
                    entity_id=run.id,
                    action="EXTRACTED",
                    author=author,
                    detail={
                        "fields": len(run.fields),
                        "documents": len(run.document_ids),
                        "engine": run.engine,
                        "checks_failed": [
                            o.code for o in outcomes if not o.passed
                        ],
                    },
                )
            )
            return run

        except Exception as exc:  # noqa: BLE001 — recorded, then re-raised
            # Exception E1: the failure is a *state*, with a recorded reason.
            # It is not a stack trace lost in a log: the case says so, and the
            # run is kept so that a second attempt stays comparable to it.
            run.status = E.EXTRACTION_FAILED
            run.failure_reason = str(exc)
            run.finished_at = _utcnow()
            self.extractions.save(run)
            case.transition_to(E.EXTRACTION_FAILED)
            self.audit.record(
                E.AuditEntry(
                    entity="ExtractionRun",
                    entity_id=run.id,
                    action="EXTRACTION_FAILED",
                    author=author,
                    detail={"reason": str(exc)},
                )
            )
            raise

    # --- helpers --------------------------------------------------------
    def _probe(self, document: E.SourceDocument) -> None:
        """Fill page_count / is_scanned at upload, so the document shows as
        Native PDF, Scanned PDF or Excel before any extraction. Optional
        (a reader without probe() is fine) and never blocks the upload: a
        file that cannot be opened here fails later, at extraction, with
        its reason recorded on the run."""
        try:
            reader = self._reader_for(document.stored_path or document.file_name)
            probe = getattr(reader, "probe", None)
            if probe is None:
                return
            page_count, needs_ocr = probe(document.stored_path or document.file_name)
            document.page_count = page_count
            document.is_scanned = needs_ocr if document.doc_type == "PDF" else None
        except Exception:  # noqa: BLE001 — labelling only, never fatal
            return

    def _reader_for(self, path: str) -> DocumentReader:
        for reader in self.readers:
            if reader.supports(path):
                return reader
        raise ExtractionFailed(f"no reader supports this file: {path}")

    def _to_fields(
        self, run_id: str, structured, document_id: str
    ) -> tuple[list[E.ExtractedField], list[E.ExtractionRejection]]:
        """Schema validation (FR-07), expressed as a filter.

        A malformed proposal is dropped, not repaired. Repairing it would be
        the system inventing data — and an invented figure that clears the
        checks is precisely the silent false positive the whole thesis is
        about.

        Collect the rejections and attach them to the run, so the evaluation
        can distinguish "the model proposed nothing" from "the model proposed
        something unusable". Those are two different failure modes in the
        typology of dossier §19.3.
        """
        fields: list[E.ExtractedField] = []
        rejections: list[E.ExtractionRejection] = []

        for item in structured.items:
            try:
                amount = Amount(item.amount)
            except (ValueError, TypeError) as exc:
                rejections.append(
                    E.ExtractionRejection(
                        raw_item=item,
                        reason=f"invalid amount: {exc}",
                    )
                )
                continue

            try:
                code = str(item.item_code).strip().upper()
                if len(code) != 2 or not code.isalpha():
                    rejections.append(
                        E.ExtractionRejection(
                            raw_item=item,
                            reason="invalid item code",
                        )
                    )
                    continue

            except Exception as exc:  # noqa: BLE001
                rejections.append(
                    E.ExtractionRejection(
                        raw_item=item,
                        reason=f"invalid item code: {exc}",
                    )
                )
                continue

            fields.append(
                E.ExtractedField(
                    item_code=code,
                    amount=amount,
                    extraction_id=run_id,
                    document_id=document_id,
                    year=item.year,
                    source_page=item.source_page,
                    confidence=(
                        Decimal(str(item.confidence)) if item.confidence is not None else None
                    ),
                    status=E.PROPOSED,
                )
            )
        return fields, rejections


def _utcnow():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)