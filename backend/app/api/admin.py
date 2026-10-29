"""The administration area — the administrator only (``require_admin``).

Everything the administrator used to do in pgAdmin or with scripts, from
the screens:

* ``GET  /api/admin/overview``            the system at a glance
* ``GET  /api/admin/audit``               the audit log, filtered, paged
* ``GET  /api/admin/audit.csv``           the same, as a CSV file
* ``GET  /api/admin/corpus``              the evaluation corpus folder
* ``POST /api/admin/corpus/packages``     add a package folder (RP002...)
* ``POST /api/admin/corpus/<p>/files``    add documents / the annotation
* ``DELETE /api/admin/corpus/<p>/files/<f>``  remove one file
* ``DELETE /api/admin/corpus/<p>``        remove an EMPTY package folder
* ``DELETE /api/admin/campaigns/<id>``    delete a stored campaign
* ``GET  /api/admin/archive``             everything deleted, kept
* ``POST /api/admin/archive/<id>/restore``  put it back exactly as it was
* ``DELETE /api/admin/archive/<id>``      delete it for good
* ``GET  /api/admin/tables``              the database tables (read-only)
* ``GET  /api/admin/tables/<name>``       the rows of one table (read-only)

Accounts go through ``/api/users`` and campaigns through
``/api/evaluations`` — the same routes and the same rules as everywhere
else, so there is one place where each rule lives.

Read-only on purpose for the data: nothing here can change a figure, a
validation or an audit entry. The administrator changes the system only
through the normal actions, and each of them is in the audit log.
"""

from __future__ import annotations

import csv
import io
import os
import re
from collections import Counter
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

from flask import Blueprint, Response, current_app, jsonify, request
from werkzeug.exceptions import Conflict, NotFound
from werkzeug.utils import secure_filename

from ..domain import entities as E
from ..domain.ports import AuditQuery
from .auth import actor, require_admin

admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")


@admin_bp.before_request
def _only_the_administrator() -> None:
    require_admin()


def container():
    return current_app.config["container"]


# ==========================================================================
# Overview
# ==========================================================================
@admin_bp.get("/overview")
def overview():
    """Counts, settings (never a secret) and the latest activity."""
    c = container()
    cases = c.cases.list()
    users = c.users.list()

    documents = [d for case in cases for d in case.documents]
    runs = [run for case in cases for run in c.extractions.list_for_case(case.id)]
    analyses = [a for case in cases for a in c.ai_analyses.list_for_case(case.id)]
    campaigns = c.evaluations.list()
    corpus_campaigns = [x for x in campaigns if x.kind == E.CAMPAIGN_CORPUS]
    recent, total_audit = c.audit.search(AuditQuery(limit=8))

    return jsonify(
        {
            "users": {
                "total": len(users),
                "active": sum(1 for u in users if u.active),
                "by_role": dict(Counter(u.role for u in users)),
                "inactive_by_role": dict(Counter(u.role for u in users if not u.active)),
            },
            "cases": {"total": len(cases), "by_status": dict(Counter(x.status for x in cases))},
            "documents": {
                "total": len(documents),
                "by_type": dict(Counter(d.doc_type for d in documents)),
                "scanned": sum(1 for d in documents if d.is_scanned),
            },
            "extractions": {
                "total": len(runs),
                "by_status": dict(Counter(r.status for r in runs)),
                "by_engine": dict(Counter(r.engine for r in runs)),
                "cost_usd": str(sum((r.cost_usd or Decimal(0)) for r in runs)),
            },
            "validated_datasets": len(c.datasets.list()),
            "ai_analyses": {
                "total": len(analyses),
                "by_status": dict(Counter(a.status for a in analyses)),
                "cost_usd": str(sum((a.cost_usd or Decimal(0)) for a in analyses)),
            },
            "campaigns": {
                "total": len(campaigns),
                "corpus": len(corpus_campaigns),
                "sensitivity": len(campaigns) - len(corpus_campaigns),
                "latest_corpus": _campaign_headline(corpus_campaigns[0]) if corpus_campaigns else None,
            },
            "audit": {
                "total": total_audit,
                "recent": [_audit_json(c, e) for e in recent],
            },
            "settings": _settings(c),
        }
    )


def _campaign_headline(campaign: E.EvaluationCampaign) -> dict:
    s = campaign.summary or {}
    silent = s.get("silent_false_positives")
    return {
        "id": campaign.id,
        "run_at": campaign.run_at.isoformat() if campaign.run_at else None,
        "author": campaign.author,
        "note": campaign.note,
        "packages": s.get("packages"),
        "evaluated": s.get("evaluated"),
        "field_accuracy": s.get("field_accuracy"),
        "ratio_accuracy": s.get("ratio_accuracy"),
        "amplification": s.get("amplification"),
        "silent_false_positives": len(silent) if isinstance(silent, list) else None,
    }


def _settings(c) -> dict:
    """How the system is configured. A password or an API key is never
    returned: only whether one is set."""
    config = c.config
    database = "memory (nothing is kept when the backend stops)"
    if c.database is not None:
        url = c.database.get_bind().url
        database = url.render_as_string(hide_password=True)
    return {
        "storage": config.storage,
        "database": database,
        "structurer": c.structurer.engine,
        "extraction_model": config.model if config.structurer == "llm" else None,
        "ai_analysis": config.ai_analysis,
        "analysis_model": config.analysis_model if config.ai_analysis == "llm" else None,
        "anthropic_api_key": "set" if config.anthropic_api_key else "not set",
        "max_cost_usd": str(config.max_cost_usd),
        "auth_required": config.auth_required,
        "max_upload_mb": config.max_upload_mb,
        "upload_dir": str(config.upload_dir),
        "corpus_dir": str(_corpus_root()),
    }


# ==========================================================================
# Audit log
# ==========================================================================
def _parse_day(value: str | None, field_name: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{field_name} must be a date like 2026-10-21") from None


def _audit_query(offset: int, limit: int) -> AuditQuery:
    args = request.args
    since = _parse_day(args.get("from"), "from")
    until = _parse_day(args.get("to"), "to")
    return AuditQuery(
        author=args.get("author") or None,
        action=args.get("action") or None,
        entity=args.get("entity") or None,
        entity_id=args.get("entity_id") or None,
        text=(args.get("q") or "").strip() or None,
        since=datetime.combine(since, time.min) if since else None,
        # "to" is the last day shown: everything before the next midnight.
        until=datetime.combine(until + timedelta(days=1), time.min) if until else None,
        offset=offset,
        limit=limit,
    )


@admin_bp.get("/audit")
def audit():
    """Who did what, newest first. Filters: author, action, entity,
    entity_id, q (free text), from / to (dates, both included); page and
    per_page (at most 200)."""
    c = container()
    per_page = max(1, min(int(request.args.get("per_page") or 50), 200))
    page = max(1, int(request.args.get("page") or 1))
    entries, total = c.audit.search(_audit_query((page - 1) * per_page, per_page))
    facets = c.audit.facets()
    kinds = _author_kinds(c)
    facets["author_kinds"] = {name: kinds.get(name, _other_kind(name)) for name in facets["authors"]}
    return jsonify(
        {
            "entries": [{**_audit_json(c, e), "author_kind": kinds.get(e.author, _other_kind(e.author))}
                        for e in entries],
            "total": total,
            "page": page,
            "per_page": per_page,
            "facets": facets,
        }
    )


def _author_kinds(c) -> dict[str, str]:
    """Who an audit author is: a current account (its role), or not."""
    return {u.full_name: u.role for u in c.users.list()}


def _other_kind(name: str) -> str:
    """An author that is no current account's full name:
    SCRIPT  — a command-line script (create_admin.py, evaluate_corpus.py);
    SYSTEM  — the application itself ("system", "evaluation", ...);
    OTHER   — a username typed at a refused sign-in, a deleted account, or
              a name since changed on My account."""
    lowered = (name or "").strip().lower()
    if lowered.endswith(".py"):
        return "SCRIPT"
    if lowered in {"system", "evaluation", "analyst", "supervisor", "administrator", "local user", "-"}:
        return "SYSTEM"
    return "OTHER"


@admin_bp.get("/audit.csv")
def audit_csv():
    """The filtered audit log as a CSV file (at most 10,000 lines)."""
    c = container()
    entries, _total = c.audit.search(_audit_query(0, 10_000))
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(["at", "author", "action", "entity", "entity_id", "about", "detail"])
    for e in entries:
        row = _audit_json(c, e)
        writer.writerow(
            [row["at"], e.author, e.action, e.entity, e.entity_id, row["about"] or "",
             _plain(e.detail) if e.detail else ""]
        )
    # A BOM so that Excel opens the accents (é, è) correctly.
    return Response(
        "\ufeff" + buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=audit_{date.today():%Y%m%d}.csv"},
    )


def _audit_json(c, entry: E.AuditEntry) -> dict:
    return {
        "id": entry.id,
        "at": entry.at.isoformat() if entry.at else None,
        "author": entry.author,
        "action": entry.action,
        "entity": entry.entity,
        "entity_id": entry.entity_id,
        "about": _about(c, entry.entity, entry.entity_id, entry.detail),
        "case_id": _case_of(c, entry.entity, entry.entity_id),
        "detail": entry.detail,
    }


def _case_label(case: E.AnalysisCase | None) -> str | None:
    return f"{case.client} · {case.fiscal_year}" if case else None


def _case_of(c, entity: str, entity_id: str) -> str | None:
    """The case an audited object belongs to, when there is one."""
    try:
        if entity == "AnalysisCase":
            return entity_id if c.cases.get(entity_id) else None
        if entity == "ExtractionRun":
            run = c.extractions.get(entity_id)
            return run.case_id if run else None
        if entity == "ValidatedDataset":
            dataset = c.datasets.get(entity_id)
            run = c.extractions.get(dataset.extraction_id) if dataset else None
            return run.case_id if run else None
        if entity == "ExtractedField":
            run = c.extractions.find_by_field(entity_id)
            return run.case_id if run else None
        if entity == "AiAnalysis":
            analysis = c.ai_analyses.get(entity_id)
            return analysis.case_id if analysis else None
        if entity == "SourceDocument":
            document = c.documents.get(entity_id)
            return document.case_id if document else None
    except Exception:  # noqa: BLE001 — a label is never worth an error
        return None
    return None


def _about(c, entity: str, entity_id: str, detail: dict | None) -> str | None:
    """A human name for what an entry is about ("ACME SARL · 2024")."""
    detail = detail or {}
    if entity == "User":
        user = c.users.get(entity_id)
        return user.full_name if user else detail.get("full_name") or detail.get("username")
    case_id = _case_of(c, entity, entity_id)
    if case_id:
        return _case_label(c.cases.get(case_id))
    if entity == "EvaluationCampaign":
        return detail.get("note") or detail.get("kind")
    if entity == "Corpus":
        return "/".join(x for x in (detail.get("package"), detail.get("file")) if x) or None
    return detail.get("client") or None


def _plain(value) -> str:
    import json  # noqa: PLC0415

    return json.dumps(value, ensure_ascii=False, default=str)


# ==========================================================================
# Evaluation corpus (the package folders the campaign reads)
# ==========================================================================
PACKAGE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$")
CORPUS_SUFFIXES = (".pdf", ".xlsx", ".xls")


def _corpus_root() -> Path:
    from ..services.corpus_campaign import DEFAULT_CORPUS  # noqa: PLC0415

    return Path(os.environ.get("CORPUS_DIR") or DEFAULT_CORPUS)


def _package_dir(name: str, must_exist: bool = True) -> Path:
    if not PACKAGE_NAME.match(name or ""):
        raise ValueError(
            "a package name has 1 to 40 letters, digits, '-' or '_' (for example RP002)"
        )
    root = _corpus_root().resolve()
    folder = (root / name).resolve()
    if folder.parent != root:
        raise ValueError("invalid package name")
    if must_exist and not folder.is_dir():
        raise NotFound(f"no package {name} in the corpus")
    return folder


def _package_json(folder: Path) -> dict:
    files = sorted(
        (f for f in folder.iterdir() if f.is_file() and not f.name.startswith("~$")),
        key=lambda f: f.name.casefold(),
    )
    annotations = [f for f in files if f.suffix.lower() in (".xlsx", ".xls")
                   and "annotation" in f.name.lower()]
    documents = [f for f in files if f.suffix.lower() in CORPUS_SUFFIXES and f not in annotations]
    if len(annotations) == 0:
        problem = "NO_ANNOTATION"
    elif len(annotations) > 1:
        problem = "SEVERAL_ANNOTATIONS"
    elif not documents:
        problem = "NO_DOCUMENT"
    else:
        problem = None
    return {
        "name": folder.name,
        "ready": problem is None,
        "problem": problem,
        "files": [
            {
                "name": f.name,
                "size": f.stat().st_size,
                "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="seconds"),
                "kind": "ANNOTATION" if f in annotations
                else "DOCUMENT" if f in documents else "OTHER",
            }
            for f in files
        ],
    }


@admin_bp.get("/corpus")
def corpus():
    root = _corpus_root()
    packages = []
    if root.is_dir():
        packages = [
            _package_json(p)
            for p in sorted(root.iterdir(), key=lambda p: p.name.casefold())
            if p.is_dir() and not p.name.startswith(("_", "."))
        ]
    return jsonify({"path": str(root), "exists": root.is_dir(), "packages": packages})


@admin_bp.post("/corpus/packages")
def create_package():
    name = str((request.get_json(silent=True) or {}).get("name") or "").strip()
    folder = _package_dir(name, must_exist=False)
    if folder.exists():
        raise Conflict(f"the package {name} already exists")
    folder.mkdir(parents=True)
    _audit_corpus("CORPUS_PACKAGE_CREATED", name)
    return jsonify(_package_json(folder)), 201


@admin_bp.post("/corpus/<package>/files")
def add_corpus_files(package: str):
    """One or more files (form field ``files``): the PDF / Excel documents
    and the annotation workbook (its name must contain "annotation").
    An existing file is never overwritten: delete it first."""
    folder = _package_dir(package)
    uploads = request.files.getlist("files")
    if not uploads:
        raise ValueError("choose at least one file")
    saved = []
    for upload in uploads:
        name = secure_filename(upload.filename or "")
        if not name or Path(name).suffix.lower() not in CORPUS_SUFFIXES:
            raise ValueError(f"{upload.filename!r}: only PDF and Excel files (.pdf, .xlsx, .xls)")
        target = folder / name
        if target.exists():
            raise Conflict(f"{name} is already in {package} — delete it first to replace it")
        upload.save(target)
        saved.append(name)
        _audit_corpus("CORPUS_FILE_ADDED", package, name)
    return jsonify({**_package_json(folder), "saved": saved}), 201


@admin_bp.delete("/corpus/<package>/files/<path:file_name>")
def delete_corpus_file(package: str, file_name: str):
    folder = _package_dir(package)
    target = (folder / file_name).resolve()
    if target.parent != folder or not target.is_file():
        raise NotFound(f"no file {file_name} in {package}")
    # Moved to the archive, not erased: the administrator can restore it.
    container().archive_service.keep_corpus_file(folder, target.name, actor(default="administrator"))
    _audit_corpus("CORPUS_FILE_DELETED", package, file_name)
    return jsonify(_package_json(folder))


@admin_bp.delete("/corpus/<package>")
def delete_package(package: str):
    """Only an empty package: its files are reference documents, each one is
    removed on purpose, one at a time."""
    folder = _package_dir(package)
    if any(folder.iterdir()):
        raise Conflict(f"{package} still has files — delete them first")
    container().archive_service.keep_corpus_package(folder, actor(default="administrator"))
    folder.rmdir()
    _audit_corpus("CORPUS_PACKAGE_DELETED", package)
    return "", 204

@admin_bp.post("/corpus/<package>/sensitivity")
def package_sensitivity(package: str):
    """A sensitivity test (§19.2) on one package's HAND READING.

    No extraction: every item of the hand reading is changed on purpose by
    1, 5 and 10 %, the ratios are recomputed, and the checks say whether
    they would have noticed. Answers which items are the most dangerous to
    misread, and which errors would pass unseen. Stored like a campaign.
    """
    from ..services.corpus_campaign import AnnotationError, load_annotation  # noqa: PLC0415

    c = container()
    folder = _package_dir(package)
    annotations = [p for p in folder.iterdir() if p.suffix.lower() in (".xlsx", ".xls")
                   and "annotation" in p.name.lower() and not p.name.startswith("~$")]
    if len(annotations) != 1:
        raise Conflict(f"{package} needs exactly one annotation workbook")
    try:
        truth = load_annotation(annotations[0]).judged()
    except AnnotationError as exc:
        raise ValueError(str(exc)) from None
    if not len(truth):
        raise ValueError(f"no judged item in the annotation workbook of {package}")
    matrix = c.evaluation.sensitivity_matrix(truth)
    interception = matrix.interception_rate()
    note = (request.get_json(silent=True) or {}).get("note")
    campaign = E.EvaluationCampaign(
        kind=E.CAMPAIGN_SENSITIVITY,
        summary={
            "cells": matrix.to_rows(),
            "criticality": {code: str(matrix.criticality(code)) for code in sorted(truth.codes())},
            "interception_rate": str(interception) if interception is not None else None,
            "package": package,
        },
        author=actor(default="administrator"),
        note=(str(note).strip() or None) if note else package,
        inputs={
            "package": package,
            "annotation": annotations[0].name,
            "ground_truth": {code: str(truth[code].value) for code in sorted(truth.codes())},
        },
    )
    c.evaluations.add(campaign)
    c.audit.record(
        E.AuditEntry(entity="EvaluationCampaign", entity_id=campaign.id, action="CAMPAIGN_RUN",
                     author=campaign.author, detail={"kind": campaign.kind, "note": campaign.note})
    )
    return jsonify({"id": campaign.id}), 201

def _audit_corpus(action: str, package: str, file_name: str | None = None) -> None:
    detail = {"package": package}
    if file_name:
        detail["file"] = file_name
    container().audit.record(
        E.AuditEntry(entity="Corpus", entity_id=package, action=action,
                     author=actor(default="administrator"), detail=detail)
    )


# ==========================================================================
# Database browser (read-only)
# ==========================================================================
#: Never shown, even to the administrator.
HIDDEN_COLUMNS = {
    "app_user": {"password_hash"},
    # The complete copy of a deletion: a deleted account's holds its hash.
    "archive_entry": {"payload"},
}


def _tables():
    from ..infra.db.models import Base  # noqa: PLC0415

    return {table.name: table for table in Base.metadata.sorted_tables}


def _need_database():
    session = container().database
    if session is None:
        raise Conflict(
            "the data browser needs STORAGE=sql — with STORAGE=memory nothing is kept in a database"
        )
    return session

@admin_bp.delete("/campaigns/<campaign_id>")
def delete_campaign(campaign_id: str):
    """Delete one stored campaign (a trial run, a run on a wrong corpus...).

    Administrator only. The campaign and its package rows are removed; the
    audit log keeps what it was (kind, date, note, headline figures), so a
    deleted measurement still leaves a trace.
    """
    c = container()
    campaign = c.evaluations.get(campaign_id)
    if campaign is None:
        raise NotFound(f"no campaign {campaign_id}")
    s = campaign.summary or {}
    archived = c.archive_service.keep_campaign(campaign, actor(default="administrator"))
    c.evaluations.delete(campaign_id)
    c.audit.record(
        E.AuditEntry(
            entity="EvaluationCampaign",
            entity_id=campaign_id,
            action="CAMPAIGN_DELETED",
            author=actor(default="administrator"),
            detail={
                "kind": campaign.kind,
                "run_at": campaign.run_at.isoformat() if campaign.run_at else None,
                "note": campaign.note,
                "field_accuracy": s.get("field_accuracy"),
                "ratio_accuracy": s.get("ratio_accuracy"),
                "archive_id": archived.id,
            },
        )
    )
    return "", 204


# --- the archive ----------------------------------------------------------
def _archive_json(entry: E.ArchiveEntry) -> dict:
    # Never the payload: a deleted account's copy holds its password hash.
    return {
        "id": entry.id,
        "kind": entry.kind,
        "entity_id": entry.entity_id,
        "label": entry.label,
        "detail": entry.detail,
        "deleted_by": entry.deleted_by,
        "deleted_at": entry.deleted_at.isoformat() if entry.deleted_at else None,
    }


@admin_bp.get("/archive")
def archive():
    """Everything deleted and kept, newest first. ``kind`` filters (CASE,
    DOCUMENT, USER, CORPUS_FILE, CORPUS_PACKAGE, CAMPAIGN); ``q`` searches
    the label and who deleted it."""
    c = container()
    kind = (request.args.get("kind") or "").strip().upper() or None
    if kind and kind not in E.ARCHIVE_KINDS:
        raise ValueError(f"kind must be one of {E.ARCHIVE_KINDS}")
    q = (request.args.get("q") or "").strip().casefold()
    entries = [
        e for e in c.archive.list(kind)
        if not q or q in e.label.casefold() or q in (e.deleted_by or "").casefold()
    ]
    counts = Counter(e.kind for e in c.archive.list())
    return jsonify({"entries": [_archive_json(e) for e in entries], "counts": dict(counts)})


def _archived(entry_id: str) -> E.ArchiveEntry:
    entry = container().archive.get(entry_id)
    if entry is None:
        raise NotFound(f"no archive entry {entry_id}")
    return entry


@admin_bp.post("/archive/<entry_id>/restore")
def restore_archived(entry_id: str):
    """Put it back exactly as it was (same identifiers). Refused (409),
    with the reason, when it would clash with what exists now."""
    entry = _archived(entry_id)
    container().archive_service.restore(entry, actor(default="administrator"),
                                        corpus_dir=_corpus_root())
    return jsonify({"restored": entry.kind, "entity_id": entry.entity_id, "label": entry.label})


@admin_bp.delete("/archive/<entry_id>")
def purge_archived(entry_id: str):
    """Delete for good: the copy, and the files only it still held."""
    entry = _archived(entry_id)
    container().archive_service.purge(entry, actor(default="administrator"))
    return "", 204

@admin_bp.get("/tables")
def tables():
    from sqlalchemy import func, select  # noqa: PLC0415

    session = container().database
    if session is None:
        return jsonify({"available": False, "tables": []})
    found = []
    for name, table in sorted(_tables().items()):
        hidden = HIDDEN_COLUMNS.get(name, set())
        found.append(
            {
                "name": name,
                "rows": session.scalar(select(func.count()).select_from(table)),
                "columns": [col.name for col in table.columns if col.name not in hidden],
            }
        )
    return jsonify({"available": True, "tables": found})


@admin_bp.get("/tables/<name>")
def table_rows(name: str):
    """One page of a table, newest first when it has a date column.
    ``q`` looks for a text in every column."""
    from sqlalchemy import DateTime, String, cast, func, or_, select  # noqa: PLC0415

    session = _need_database()
    table = _tables().get(name)
    if table is None:
        raise NotFound(f"no table {name}")
    hidden = HIDDEN_COLUMNS.get(name, set())
    columns = [col for col in table.columns if col.name not in hidden]
    per_page = max(1, min(int(request.args.get("per_page") or 50), 200))
    page = max(1, int(request.args.get("page") or 1))

    conditions = []
    text = (request.args.get("q") or "").strip()
    if text:
        like = f"%{text.lower()}%"
        conditions.append(or_(*(func.lower(cast(col, String)).like(like) for col in columns)))

    dated = next((col for col in table.columns if isinstance(col.type, DateTime)), None)
    order = [dated.desc()] if dated is not None else list(table.primary_key.columns)

    total = session.scalar(select(func.count()).select_from(table).where(*conditions))
    rows = session.execute(
        select(*columns).where(*conditions).order_by(*order)
        .offset((page - 1) * per_page).limit(per_page)
    ).all()
    return jsonify(
        {
            "name": name,
            "columns": [col.name for col in columns],
            "rows": [[_cell(value) for value in row] for row in rows],
            "total": int(total or 0),
            "page": page,
            "per_page": per_page,
        }
    )


def _cell(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (bytes, bytearray)):
        return f"<{len(value)} bytes>"
    return value