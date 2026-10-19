"""The SQL repositories had no test coverage at all before this — only their
in-memory twins did (test_memory_repositories.py). That gap is exactly how
SqlDocumentRepository ended up with no ``save()`` method: nothing exercised
"mutate a document after it was added, then read it back" against a real
database, where — unlike the in-memory repository, whose dict holds the very
same Python object by reference — a mutation made on a domain entity is
invisible to the database until something writes it back.

ExtractionService.run_extraction() learns page_count and is_scanned only once
the reader has opened the file, and sets both directly on the SourceDocument
it was handed. Without a save() call (and a save() method to call), that
mutation never reaches the document table: every document, including ones
whose extraction succeeded, reports page_count=null and is_scanned=null
forever. That is exactly what hid, for a while, the real cause of client4's
failing document being a scan: the UI never saw it, because this field never
reached the database.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.domain import entities as E
from app.infra.db.models import DocumentRow
from app.infra.db.repositories import SqlCaseRepository, SqlDocumentRepository
from app.infra.db.session import create_schema, make_engine, make_session_factory


def _session() -> Session:
    engine = make_engine("sqlite:///:memory:")
    create_schema(engine)
    return make_session_factory(engine)()


def test_save_persists_page_count_and_is_scanned():
    session = _session()
    cases = SqlCaseRepository(session)
    documents = SqlDocumentRepository(session)

    case = E.AnalysisCase(client="ACME SARL", fiscal_year=2024)
    cases.add(case)

    document = E.SourceDocument(
        case_id=case.id,
        file_name="statement.pdf",
        doc_type="PDF",
        sha256="a" * 64,
    )
    documents.add(document)

    # The same mutation ExtractionService.run_extraction() makes once the
    # reader has actually opened the file.
    document.page_count = 2
    document.is_scanned = True
    documents.save(document)

    row = session.get(DocumentRow, document.id)
    assert row.page_count == 2
    assert row.is_scanned is True

    # And through the repository's own read path, not just the raw row.
    reloaded = documents.get(document.id)
    assert reloaded.page_count == 2
    assert reloaded.is_scanned is True

def test_find_by_sha256_is_scoped_to_the_case_not_global():
    """register_document()'s dedup check only ever proves two uploads are
    the same bytes, not that they belong to the same client — scoping this
    query to case_id is what stops a second, unrelated case that happens
    to upload a byte-identical file (an empty template, say) from silently
    receiving the FIRST case's document.
    """
    session = _session()
    cases = SqlCaseRepository(session)
    documents = SqlDocumentRepository(session)

    case_one = E.AnalysisCase(client="client A", fiscal_year=2024)
    case_two = E.AnalysisCase(client="client B", fiscal_year=2024)
    cases.add(case_one)
    cases.add(case_two)

    document_one = E.SourceDocument(
        case_id=case_one.id,
        file_name="template.xlsx",
        doc_type="XLSX",
        sha256="b" * 64,
    )
    documents.add(document_one)

    # Case two has never uploaded anything — same bytes, different case —
    # so this must find nothing, not case one's document.
    assert documents.find_by_sha256("b" * 64, case_two.id) is None

    # Case one re-uploading its own file is exactly what NFR-08 means to
    # catch, and still does.
    assert documents.find_by_sha256("b" * 64, case_one.id).id == document_one.id