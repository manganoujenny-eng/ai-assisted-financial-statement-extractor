"""HTTP controllers. Thin on purpose.

Every function here does three things and only three: read the request,
call a service, serialise the answer. No accounting rule, no state machine,
no ``if status ==`` — all of that lives in the domain, where it is unit-tested
without a web server.

Use the file as a checklist against dossier §17.1: each route is annotated
with the endpoint and the use case it implements.
"""

from __future__ import annotations

import mimetypes
import os
from decimal import Decimal

from ..infra.export.spreadsheet import export_analysis

from flask import Blueprint, current_app, jsonify, request ,send_file
from werkzeug.exceptions import Forbidden
from werkzeug.utils import secure_filename
from dataclasses import replace

from ..domain import entities as E, interpretation
from ..domain.checks import run_all
from ..domain.interpretation import interpret_all
from ..domain.ratios import compute_all
from ..services.insight_service import build_payload
from ..services.overview_service import build_overview
from .auth import (
    actor,
    actor_role,
    auth_required,
    current_user,
    require_analyst,
    require_case_owner,
    require_supervisor,
)
from ..services.validation_service import WORKFLOW_ACTIONS
from ..domain.statement import FinancialStatement
from .serialisation import (
    ai_analysis_json,
    case_json,
    check_json,
    dataset_json,
    document_json,
    field_json,
    ratio_json,
    run_json,
)

bp = Blueprint("api", __name__, url_prefix="/api")


def container():
    return current_app.config["container"]


def _need(value, what: str):
    if value is None:
        raise KeyError(what)
    return value

def _latest_validated_dataset(c, case: E.AnalysisCase):
    """The run and dataset behind a case's current validated result.

        A case can carry more than one ExtractionRun: EXTRACTED and
        UNDER_REVIEW both allow a transition back to EXTRACTING (see
        E.ALLOWED_TRANSITIONS), and ExtractionService.run_extraction() always
        adds a new row rather than replacing the old one. Re-validating adds a
        new ValidatedDataset row on top of that, also on purpose — reopen()
        keeps the earlier snapshot rather than deleting it. So a case can have
        several (run, dataset) pairs on record, and "the" current one is not
        whichever a repository happens to return first: it is the one most
        recently validated.

        Scanning for the first run that has any dataset at all — the shape this
        replaces — looked correct until a case was reopened and re-extracted,
        at which point it could silently return a stale run/dataset depending on
        repository iteration order. This picks the maximum by validated_at
        instead, so the result is right regardless of how many times the case
        has been reopened.

        A run now belongs to the case directly (it is built from every
        document the case had at the time, not from one document — see
        ExtractionRun's docstring), so this looks the runs up by case_id
        rather than walking the case's documents one by one.
        """
    latest_run = None
    latest_dataset = None

    for run in c.extractions.list_for_case(case.id):
        dataset = c.datasets.find_by_extraction(run.id)
        if dataset is None:
            continue
        if latest_dataset is None or dataset.validated_at > latest_dataset.validated_at:
            latest_run , latest_dataset  = run , dataset

    return latest_run , latest_dataset

# ==========================================================================
# Cases — FR-01
# ==========================================================================
@bp.get("/health")
def health():
    c = container()
    return jsonify(
        {
            "status": "ok",
            "storage": c.config.storage,
            "structurer": c.structurer.engine,
            "max_upload_mb": c.config.max_upload_mb,
        }
    )


@bp.post("/cases")
def create_case():
    """POST /api/cases — FR-01. Analysts only."""
    require_analyst("create a case")
    payload = request.get_json(silent=True) or {}
    case = E.AnalysisCase(
        client=str(payload.get("client", "")).strip(),
        fiscal_year=int(payload.get("fiscal_year") or 0),
        analyst=_case_analyst(payload),
    )
    if not case.client or not case.fiscal_year:
        raise ValueError("client and fiscal_year are required")
    container().cases.add(case)
    return jsonify(case_json(case)), 201

def _case_analyst(payload: dict) -> str | None:
    """Who the new case belongs to: always the analyst who creates it.

    Only an analyst creates cases (require_analyst above), so whatever
    name the body claims is ignored once sign-in is on. With
    AUTH_REQUIRED=false the name from the request is kept, as before.
    """
    if not auth_required():
        claimed = str(payload.get("analyst") or "").strip()
        return claimed or None
    return current_user().full_name

@bp.get("/cases")
def list_cases():
        c = container()
        result = []

        for case in c.cases.list():
            payload = case_json(case)

            # run_json(..., fields=False) is a strict superset of the fields
            # this used to hand-build (id/document_id/status/engine/model/
            # field_count) — it adds failure_reason, which the cases list needs
            # so a failed run can say *why* it failed, instead of just that it
            # did. A run belongs to the case directly now (see ExtractionRun's
            # docstring), so this is one lookup per case, not one per document.
            payload["extractions"] = [
                run_json(run, fields=False) for run in c.extractions.list_for_case(case.id)
            ]
            # Who the case is waiting for, and who validated its current
            # result: the Cases page shows a supervisor's buttons from these.
            payload["assigned_supervisor"] = (
                _assigned_supervisor(c, case) if case.status == E.SUBMITTED else None
            )
            _run, current = _latest_validated_dataset(c, case)
            payload["validated_by"] = current.validated_by if current else None
            # The same, but only while that person is an active supervisor:
            # they alone may delete it or send it back (None = anyone).
            payload["validator"] = _validator(c, case)

            result.append(payload)

        return jsonify(result)


@bp.get("/cases/<case_id>")
def get_case(case_id: str):
    return jsonify(case_json(_need(container().cases.get(case_id), case_id)))


@bp.patch("/cases/<case_id>")
def update_case(case_id: str):
    """PATCH /api/cases/{id} — rename a case or correct its fiscal year.

    Bookkeeping, not a lifecycle move: it never touches ``status``, so it is
    allowed at any point in the case's life, unlike the state transitions in
    ``ALLOWED_TRANSITIONS``.
    """
    require_analyst("edit a case")
    c = container()
    case = _need(c.cases.get(case_id), case_id)
    require_case_owner(case)
    payload = request.get_json(silent=True) or {}

    case = c.case_management.update(
        case,
        client=payload.get("client"),
        fiscal_year=payload.get("fiscal_year"),
        author=actor(payload.get("author")),
    )
    return jsonify(case_json(case))


@bp.delete("/cases/<case_id>")
def delete_case(case_id: str):
    """DELETE /api/cases/{id}.

    Free before anything in the case has been validated. Once any document
    in it carries a validated result, the request body must identify the
    caller as ``"supervisor"`` or this is refused with 409 (DomainError) —
    the rule decided directly with the analyst: once validated, only a
    supervisor can delete.
    """
    c = container()
    case = _need(c.cases.get(case_id), case_id)
    payload = request.get_json(silent=True) or {}

    role = actor_role(payload.get("role"))
    if role != "supervisor":
        require_case_owner(case)
    else:
        # A supervisor deletes only a result they validated themselves.
        _require_validator(c, case, "delete it")
    # CaseService decides the rest: an analyst deletes nothing validated,
    # a supervisor deletes ANALYSED cases only.
    c.case_management.delete_case(
        case,
        role=role,
        author=actor(payload.get("author")),
    )
    return "", 204


@bp.post("/cases/<case_id>/documents")
def upload_document(case_id: str):
    """POST /api/cases/{id}/documents — FR-02, fingerprint computed here."""
    require_analyst("upload a document")
    c = container()
    case = _need(c.cases.get(case_id), case_id)
    require_case_owner(case)

    uploaded = request.files.get("file")
    if uploaded is None or not uploaded.filename:
        raise ValueError("a file is required, under the form field 'file'")

    filename = secure_filename(uploaded.filename)
    target = os.path.join(c.config.upload_dir, f"{case.id}__{filename}")
    uploaded.save(target)

    document = c.extraction.register_document(case, target)
    c.cases.save(case)
    return jsonify(document_json(document)), 201


@bp.delete("/documents/<document_id>")
def delete_document(document_id: str):
    """DELETE /api/documents/{id}.

    Same rule as DELETE /api/cases/{id}, scoped to one document: free until
    it carries a validated result, then supervisor-only (409 otherwise).
    Returns the case, since removing the case's last document resets its
    status to CREATED.
    """
    require_analyst("delete a document")
    c = container()
    document = _need(c.documents.get(document_id), document_id)
    case = _need(c.cases.get(document.case_id), document.case_id)
    require_case_owner(case)
    payload = request.get_json(silent=True) or {}

    case = c.case_management.delete_document(
        case,
        document,
        role=actor_role(payload.get("role")),
        author=actor(payload.get("author")),
    )
    return jsonify(case_json(case))


@bp.get("/documents/<document_id>/file")
def get_document_file(document_id: str):
    """GET /api/documents/{id}/file — serve the original source document.

        The review interface uses this endpoint to display the original document
        beside the extracted financial data.
        """
    document = _need(container().documents.get(document_id), document_id)

    if not document.stored_path:
        raise ValueError("document has no stored file")

    if not os.path.isfile(document.stored_path):
        raise FileNotFoundError(document.stored_path)

    extension = os.path.splitext(document.file_name)[1].lower()

    if extension == ".pdf":
        mimetype = "application/pdf"

    elif extension == ".xlsx":
        mimetype = (
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        )

    elif extension == ".xls":
        mimetype = "application/vnd.ms-excel"

    else:
        mimetype = "application/octet-stream"

    return send_file(
        document.stored_path,
        mimetype=mimetype,
        download_name=document.file_name,
        as_attachment=False
    )

@bp.get("/documents/<document_id>/preview")
def get_document_preview(document_id: str):
    document = _need(
        container().documents.get(document_id),
        document_id,
    )

    if document.doc_type != "XLSX":
        return jsonify({"error": "document is not an Excel workbook"}), 400

    from openpyxl import load_workbook

    workbook = load_workbook(
        document.stored_path,
        data_only=False,
        read_only=True,
    )

    sheets = []

    for worksheet in workbook.worksheets:
        rows = []

        for row in worksheet.iter_rows(values_only=True):
            values = [
                "" if value is None else str(value)
                for value in row
            ]

            if any(value.strip() for value in values):
                rows.append(values)

        sheets.append({
            "name": worksheet.title,
            "rows": rows,
        })

    workbook.close()

    return jsonify({
        "file_name": document.file_name,
        "doc_type": document.doc_type,
        "sheets": sheets,
    })


# ==========================================================================
# Extraction — UC-03
# ==========================================================================
@bp.post("/cases/<case_id>/extractions")
def run_extraction(case_id: str):
    """POST /api/cases/{id}/extractions — UC-03.

    Case-level, not document-level: this reads every document currently
    attached to the case and merges their proposed fields into one run (see
    ExtractionService.run_extraction and ExtractionRun's docstring). Calling
    it again later — after a document was deleted and a corrected one
    attached, say — starts a brand-new run over whatever documents the case
    has at that moment; the earlier run is kept, not replaced.

    Synchronous. NFR-03 allows 90 seconds per document, which a browser will
    wait for. The day OCR on a 40-page scan pushes past that, this becomes a
    background job returning 202 with a polling URL — and *only this function*
    changes, because nothing below it knows it is being called from HTTP.
    """
    require_analyst("run an extraction")
    c = container()
    case = _need(c.cases.get(case_id), case_id)
    require_case_owner(case)
    run = c.extraction.run_extraction(
        case, author=actor(request.args.get("author"))
    )
    c.cases.save(case)
    return jsonify(run_json(run)), 201


@bp.get("/extractions/<run_id>")
def get_extraction(run_id: str):
    run = _need(container().extractions.get(run_id), run_id)
    return jsonify(run_json(run))


@bp.get("/extractions/<run_id>/fields")
def get_fields(run_id: str):
    """GET /api/extractions/{id}/fields — the review screen's data (FR-10).

    Fields and checks together in one response, deliberately: the analyst
    reads them as one picture, and two round trips would let the screen show
    checks that no longer match the fields beside them.
    """
    run = _need(container().extractions.get(run_id), run_id)
    outcomes = run_all(run.statement())
    return jsonify(
        {
            "extraction": run_json(run, fields=False),
            "fields": [field_json(f) for f in run.fields],
            "checks": [check_json(o) for o in outcomes],
        }
    )

@bp.post("/extractions/<run_id>/fields")
def add_field(run_id: str):
    """POST /api/extractions/{id}/fields — key in an item the extractor missed.

    Body: {"item_code": "XB", "year": "N", "amount": "5198800000",
           "author": "...", "document_id": "...", "source_page": 2}
    Recorded as KEYED (never proposed), audited, and every check is rerun.
    """
    require_analyst("add an item")
    c = container()
    run = _need(c.extractions.get(run_id), run_id)
    case = _need(c.cases.get(run.case_id), run.case_id)
    require_case_owner(case)
    payload = request.get_json(silent=True) or {}

    page = payload.get("source_page")
    field, outcomes = c.validation.add_field(
        case,
        run,
        item_code=str(payload.get("item_code") or ""),
        year=str(payload.get("year") or "N"),
        amount=str(payload.get("amount") or ""),
        author=actor(payload.get("author"), default=""),
        document_id=payload.get("document_id") or None,
        source_page=int(page) if page not in (None, "") else None,
    )
    return (
        jsonify({"field": field_json(field), "checks": [check_json(o) for o in outcomes]}),
        201,
    )

@bp.patch("/fields/<field_id>")
def correct_field(field_id: str):
    """PATCH /api/fields/{id} — UC-04. Corrects, then reruns every check.

    Analysts only, on their own case, while it is EXTRACTED or UNDER_REVIEW
    (not once submitted: the supervisor must validate what they reviewed).
    """
    require_analyst("correct an item")
    c = container()
    payload = request.get_json(silent=True) or {}
    run = _need(c.extractions.find_by_field(field_id), field_id)
    case = _need(c.cases.get(run.case_id), run.case_id)
    require_case_owner(case)

    outcomes = c.validation.correct_field(
        run=run,
        field_id=field_id,
        new_amount=str(payload.get("amount")),
        author=actor(payload.get("author")),
        case=case,
    )
    field = next(f for f in run.fields if f.id == field_id)
    return jsonify({"field": field_json(field), "checks": [check_json(o) for o in outcomes]})


@bp.post("/extractions/<run_id>/validation")
def validate(run_id: str):
    """POST /api/extractions/{id}/validation — UC-06.

    If a blocking check fails and the body does not carry
    ``"acknowledge_failed_checks": true``, this returns 409 with the failing
    checks listed (see ``api/errors.py``) — the screen shows them as a
    warning and asks for confirmation. Sent again with the flag, the dataset
    is validated anyway and the response lists the checks that were failing.
    Only a literal JSON ``true`` counts, so a stray string cannot override.
    """
    # dossier §6.2: the power to validate is the supervisor's.
    require_supervisor()
    c = container()
    payload = request.get_json(silent=True) or {}
    run = _need(c.extractions.get(run_id), run_id)
    case = _need(c.cases.get(run.case_id), run.case_id)
    _require_assignee(c, case, "validate it")

    dataset = c.validation.validate(
        case,
        run,
        supervisor=actor(payload.get("supervisor"), default="supervisor"),
        acknowledge_failed_checks=payload.get("acknowledge_failed_checks") is True,
    )
    c.cases.save(case)
    body = dataset_json(dataset)
    body["failed_checks_acknowledged"] = [
        check_json(o) for o in run_all(dataset.statement()) if o.is_blocking_failure
    ]
    return jsonify(body), 201


@bp.post("/cases/<case_id>/reopen")
def reopen_case(case_id: str):
    """POST /api/cases/{id}/reopen — dossier §15.

    Moves a VALIDATED or ANALYSED case back to UNDER_REVIEW so its extraction
    can be corrected and re-validated. The existing ValidatedDataset is kept
    as a historical snapshot (ValidationService.reopen does not delete it);
    re-validating afterwards creates a fresh one.
    """
    # The supervisor's way back is a correction request (with a message,
    # addressed to the analyst); reopening is the analyst's own decision.
    require_analyst("reopen a case")
    c = container()
    payload = request.get_json(silent=True) or {}
    case = _need(c.cases.get(case_id), case_id)
    require_case_owner(case)

    # The run behind the case's current (most recently validated) dataset —
    # see _latest_validated_dataset's docstring for why "current" has to mean
    # that, and not just any extraction that happens to have ever been
    # validated.
    run, _dataset = _latest_validated_dataset(c, case)
    run = _need(run, f"validated extraction for case {case_id}")

    c.validation.reopen(
        case,
        run,
        author=actor(payload.get("author"), default="Supervisor"),
        reason=str(payload.get("reason") or "re-validate under current rules"),
    )
    c.cases.save(case)
    return jsonify(case_json(case)), 200


# ==========================================================================
# Hand-over between analyst and supervisor
# ==========================================================================
@bp.post("/cases/<case_id>/submission")
def submit_case(case_id: str):
    """POST /api/cases/{id}/submission — the analyst asks for validation.

    Body (optional): {"note": "..."}. Submits the case's newest extraction
    run. The case becomes SUBMITTED and appears in the supervisor's
    notifications and "awaiting validation" queue.
    """
    require_analyst("submit a case")
    c = container()
    case = _need(c.cases.get(case_id), case_id)
    require_case_owner(case)
    payload = request.get_json(silent=True) or {}

    runs = c.extractions.list_for_case(case.id)
    run = _need(runs[-1] if runs else None, f"extraction for case {case_id}")
    c.validation.submit(
        case,
        run,
        author=actor(payload.get("author")),
        note=str(payload.get("note") or ""),
        supervisor=_chosen_supervisor(c, payload.get("supervisor")),
    )
    c.cases.save(case)
    return jsonify(case_json(case)), 200


@bp.post("/cases/<case_id>/correction-request")
def request_correction(case_id: str):
    """POST /api/cases/{id}/correction-request — the supervisor sends a case
    back to its analyst. Body: {"message": "what to correct"} (required).

    Works on a SUBMITTED case (instead of validating it) and on a VALIDATED
    or ANALYSED one (a problem found later; the validated snapshot is kept).
    The case returns to UNDER_REVIEW and the analyst is notified.
    """
    require_supervisor()
    c = container()
    case = _need(c.cases.get(case_id), case_id)
    payload = request.get_json(silent=True) or {}

    if case.status == E.SUBMITTED:
        _require_assignee(c, case, "send it back")
        runs = c.extractions.list_for_case(case.id)
        run = runs[-1] if runs else None
    else:
        _require_validator(c, case, "send it back")
        run, _dataset = _latest_validated_dataset(c, case)
    run = _need(run, f"extraction for case {case_id}")

    c.validation.request_correction(
        case,
        run,
        supervisor=actor(payload.get("supervisor"), default="supervisor"),
        message=str(payload.get("message") or ""),
    )
    c.cases.save(case)
    return jsonify(case_json(case)), 200


def _workflow_history(c, case: E.AnalysisCase) -> list[dict]:
    """Submissions, correction requests, reopenings and validations of one
    case, oldest first — read from the audit log and the datasets.

    ``supervisor`` (SUBMITTED) is who the analyst assigned it to;
    ``supervisor_active`` says whether that person — or, on VALIDATED, the
    validator — is still an active supervisor, i.e. whether the
    assigned-only / validator-only rules still apply (see _assigned_supervisor).
    """
    active = _active_supervisors(c)
    entries = [
        {
            "action": entry.action,
            "author": entry.author,
            "at": entry.at.isoformat(),
            "message": (entry.detail or {}).get("message")
                       or (entry.detail or {}).get("note")
                       or (entry.detail or {}).get("reason")
                       or None,
            # SUBMITTED only: the supervisor the analyst assigned it to,
            # as recorded, and that person's current name if still active.
            "supervisor": (entry.detail or {}).get("supervisor"),
            "supervisor_active": _norm((entry.detail or {}).get("supervisor")) in active,
            "supervisor_now": active.get(_norm((entry.detail or {}).get("supervisor"))),
        }
        for entry in c.audit.list_for("AnalysisCase", case.id)
        if entry.action in WORKFLOW_ACTIONS
    ]
    for run in c.extractions.list_for_case(case.id):
        for dataset in c.datasets.list_for_extraction(run.id):
            entries.append(
                {
                    "action": "VALIDATED",
                    "author": dataset.validated_by,
                    "at": dataset.validated_at.isoformat(),
                    "message": None,
                    "supervisor": None,
                    "supervisor_active": _norm(dataset.validated_by) in active,
                    "supervisor_now": active.get(_norm(dataset.validated_by)),
                }
            )
    entries.sort(key=lambda item: item["at"])
    return entries


@bp.get("/cases/<case_id>/history")
def case_history(case_id: str):
    """GET /api/cases/{id}/history — who submitted, who asked for what
    correction, who validated. The review screen shows the latest request."""
    c = container()
    case = _need(c.cases.get(case_id), case_id)
    return jsonify(_workflow_history(c, case))

# --- who validates, who deletes --------------------------------------------
# The analyst assigns a submitted case to one supervisor; only that person is
# notified and may validate it or send it back. Once validated, only the
# supervisor who validated it may send it back or delete it. If that person
# is no longer an active supervisor (left, deactivated, renamed), the case
# is open to every supervisor again, so nothing can get stuck.
def _norm(name: str | None) -> str:
    return " ".join((name or "").split()).casefold()


def _active_supervisors(c) -> dict[str, str]:
    """Every name an active supervisor is known by -> their current name.

    Records keep the name in force when they were written (a validation
    signed "Paul Mbarga" stays signed "Paul Mbarga"). If that supervisor
    later renamed themselves on My account, their former names come from
    the audit trail of their account (USER_UPDATED, full_name [old, new]),
    so the cases they were assigned or validated under the old name still
    belong to them: nothing opens up to the other supervisors.
    """
    names: dict[str, str] = {}
    for u in c.users.list():
        if not (u.is_supervisor and u.active):
            continue
        names[_norm(u.full_name)] = u.full_name
        for entry in c.audit.list_for("User", u.id):
            renamed = (entry.detail or {}).get("full_name") if entry.action == "USER_UPDATED" else None
            if isinstance(renamed, (list, tuple)) and len(renamed) == 2:
                names.setdefault(_norm(renamed[0]), u.full_name)
    return names


def _assigned_supervisor(c, case: E.AnalysisCase) -> str | None:
    """The active supervisor the latest submission went to, or None."""
    submissions = sorted(
        (e for e in c.audit.list_for("AnalysisCase", case.id) if e.action == "SUBMITTED"),
        key=lambda e: e.at,
    )
    if not submissions:
        return None
    name = (submissions[-1].detail or {}).get("supervisor")
    return _active_supervisors(c).get(_norm(name)) if name else None


def _validator(c, case: E.AnalysisCase) -> str | None:
    """The active supervisor who validated the current result, or None."""
    _run, dataset = _latest_validated_dataset(c, case)
    if dataset is None:
        return None
    return _active_supervisors(c).get(_norm(dataset.validated_by))


def _is_for_me(owner: str | None, me: str | None) -> bool:
    """No owner (or sign-in off) = for every supervisor."""
    return owner is None or me is None or _norm(owner) == me


def _require_assignee(c, case: E.AnalysisCase, action: str) -> None:
    if not auth_required() or case.status != E.SUBMITTED:
        return
    assigned = _assigned_supervisor(c, case)
    if assigned and _norm(assigned) != _norm(current_user().full_name):
        raise Forbidden(f"this case was submitted to {assigned} — only they can {action}")


def _require_validator(c, case: E.AnalysisCase, action: str) -> None:
    if not auth_required():
        return
    validator = _validator(c, case)
    if validator and _norm(validator) != _norm(current_user().full_name):
        raise Forbidden(f"this result was validated by {validator} — only they can {action}")


def _chosen_supervisor(c, name) -> str | None:
    """The supervisor named on a submission, checked against the users.

    With sign-in on and at least one active supervisor, choosing one is
    required. With sign-in off (tests, demos) it stays optional.
    """
    supervisors = _active_supervisors(c)
    name = str(name or "").strip()
    if not name:
        if auth_required() and supervisors:
            raise ValueError("choose the supervisor who will validate this case")
        return None
    chosen = supervisors.get(_norm(name))
    if chosen is None:
        raise ValueError(f"{name} is not an active supervisor")
    return chosen


@bp.get("/supervisors")
def list_supervisors():
    """GET /api/supervisors — the active supervisors a case can be
    submitted to. Names only; open to every signed-in user."""
    c = container()
    return jsonify(
        sorted(
            (
                {"full_name": u.full_name, "username": u.username}
                for u in c.users.list()
                if u.is_supervisor and u.active
            ),
            key=lambda u: u["full_name"].casefold(),
        )
    )

def _latest_run_id(c, case: E.AnalysisCase) -> str | None:
    runs = c.extractions.list_for_case(case.id)
    return runs[-1].id if runs else None


@bp.get("/notifications")
def notifications():
    """GET /api/notifications — what is waiting for the signed-in user.

    Derived from the cases' state and the audit log, so nothing needs to be
    marked as read: a notification disappears when its case moves on.

    * Supervisor: every SUBMITTED case ("needs validation").
    * Analyst: each of their cases sent back with a correction request
      and not submitted again yet.
    """
    c = container()
    user = current_user() if auth_required() else None
    supervisor = user is None or user.is_supervisor
    me = " ".join(user.full_name.split()).casefold() if user else None

    items = []
    for case in c.cases.list():
        history = None
        if (
            supervisor
            and case.status == E.SUBMITTED
            and _is_for_me(_assigned_supervisor(c, case), me)
        ):
            history = _workflow_history(c, case)
            last = next((h for h in reversed(history) if h["action"] == "SUBMITTED"), None)
            items.append(
                {
                    "kind": "SUBMITTED",
                    "case_id": case.id,
                    "client": case.client,
                    "fiscal_year": case.fiscal_year,
                    "analyst": case.analyst,
                    "author": last["author"] if last else case.analyst,
                    "at": last["at"] if last else case.created_at.isoformat(),
                    "message": last["message"] if last else None,
                    "extraction_id": _latest_run_id(c, case),
                    "supervisor": _assigned_supervisor(c, case),
                }
            )
        owner =" ".join((case.analyst or "").split()).casefold()
        mine = user is None or (not user.is_supervisor and (owner == me or not owner))
        if mine and case.status == E.UNDER_REVIEW:
            history = history or _workflow_history(c, case)
            last = history[-1] if history else None
            if last and last["action"] == "CORRECTION_REQUESTED":
                items.append(
                    {
                        "kind": "CORRECTION_REQUESTED",
                        "case_id": case.id,
                        "client": case.client,
                        "fiscal_year": case.fiscal_year,
                        "analyst": case.analyst,
                        "author": last["author"],
                        "at": last["at"],
                        "message": last["message"],
                        "extraction_id": _latest_run_id(c, case),
                    }
                )
    items.sort(key=lambda item: item["at"], reverse=True)
    return jsonify(items)


# ==========================================================================
# Analysis — FR-15 to FR-18
# ==========================================================================
@bp.post("/datasets/<dataset_id>/analysis")
def analyse(dataset_id: str):
    """POST /api/datasets/{id}/analysis — ratios and interpretations.

    Item 4: this is also where the AI commentary is drafted, automatically,
    right after validation (the review screen calls this straight after
    POST /validation). Ratios, checks and the comparison are computed by the
    rule-based engine first; the model only comments on them. The draft is
    written once per dataset — calling this again does not bill again — and
    a failure of the model never fails this request.
    """
    c = container()
    dataset = _need(c.datasets.get(dataset_id), dataset_id)
    run = _need(c.extractions.get(dataset.extraction_id), dataset.extraction_id)
    case = _need(c.cases.get(run.case_id), run.case_id)

    results, interpretations = c.analysis.analyse(case, dataset)
    c.cases.save(case)
    by_code = {i.ratio_code: i for i in interpretations}
    ratios = [ratio_json(r, by_code.get(r.code)) for r in results]

    ai_analysis = _draft_ai_analysis(c, case, dataset, ratios, author=actor(default="system"))
    return jsonify(
        {
            "dataset": dataset_json(dataset),
            "ratios": ratios,
            "ai_analysis": ai_analysis_json(ai_analysis),
        }
    )


def _year_comparison(c, case: E.AnalysisCase, dataset: E.ValidatedDataset, current_ratios):
    """FR-20 — the ratio-by-ratio comparison with the previous year.

    Moved out of case_dashboard unchanged, so the AI commentary (item 4)
    comments on exactly the comparison the dashboard shows. Prefers Year
    N-1 from the same validated package; falls back to a separately
    validated previous-year case for the same client.
    """
    comparison_case = None
    comparison_dataset = None
    comparison_year = None

    prior_amounts = getattr(dataset, "prior_year_amounts", {}) or {}

    if prior_amounts:
        # Make a temporary dataset whose current amounts are the
        # package's Year N-1 amounts. Do not modify the stored dataset.
        comparison_dataset = replace(
            dataset,
            amounts=dict(prior_amounts),
            prior_year_amounts={},
        )
        comparison_case = case
        comparison_year = case.fiscal_year - 1

    else:
        previous_case = next(
            (
                candidate
                for candidate in c.cases.list()
                if candidate.id != case.id
                and candidate.client.strip().casefold()
                    == case.client.strip().casefold()
                and candidate.fiscal_year == case.fiscal_year - 1
            ),
            None,
        )

        if previous_case is not None:
            # Same recency rule as the current case: the previous case may
            # itself have been reopened and re-validated more than once, so
            # pick its most recent dataset rather than an arbitrary one.
            _, previous_dataset = _latest_validated_dataset(c, previous_case)
            if previous_dataset is not None:
                comparison_case = previous_case
                comparison_dataset = previous_dataset
                comparison_year = previous_case.fiscal_year

    if comparison_case is None or comparison_dataset is None:
        return None

    # Pure computation on purpose (no AnalysisService.analyse): looking at
    # last year's figures must not move last year's case to ANALYSED.
    previous_by_code = {
        result.code: result
        for result in compute_all(comparison_dataset.statement())
    }

    comparisons = []

    for current in current_ratios:
        previous = previous_by_code.get(current["code"])
        if previous is None:
            continue

        current_computed = current["status"] == "COMPUTED"
        previous_computed = previous.status == "COMPUTED"

        current_value = current["value"]
        previous_value = (
            str(previous.value)
            if previous.value is not None
            else None
        )

        change = None
        percent_change = None

        if (
            current_computed
            and previous_computed
            and current_value is not None
            and previous_value is not None
        ):
            current_decimal = Decimal(str(current_value))
            previous_decimal = Decimal(str(previous_value))

            change = format(current_decimal - previous_decimal, "f")

            if previous_decimal != 0:
                percent_change = format(
                    (
                        (current_decimal - previous_decimal)
                        / abs(previous_decimal)
                    ) * Decimal("100"),
                    "f",
                )

        comparisons.append({
            "code": current["code"],
            "name": current["name"],
            "unit": current["unit"],
            "current_status": current["status"],
            "current_value": current_value,
            "previous_status": previous.status,
            "previous_value": previous_value,
            "change": change,
            "percent_change": percent_change,
        })

    return {
        "current_year": case.fiscal_year,
        "previous_year": comparison_year,
        "ratios": comparisons,
    }


#: Interface languages. The frontend sends the one the user picked as the
#: Accept-Language header of every request.
UI_LANGUAGES = ("en", "fr")


def _ui_language() -> str:
    return request.accept_languages.best_match(UI_LANGUAGES) or "en"


def _draft_ai_analysis(c, case, dataset, ratios, author: str, force: bool = False):
    """Build the figures-only payload and ask InsightService for the draft.

    The commentary is written in the language of the screen that asked for
    it. "language" is not a figure: the writer takes it out of the payload
    before the payload goes into the prompt.
    """
    checks = [check_json(o) for o in run_all(dataset.statement())]
    payload = build_payload(
        amounts=dataset.amounts,
        prior_year_amounts=dataset.prior_year_amounts,
        ratios=ratios,
        checks=checks,
        year_comparison=_year_comparison(c, case, dataset, ratios),
    )
    payload["language"] = _ui_language()
    return c.insight.generate(case, dataset, payload, author=author, force=force)


@bp.get("/cases/<case_id>/analysis")
def case_dashboard(case_id: str):
    """GET /api/cases/{id}/analysis — FR-18 and FR-20, plus the AI commentary."""
    c = container()
    case = _need(c.cases.get(case_id), case_id)

    # Find the current case's validated dataset and its extraction run.
    current_run, current_dataset = _latest_validated_dataset(c, case)

    if current_dataset is None or current_run is None:
        return jsonify({
            "case": case_json(case),
            "dataset": None,
            "ratios": [],
            "checks": [],
            "year_comparison": None,
            "ai_analysis": None,
        })

    # Compute current-year ratios from the validated dataset.
    current_results, current_interpretations = c.analysis.analyse(
        case, current_dataset
    )
    current_by_code = {
        item.ratio_code: item for item in current_interpretations
    }
    current_ratios = [
        ratio_json(result, current_by_code.get(result.code))
        for result in current_results
    ]

    return jsonify({
        "case": case_json(case),
        "dataset": dataset_json(current_dataset),
        "ratios": current_ratios,
        "checks": [
            check_json(outcome)
            for outcome in run_all(current_dataset.statement())
        ],
        "year_comparison": _year_comparison(c, case, current_dataset, current_ratios),
        "ai_analysis": ai_analysis_json(c.insight.latest(current_dataset.id)),
    })


@bp.post("/cases/<case_id>/ai-analysis")
def regenerate_ai_analysis(case_id: str):
    """POST /api/cases/{id}/ai-analysis — draft the AI commentary again.

    For a FAILED attempt (no key, network, budget) or a DRAFT the analyst
    wants rewritten. An APPROVED commentary is never replaced: reopen and
    re-validate the case to get new figures and a new draft.
    """
    c = container()
    case = _need(c.cases.get(case_id), case_id)
    payload = request.get_json(silent=True) or {}
    _run, dataset = _latest_validated_dataset(c, case)
    dataset = _need(dataset, f"validated dataset for case {case_id}")

    results = compute_all(dataset.statement())
    by_code = {i.ratio_code: i for i in interpret_all(results)}
    ratios = [ratio_json(r, by_code.get(r.code)) for r in results]

    analysis = _draft_ai_analysis(
        c, case, dataset, ratios,
        author=actor(payload.get("author")),
        force=True,
    )
    return jsonify(ai_analysis_json(analysis)), 201


@bp.post("/ai-analyses/<analysis_id>/approval")
def approve_ai_analysis(analysis_id: str):
    """POST /api/ai-analyses/{id}/approval — BR-13: a named analyst approves.

    Body: {"author": "...", "sections": {...the edited commentary...}}.
    The model's original text stays on record in generated_sections.
    """
    c = container()
    analysis = _need(c.ai_analyses.get(analysis_id), analysis_id)
    payload = request.get_json(silent=True) or {}
    c.insight.approve(
        analysis,
        payload.get("sections") or analysis.sections or {},
        author=actor(payload.get("author"), default=""),
    )
    return jsonify(ai_analysis_json(analysis))

@bp.get("/supervisor/overview")
def supervisor_overview():
    """GET /api/supervisor/overview — every analyst's cases in one view.

    Supervisor only. Totals and work queues (awaiting validation, validated
    with failing checks, AI drafts awaiting approval, failed extractions),
    per-analyst activity and extraction quality, and statistics of each
    ratio across all current validated results. Read-only.
    """
    require_supervisor()
    c = container()
    return jsonify(
        build_overview(c.cases, c.extractions, c.datasets, c.ai_analyses, c.users)
    )

@bp.get("/my-cases")
def my_cases():
    """GET /api/my-cases — the signed-in person's own work, with state.

    * An analyst: the cases they own.
    * A supervisor: their validation work — the cases waiting for a
      validation (status SUBMITTED; any supervisor may validate them, there
      is no assignment) and the cases whose current result they validated.
      Each entry says which list it belongs to in ``my_queue``
      ("AWAITING_VALIDATION" or "VALIDATED_BY_ME"). Every case of every
      analyst stays on the Cases page.
    * ``?analyst=NAME`` (supervisor only) still lists one analyst's cases,
      and ``?analyst=`` empty the cases nobody has claimed.

    For each validated case: its ratios with the rule-based interpretation,
    failing checks, and the AI commentary's status (its text only once
    approved — a draft is not an analytical conclusion, BR-13).

    Read-only and side-effect free: ratios are computed directly, so
    opening this page never moves a case to ANALYSED or writes the audit.
    """
    c = container()
    analyst = (request.args.get("analyst") or "").strip()
    supervisor_view = False
    me = ""
    if auth_required():
        user = current_user()
        me = user.full_name
        if user.is_supervisor and "analyst" not in request.args:
            supervisor_view = True
        elif not user.is_supervisor or "analyst" not in request.args:
            # An analyst sees their own cases only.
            analyst = user.full_name
    wanted = analyst.casefold()

    result = []
    for case in c.cases.list():
        run, dataset = _latest_validated_dataset(c, case)

        if supervisor_view:
            # _validator follows a rename (see _active_supervisors).
            validated_by_me = (
                dataset is not None
                and case.status in {E.VALIDATED, E.ANALYSED}
                and _norm(_validator(c, case) or dataset.validated_by) == _norm(me)
            )
            if case.status == E.SUBMITTED:
                if not _is_for_me(_assigned_supervisor(c, case), " ".join(me.split()).casefold()):
                    continue
                queue = "AWAITING_VALIDATION"
            elif validated_by_me:
                queue = "VALIDATED_BY_ME"
            else:
                continue
        else:
            owner = (case.analyst or "").strip().casefold()
            if owner != wanted:
                continue
            queue = None

        entry = _my_case_entry(c, case, dataset)
        entry["my_queue"] = queue
        entry["assigned_supervisor"] = (
            _assigned_supervisor(c, case) if case.status == E.SUBMITTED else None
        )
        result.append(entry)

    return jsonify(result)


def _my_case_entry(c, case: E.AnalysisCase, dataset) -> dict:
    """One card of the My cases page: the case, its latest run and results."""
    runs = c.extractions.list_for_case(case.id)
    latest_run = runs[-1] if runs else None

    entry = case_json(case)
    entry["latest_extraction"] = (
        run_json(latest_run, fields=False) if latest_run else None
    )
    entry["dataset"] = dataset_json(dataset) if dataset else None
    entry["ratios"] = []
    entry["failed_checks"] = []
    entry["ai_analysis"] = None

    if dataset is not None:
        results = compute_all(dataset.statement())
        by_code = {i.ratio_code: i for i in interpret_all(results)}
        entry["ratios"] = [ratio_json(r, by_code.get(r.code)) for r in results]
        entry["failed_checks"] = [
            check_json(o) for o in run_all(dataset.statement()) if not o.passed
        ]
        ai = c.insight.latest(dataset.id)
        if ai is not None:
            summary = ai_analysis_json(ai)
            if ai.status != E.AI_APPROVED:
                summary["sections"] = None
                summary["generated_sections"] = None
            entry["ai_analysis"] = summary

    return entry


@bp.get("/cases/<case_id>/export")
def export_case(case_id: str):
    """GET /api/cases/{id}/export -- FR-19 spreadsheet export. """

    c = container()
    case = _need(c.cases.get(case_id), case_id)

    # Same recency rule as case_dashboard(): export the case's current
    # (most recently validated) dataset, not an arbitrary one that happens
    # to surface first when a document has more than one extraction run.
    _run, dataset = _latest_validated_dataset(c, case)
    dataset = _need(dataset, f"validated dataset for case {case_id}")

    results, interpretations = c.analysis.analyse(case, dataset)
    by_code = {i.ratio_code: i for i in interpretations}

    ratios = [
        ratio_json(result, by_code.get(result.code))
        for result in results
    ]

    checks = [
        check_json(outcome)
        for outcome in run_all(dataset.statement())
    ]

    output = export_analysis(
        case=case_json(case),
        dataset={
            **dataset_json(dataset),
            "amounts": dataset.amounts,
        },
        ratios=ratios,
        checks=checks,
    )

    return send_file(
        output,
        as_attachment=True,
        download_name=(
            f"{case.client}_{case.fiscal_year}_analysis.xlsx"
        ),
        mimetype=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
    )

    return jsonify(
        {
            "error": "not_found",
            "detail": "No validated dataset found for this case",
        }
    ), 404

# ==========================================================================
# Evaluation — Part D (week 7). Every campaign is stored (exercise 20).
# ==========================================================================
def _campaign_json(campaign: E.EvaluationCampaign, full: bool = True) -> dict:
    s = campaign.summary or {}
    silent = s.get("silent_false_positives")
    body = {
        "id": campaign.id,
        "kind": campaign.kind,
        "run_at": campaign.run_at.isoformat() if campaign.run_at else None,
        "author": campaign.author,
        "engine": campaign.engine,
        "corpus": campaign.corpus,
        "note": campaign.note,
        "headline": {
            "packages": s.get("packages"),
            "evaluated": s.get("evaluated"),
            "field_accuracy": s.get("field_accuracy"),
            "ratio_accuracy": s.get("ratio_accuracy"),
            "amplification": s.get("amplification"),
            "silent_false_positives": len(silent) if isinstance(silent, list) else None,
            "interception_rate": s.get("interception_rate"),
        },
    }
    if full:
        body.update(summary=s, inputs=campaign.inputs, packages=campaign.packages)
    return body


@bp.post("/evaluations")
def run_evaluation():
    """POST /api/evaluations — FR-21, the sensitivity campaign of §19.2.

    Give it a ground-truth statement and it perturbs every item, recomputes
    every ratio, and reports what moved and what the checks would have caught.
    The campaign is stored: the answer carries its ``id``.

    Body::

        {"ground_truth": {"BK": "100", "BT": "20", ...},
         "items": ["CP", "XI"],                 # optional, defaults to all
         "perturbations": ["0.01", "0.05", "0.10"],   # optional
         "note": "RP001 before the XB check"}         # optional
    """
    c = container()
    payload = request.get_json(silent=True) or {}
    ground_truth = FinancialStatement.from_dict(payload.get("ground_truth") or {})
    if not len(ground_truth):
        raise ValueError("ground_truth is required and must not be empty")

    items = tuple(payload["items"]) if payload.get("items") else None
    perturbations = (
        tuple(Decimal(str(p)) for p in payload["perturbations"])
        if payload.get("perturbations")
        else None
    )

    matrix = c.evaluation.sensitivity_matrix(
        ground_truth,
        items=items,
        **({"perturbations": perturbations} if perturbations else {}),
    )
    interception = matrix.interception_rate()
    result = {
        "cells": matrix.to_rows(),
        "criticality": {
            code: str(matrix.criticality(code))
            for code in (items or sorted(ground_truth.codes()))
        },
        "interception_rate": str(interception) if interception is not None else None,
    }
    campaign = E.EvaluationCampaign(
        kind=E.CAMPAIGN_SENSITIVITY,
        summary=result,
        author=actor(payload.get("author"), default="evaluation"),
        note=(str(payload["note"]).strip() or None) if payload.get("note") else None,
        inputs={
            "ground_truth": {code: str(ground_truth[code].value) for code in sorted(ground_truth.codes())},
            "items": list(items) if items else None,
            "perturbations": [str(p) for p in perturbations] if perturbations else None,
        },
    )
    c.evaluations.add(campaign)
    return jsonify({**result, "id": campaign.id, "run_at": campaign.run_at.isoformat()}), 201


@bp.post("/evaluations/corpus")
def run_corpus_evaluation():
    """POST /api/evaluations/corpus — the week 7 campaign over the corpus.

    The same campaign as ``backend/evaluate_corpus.py``, started from the
    API, on the server's corpus folder (CORPUS_DIR in .env, else
    data/corpus — never a path sent by the browser). Supervisors only: it
    reads every package, and the result is quoted in the thesis.
    Body (optional): {"note": "..."}. Answers the stored campaign.
    """
    require_supervisor()
    from ..services.corpus_campaign import DEFAULT_CORPUS, run_campaign, to_entity

    c = container()
    payload = request.get_json(silent=True) or {}
    corpus = os.environ.get("CORPUS_DIR") or DEFAULT_CORPUS
    try:
        result = run_campaign(corpus)
    except FileNotFoundError as exc:
        return jsonify({"error": "not_found", "detail": str(exc)}), 404
    campaign = to_entity(
        result,
        author=actor(payload.get("author"), default="evaluation"),
        note=(str(payload["note"]).strip() or None) if payload.get("note") else None,
    )
    c.evaluations.add(campaign)
    return jsonify(_campaign_json(campaign)), 201


@bp.get("/evaluations")
def list_evaluations():
    """GET /api/evaluations — every stored campaign, newest first, headline
    figures only. ``?kind=CORPUS`` or ``?kind=SENSITIVITY`` filters."""
    kind = (request.args.get("kind") or "").strip().upper() or None
    if kind and kind not in E.CAMPAIGN_KINDS:
        raise ValueError(f"kind must be one of {', '.join(E.CAMPAIGN_KINDS)}")
    return jsonify(
        {"campaigns": [_campaign_json(c, full=False) for c in container().evaluations.list(kind)]}
    )


@bp.get("/evaluations/<evaluation_id>")
def get_evaluation(evaluation_id: str):
    """GET /api/evaluations/{id} — FR-21, reading back a stored campaign.

    Exercise 20, decided: campaigns ARE stored. The computation is
    deterministic, but what it runs on is not frozen — the extractor, the
    checks and the corpus all change over the internship. A figure quoted
    in the thesis must be readable later exactly as it was measured, with
    the fingerprints of the files that produced it.
    """
    campaign = container().evaluations.get(evaluation_id)
    if campaign is None:
        return jsonify({"error": "not_found", "detail": "no evaluation campaign with this id"}), 404
    return jsonify(_campaign_json(campaign))