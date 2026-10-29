"""CaseService — editing and deleting a case or one of its documents.

The lifecycle on AnalysisCase (dossier §15, ``ALLOWED_TRANSITIONS``) only
ever moves a case forward or back between states; nothing in the domain
removes a case, a document, or anything built from one. That omission was
deliberate, in service of the append-only history the dossier asks for
(FR-22, BR-10) — but the analyst needs a real way to undo a mistake: a case
created with the wrong client name, a document attached in error, a whole
case abandoned before it goes anywhere. This service is where that
capability lives, kept out of the domain entities on purpose so the
append-only guarantees those still carry for everything else (the audit
log, ``proposed_amount``, ``ValidatedDataset``) are not touched by it.

The one rule governing every delete here was decided directly with the
analyst: once a case or document has a validated result attached to it —
anywhere in its history, including a reopened case whose earlier
validation is kept as a historical snapshot rather than deleted — deleting
it stops being a free action. Only a caller identifying itself as
"supervisor" may still do it. Before that point (a case just created, a
document just uploaded, an extraction that was never validated) any caller
may delete freely.

No real authentication exists in this prototype (§3.3 says so explicitly) —
``role`` here is a trusted string the caller supplies, the same pattern
``ValidationService.validate``'s ``supervisor`` parameter and ``reopen``'s
``author`` parameter already use. Wiring a real role check later touches
only the caller of this service, never its logic.
"""

from __future__ import annotations

from ..domain import entities as E
from ..domain.ports import (
    AiAnalysisRepository,
    AuditLog,
    CaseRepository,
    DatasetRepository,
    DocumentRepository,
    ExtractionRepository,
)

SUPERVISOR = "supervisor"


class CaseService:
    def __init__(
        self,
        cases: CaseRepository,
        documents: DocumentRepository,
        extractions: ExtractionRepository,
        datasets: DatasetRepository,
        audit: AuditLog,
        ai_analyses: AiAnalysisRepository | None = None,
        archive=None,
        comments=None,
    ) -> None:
        self.cases = cases
        self.documents = documents
        self.extractions = extractions
        self.datasets = datasets
        self.audit = audit
        self.ai_analyses = ai_analyses
        #: ArchiveService: a complete copy of what is deleted goes there
        #: first, so the administrator can restore it (None: no archive).
        self.archive = archive
        #: The supervisors' discussion of each case (deleted with the case).
        self.comments = comments

    # --- metadata edits ---------------------------------------------------
    def update(
        self,
        case: E.AnalysisCase,
        client: str | None = None,
        fiscal_year: int | None = None,
        author: str = "analyst",
    ) -> E.AnalysisCase:
        """Rename a case or correct its fiscal year.

        Deliberately not a domain-entity method and not a transition: this
        is bookkeeping, not a business rule, and ``ALLOWED_TRANSITIONS`` has
        nothing to say about it, so it does not go through
        ``transition_to``. The audit entry is still written — FR-22 asks for
        every change to a case, not only the ones the state machine already
        tracks.
        """
        before = {"client": case.client, "fiscal_year": case.fiscal_year}

        if client is not None:
            client = client.strip()
            if not client:
                raise ValueError("client cannot be blank")
            case.client = client

        if fiscal_year is not None:
            case.fiscal_year = int(fiscal_year)

        self.cases.save(case)
        self.audit.record(
            E.AuditEntry(
                entity="AnalysisCase",
                entity_id=case.id,
                action="UPDATED",
                author=author,
                detail={
                    "before": before,
                    "after": {"client": case.client, "fiscal_year": case.fiscal_year},
                },
            )
        )
        return case

    # --- the delete guard --------------------------------------------------
    def _case_has_validated_result(self, case: E.AnalysisCase) -> bool:
        # An extraction run now spans the case's whole set of documents, not
        # one document (see ExtractionRun's docstring) — so "has this case
        # ever produced a validated result" is a case-level question, and
        # there is no narrower "has this one document been validated" to
        # ask any more. Once any run on this case has been validated, every
        # document in it is treated as validated for the purpose of this
        # rule: a supervisor's sign-off is not something an analyst should
        # be able to erase by deleting one of the documents behind it.
        for run in self.extractions.list_for_case(case.id):
            if self.datasets.list_for_extraction(run.id):
                return True
        return False

    def _guard_delete(self, has_validated_result: bool, role: str, what: str) -> None:
        if has_validated_result and role != SUPERVISOR:
            raise E.DomainError(
                f"{what} has a validated result — only a supervisor can delete it"
            )

    def _guard_supervisor_case_delete(self, case: E.AnalysisCase, role: str) -> None:
        """A supervisor deletes finished work only: an ANALYSED case.

        Everything before that belongs to the analyst working on it. A case
        still in progress is the analyst's to delete (while nothing in it was
        validated); a VALIDATED case not yet analysed is still on its way.
        """
        if role == SUPERVISOR and case.status != E.ANALYSED:
            raise E.DomainError(
                f"a supervisor can only delete an ANALYSED case (this one is {case.status})"
            )

    # --- detaching a document from its case's extraction history ----------
    def _detach_document_from_runs(self, document: E.SourceDocument) -> None:
        """Scrub a deleted document out of the runs that used to include it.

        Runs and their fields are never deleted here, deliberately — they
        are this case's append-only history (dossier §12.1 wants two runs on
        the same case comparable), and ``_guard_delete`` above has already
        refused this call outright if any of them was ever validated. What
        does need updating is the still-live pointer: a run's
        ``document_ids`` would otherwise go on claiming it was built from a
        document that no longer exists, and a field tagged with this
        document's id would have nowhere valid to point the review screen's
        "open source" link. Both are cleared through ``save()`` so the
        in-memory and SQL adapters behave identically — relying on the
        database's own ``ON DELETE`` instead would leave the in-memory one
        silently out of step, exactly the bug class this codebase keeps
        catching.
        """
        for run in self.extractions.list_for_case(document.case_id):
            changed = False

            if document.id in run.document_ids:
                run.document_ids = [d for d in run.document_ids if d != document.id]
                changed = True

            for extracted_field in run.fields:
                if extracted_field.document_id == document.id:
                    extracted_field.document_id = None
                    changed = True

            if changed:
                self.extractions.save(run)

    def delete_document(
        self,
        case: E.AnalysisCase,
        document: E.SourceDocument,
        role: str,
        author: str = "analyst",
    ) -> E.AnalysisCase:
        """Remove one document — typically to replace it with a correct one.

        Guarded the same way ``delete_case`` is: once the CASE carries a
        validated result anywhere in its history, only a supervisor can
        still remove any of its documents. Before that point, this is
        exactly the "I uploaded the wrong file" correction: delete it, add
        the right one, and re-extract (``ExtractionService.run_extraction``
        always reads the case's *current* documents, so the next run — or
        the one after this request — picks up the change automatically).

        If this was the case's last document, the case is reset to CREATED
        — there is nothing left to extract, review or validate, and CREATED
        is where every case already starts. A case with other documents
        remaining keeps its current status: deciding whether removing one
        document should also roll back a status that other documents are
        still supporting is a judgement call past what this request asked
        for, and is left as-is rather than guessed at.
        """
        if document.case_id != case.id:
            raise ValueError(
                f"document {document.id} does not belong to case {case.id}"
            )
        if role == SUPERVISOR:
            raise E.DomainError(
                "documents are managed by the analyst — a supervisor cannot delete one"
            )

        self._guard_delete(
            self._case_has_validated_result(case),
            role,
            f"case {case.id}",
        )

        archived = self.archive.keep_document(case, document, author) if self.archive else None
        self._detach_document_from_runs(document)
        self.documents.delete(document.id)
        case.documents = [d for d in case.documents if d.id != document.id]

        if not case.documents:
            case.status = E.CREATED

        self.cases.save(case)
        self.audit.record(
            E.AuditEntry(
                entity="SourceDocument",
                entity_id=document.id,
                action="DELETED",
                author=author,
                detail={"case_id": case.id, "file_name": document.file_name,
                        **({"archive_id": archived.id} if archived else {})},
            )
        )
        return case

    def delete_case(
        self, case: E.AnalysisCase, role: str, author: str = "analyst"
    ) -> None:
        """Remove a case and everything it owns.

        Guarded once, for the case as a whole: see
        ``_case_has_validated_result``. A supervisor may only delete an
        ANALYSED case (``_guard_supervisor_case_delete``).
        """
        self._guard_supervisor_case_delete(case, role)
        self._guard_delete(
            self._case_has_validated_result(case), role, f"case {case.id}"
        )
        # The complete copy first, while everything is still there.
        archived = self.archive.keep_case(case, author) if self.archive else None
        if self.comments is not None:
            self.comments.delete_for_case(case.id)
        # AI commentary first: it refers to the case's datasets.
        if self.ai_analyses is not None:
            self.ai_analyses.delete_for_case(case.id)

        # Order matters, and it is the one every repository.delete() in this
        # codebase already assumes: every ValidatedDataset for a run before
        # the run, every run for the case before its documents. Postgres
        # enforces these foreign keys with no ON DELETE CASCADE declared, so
        # deleting out of order raises there even though the InMemory
        # adapter would silently tolerate it.
        for run in self.extractions.list_for_case(case.id):
            for dataset in self.datasets.list_for_extraction(run.id):
                self.datasets.delete(dataset.id)
            self.extractions.delete(run.id)

        for document in list(case.documents):
            self.documents.delete(document.id)

        self.cases.delete(case.id)
        self.audit.record(
            E.AuditEntry(
                entity="AnalysisCase",
                entity_id=case.id,
                action="DELETED",
                author=author,
                detail={"client": case.client, "fiscal_year": case.fiscal_year,
                        **({"archive_id": archived.id} if archived else {})},
            )
        )