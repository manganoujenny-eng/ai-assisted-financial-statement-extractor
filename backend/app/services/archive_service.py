"""ArchiveService — every deletion, kept so the administrator can undo it.

When a case, a document, an account, a corpus file or package, or a stored
campaign is deleted, it disappears for the person who deleted it, exactly
as before. But a complete copy goes to the archive first:

* CASE      the case, its documents, every extraction run with its fields,
            every validated dataset, the AI commentary and the supervisors'
            discussion;
* DOCUMENT  the document, and which runs and fields pointed at it;
* USER      the account (with its password hash, so it signs in again);
* CORPUS_FILE / CORPUS_PACKAGE  the file is MOVED to the archive folder
            (``ARCHIVE_DIR``), not erased; a package is just its name;
* CAMPAIGN  the stored campaign with all its packages.

The administrator (Administration → Archive) restores an entry exactly as
it was — same identifiers, so the audit log, the URLs and the history still
point at the right thing — or deletes it for good. A restore that would
clash with what exists now (the same username taken again, the case of a
document deleted too...) is refused with the reason, and the entry stays.

Nothing here is an accounting rule, so it lives in services. The copy is
plain JSON (``encode`` / ``decode`` below), readable in the database and
independent of SQLAlchemy, so the same archive works with both storages.
"""

from __future__ import annotations

import dataclasses
import shutil
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from ..domain import entities as E
from ..domain import value_objects as V

# --- entities <-> plain JSON ------------------------------------------------
# Only the domain's own dataclasses can be rebuilt: the archive never turns
# arbitrary data into arbitrary objects.
_CLASSES = {
    cls.__name__: cls
    for module in (E, V)
    for cls in vars(module).values()
    if isinstance(cls, type) and dataclasses.is_dataclass(cls) and cls.__module__ == module.__name__
}


def encode(value):
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        name = type(value).__name__
        if name not in _CLASSES:
            raise TypeError(f"cannot archive a {name}")
        return {"__type__": name,
                **{f.name: encode(getattr(value, f.name)) for f in dataclasses.fields(value)}}
    if isinstance(value, Decimal):
        return {"__decimal__": str(value)}
    if isinstance(value, datetime):
        return {"__datetime__": value.isoformat()}
    if isinstance(value, (list, tuple)):
        return [encode(v) for v in value]
    if isinstance(value, dict):
        return {str(k): encode(v) for k, v in value.items()}
    return value


def decode(value):
    if isinstance(value, list):
        return [decode(v) for v in value]
    if not isinstance(value, dict):
        return value
    if "__decimal__" in value:
        return Decimal(value["__decimal__"])
    if "__datetime__" in value:
        return datetime.fromisoformat(value["__datetime__"])
    if "__type__" in value:
        cls = _CLASSES[value["__type__"]]
        # Built without calling __init__ (no validation side effects), then
        # every field set: the defaults first — a field added to the class
        # after the entry was archived gets its default — then the archived
        # values. A field removed from the class since is ignored.
        obj = cls.__new__(cls)
        for f in dataclasses.fields(cls):
            if f.default is not dataclasses.MISSING:
                object.__setattr__(obj, f.name, f.default)
            elif f.default_factory is not dataclasses.MISSING:
                object.__setattr__(obj, f.name, f.default_factory())
        names = {f.name for f in dataclasses.fields(cls)}
        for key, item in value.items():
            if key in names:
                object.__setattr__(obj, key, decode(item))
        return obj
    return {k: decode(v) for k, v in value.items()}


def _shown_name(file_name: str) -> str:
    """The name the screens show: uploads are stored as "<uuid>__name.pdf"
    (same rule as api/serialisation.py::document_display_name)."""
    head, sep, tail = (file_name or "").partition("__")
    return tail if sep and len(head) == 36 and head.count("-") == 4 else file_name


class ArchiveService:
    def __init__(self, archive, audit, cases, documents, extractions, datasets,
                 ai_analyses, users, evaluations, upload_dir=None, archive_dir=None,
                 comments=None) -> None:
        self.archive = archive
        self.audit = audit
        self.cases = cases
        self.documents = documents
        self.extractions = extractions
        self.datasets = datasets
        self.ai_analyses = ai_analyses
        self.users = users
        self.evaluations = evaluations
        self.upload_dir = Path(upload_dir) if upload_dir else None
        self.archive_dir = Path(archive_dir) if archive_dir else None
        self.comments = comments

    # --- keeping a copy (called just before each deletion) ------------------
    def _store(self, kind, entity_id, label, payload, detail, author) -> E.ArchiveEntry:
        entry = E.ArchiveEntry(kind=kind, entity_id=str(entity_id), label=label,
                               payload=encode(payload), detail=detail, deleted_by=author)
        self.archive.add(entry)
        return entry

    def keep_case(self, case: E.AnalysisCase, author: str) -> E.ArchiveEntry:
        runs = self.extractions.list_for_case(case.id)
        datasets = [d for run in runs for d in self.datasets.list_for_extraction(run.id)]
        ai = self.ai_analyses.list_for_case(case.id) if self.ai_analyses is not None else []
        messages = self.comments.list_for_case(case.id) if self.comments is not None else []
        return self._store(
            E.ARCHIVE_CASE, case.id, f"{case.client} · {case.fiscal_year}",
            {"case": case, "documents": list(case.documents), "runs": runs,
             "datasets": datasets, "ai_analyses": ai, "comments": messages},
            {"client": case.client, "fiscal_year": case.fiscal_year, "status": case.status,
             "analyst": case.analyst, "documents": len(case.documents), "runs": len(runs),
             "datasets": len(datasets), "messages": len(messages)},
            author,
        )

    def keep_document(self, case: E.AnalysisCase, document: E.SourceDocument,
                      author: str) -> E.ArchiveEntry:
        links = {}
        for run in self.extractions.list_for_case(case.id):
            fields = [f.id for f in run.fields if f.document_id == document.id]
            if document.id in run.document_ids or fields:
                links[run.id] = {"in_run": document.id in run.document_ids, "fields": fields}
        return self._store(
            E.ARCHIVE_DOCUMENT, document.id,
            f"{_shown_name(document.file_name)} — {case.client} · {case.fiscal_year}",
            {"document": document, "links": links, "case_status": case.status,
             "last_document": len(case.documents) == 1},
            {"file_name": _shown_name(document.file_name), "case_id": case.id, "client": case.client,
             "fiscal_year": case.fiscal_year, "doc_type": document.doc_type},
            author,
        )

    def keep_user(self, user: E.User, author: str) -> E.ArchiveEntry:
        return self._store(
            E.ARCHIVE_USER, user.id, user.full_name, {"user": user},
            {"username": user.username, "role": user.role, "active": user.active},
            author,
        )

    def keep_campaign(self, campaign: E.EvaluationCampaign, author: str) -> E.ArchiveEntry:
        when = campaign.run_at.strftime("%Y-%m-%d %H:%M") if campaign.run_at else ""
        label = f"{campaign.kind} · {when}" + (f" · {campaign.note}" if campaign.note else "")
        return self._store(
            E.ARCHIVE_CAMPAIGN, campaign.id, label, {"campaign": campaign},
            {"kind": campaign.kind, "run_at": campaign.run_at.isoformat() if campaign.run_at else None,
             "note": campaign.note, "packages": len(campaign.packages)},
            author,
        )

    def keep_corpus_file(self, package_dir: Path, file_name: str, author: str) -> E.ArchiveEntry:
        """MOVES the file into the archive folder (instead of erasing it)."""
        source = Path(package_dir) / file_name
        entry = self._store(
            E.ARCHIVE_CORPUS_FILE, f"{package_dir.name}/{file_name}",
            f"{package_dir.name} / {file_name}",
            {"package": package_dir.name, "file_name": file_name},
            {"package": package_dir.name, "file_name": file_name, "size": source.stat().st_size},
            author,
        )
        target = self._archived_file(entry)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
        return entry

    def keep_corpus_package(self, package_dir: Path, author: str) -> E.ArchiveEntry:
        return self._store(
            E.ARCHIVE_CORPUS_PACKAGE, package_dir.name, package_dir.name,
            {"package": package_dir.name}, {"package": package_dir.name}, author,
        )

    def _archived_file(self, entry: E.ArchiveEntry) -> Path:
        if self.archive_dir is None:
            raise E.DomainError("no archive folder is configured (ARCHIVE_DIR)")
        return self.archive_dir / entry.id / entry.payload["file_name"]

    # --- the administrator ----------------------------------------------------
    def restore(self, entry: E.ArchiveEntry, author: str, corpus_dir: Path | None = None) -> None:
        payload = decode(entry.payload)
        restore = {
            E.ARCHIVE_CASE: self._restore_case,
            E.ARCHIVE_DOCUMENT: self._restore_document,
            E.ARCHIVE_USER: self._restore_user,
            E.ARCHIVE_CAMPAIGN: self._restore_campaign,
            E.ARCHIVE_CORPUS_FILE: lambda p: self._restore_corpus_file(entry, p, corpus_dir),
            E.ARCHIVE_CORPUS_PACKAGE: lambda p: self._restore_corpus_package(p, corpus_dir),
        }[entry.kind]
        restore(payload)
        self.archive.delete(entry.id)
        self.audit.record(E.AuditEntry(
            entity=_ENTITY[entry.kind], entity_id=entry.entity_id, action="RESTORED",
            author=author, detail={"label": entry.label, "deleted_by": entry.deleted_by,
                                   "deleted_at": entry.deleted_at.isoformat()},
        ))

    def purge(self, entry: E.ArchiveEntry, author: str) -> None:
        """Delete for good: the entry, and the files only it still holds."""
        if entry.kind == E.ARCHIVE_CORPUS_FILE and self.archive_dir is not None:
            shutil.rmtree(self.archive_dir / entry.id, ignore_errors=True)
        if entry.kind in (E.ARCHIVE_CASE, E.ARCHIVE_DOCUMENT):
            payload = decode(entry.payload)
            documents = payload.get("documents") or [payload.get("document")]
            for document in documents:
                self._remove_upload(document)
        self.archive.delete(entry.id)
        self.audit.record(E.AuditEntry(
            entity=_ENTITY[entry.kind], entity_id=entry.entity_id, action="PURGED",
            author=author, detail={"label": entry.label, "deleted_by": entry.deleted_by},
        ))

    # --- restoring, kind by kind -----------------------------------------------
    def _restore_case(self, p: dict) -> None:
        case: E.AnalysisCase = p["case"]
        if self.cases.get(case.id) is not None:
            raise E.DomainError(f"the case {case.client} · {case.fiscal_year} already exists")
        case.documents = list(p["documents"])
        self.cases.add(case)
        for document in p["documents"]:
            self.documents.add(document)
        for run in p["runs"]:
            self.extractions.add(run)
        for dataset in p["datasets"]:
            self.datasets.add(dataset)
        if self.ai_analyses is not None:
            for analysis in p["ai_analyses"]:
                self.ai_analyses.add(analysis)
        if self.comments is not None:
            for comment in p.get("comments") or []:
                self.comments.add(comment)

    def _restore_document(self, p: dict) -> None:
        document: E.SourceDocument = p["document"]
        case = self.cases.get(document.case_id)
        if case is None:
            raise E.DomainError(
                f"the case of {_shown_name(document.file_name)} was deleted too — restore the case first"
            )
        if self.documents.get(document.id) is not None:
            raise E.DomainError(f"{_shown_name(document.file_name)} is already in its case")
        if self.documents.find_by_sha256(document.sha256, case.id) is not None:
            raise E.DomainError(f"the same file as {_shown_name(document.file_name)} was uploaded to the case again")
        self.documents.add(document)
        case.documents = [*case.documents, document]
        for run_id, link in p["links"].items():
            run = self.extractions.get(run_id)
            if run is None:
                continue
            if link["in_run"] and document.id not in run.document_ids:
                run.document_ids = [*run.document_ids, document.id]
            for f in run.fields:
                if f.id in link["fields"]:
                    f.document_id = document.id
            self.extractions.save(run)
        # Deleting the last document put the case back to CREATED; if nothing
        # has happened to it since, it goes back to where it was.
        if p.get("last_document") and case.status == E.CREATED and len(case.documents) == 1:
            case.status = p["case_status"]
        self.cases.save(case)

    def _restore_user(self, p: dict) -> None:
        user: E.User = p["user"]
        if self.users.get(user.id) is not None:
            raise E.DomainError(f"the account {user.username} already exists")
        if self.users.get_by_username(user.username) is not None:
            raise E.DomainError(f"the username {user.username} is taken by another account now")
        if any(u.full_name.casefold() == user.full_name.casefold() for u in self.users.list()):
            raise E.DomainError(f"another account is called {user.full_name} now")
        if user.is_superadmin and any(u.is_superadmin for u in self.users.list()):
            raise E.DomainError("a super administrator already exists — there is only one")
        self.users.add(user)

    def _restore_campaign(self, p: dict) -> None:
        campaign: E.EvaluationCampaign = p["campaign"]
        if self.evaluations.get(campaign.id) is not None:
            raise E.DomainError("this campaign already exists")
        self.evaluations.add(campaign)

    def _restore_corpus_file(self, entry: E.ArchiveEntry, p: dict, corpus_dir) -> None:
        if corpus_dir is None:
            raise E.DomainError("no corpus folder is configured")
        source = self._archived_file(entry)
        if not source.is_file():
            raise E.DomainError(f"the archived file {p['file_name']} is missing from the archive folder")
        target = Path(corpus_dir) / p["package"] / p["file_name"]
        if target.exists():
            raise E.DomainError(f"{p['package']} already has a file called {p['file_name']}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
        shutil.rmtree(source.parent, ignore_errors=True)

    def _restore_corpus_package(self, p: dict, corpus_dir) -> None:
        if corpus_dir is None:
            raise E.DomainError("no corpus folder is configured")
        folder = Path(corpus_dir) / p["package"]
        if folder.exists():
            raise E.DomainError(f"the package {p['package']} already exists")
        folder.mkdir(parents=True)

    def _remove_upload(self, document) -> None:
        """An uploaded file, removed once nothing live and nothing else in
        the archive needs it. Only inside the upload folder."""
        if document is None or not document.stored_path or self.upload_dir is None:
            return
        path = Path(document.stored_path).resolve()
        if self.upload_dir.resolve() not in path.parents:
            return
        if self.documents.get(document.id) is not None:
            return
        if path.is_file():
            path.unlink()


#: The audit "entity" of each kind (the same names the deletions use).
_ENTITY = {
    E.ARCHIVE_CASE: "AnalysisCase",
    E.ARCHIVE_DOCUMENT: "SourceDocument",
    E.ARCHIVE_USER: "User",
    E.ARCHIVE_CORPUS_FILE: "Corpus",
    E.ARCHIVE_CORPUS_PACKAGE: "Corpus",
    E.ARCHIVE_CAMPAIGN: "EvaluationCampaign",
}
