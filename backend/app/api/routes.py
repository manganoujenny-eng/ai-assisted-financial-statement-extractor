"""HTTP controllers. Thin on purpose.

Every function here does three things and only three: read the request,
call a service, serialise the answer. No accounting rule, no state machine,
no ``if status ==`` — all of that lives in the domain, where it is unit-tested
without a web server.

Use the file as a checklist against dossier §17.1: each route is annotated
with the endpoint and the use case it implements.
"""

from __future__ import annotations

import os
from decimal import Decimal

from flask import Blueprint, current_app, jsonify, request
from werkzeug.utils import secure_filename

from ..domain import entities as E
from ..domain.checks import run_all
from ..domain.statement import FinancialStatement
from .serialisation import (
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
        }
    )


@bp.post("/cases")
def create_case():
    """POST /api/cases — FR-01."""
    payload = request.get_json(silent=True) or {}
    case = E.AnalysisCase(
        client=str(payload.get("client", "")).strip(),
        fiscal_year=int(payload.get("fiscal_year") or 0),
    )
    if not case.client or not case.fiscal_year:
        raise ValueError("client and fiscal_year are required")
    container().cases.add(case)
    return jsonify(case_json(case)), 201


@bp.get("/cases")
def list_cases():
    return jsonify([case_json(c) for c in container().cases.list()])


@bp.get("/cases/<case_id>")
def get_case(case_id: str):
    return jsonify(case_json(_need(container().cases.get(case_id), case_id)))


@bp.post("/cases/<case_id>/documents")
def upload_document(case_id: str):
    """POST /api/cases/{id}/documents — FR-02, fingerprint computed here."""
    c = container()
    case = _need(c.cases.get(case_id), case_id)

    uploaded = request.files.get("file")
    if uploaded is None or not uploaded.filename:
        raise ValueError("a file is required, under the form field 'file'")

    filename = secure_filename(uploaded.filename)
    target = os.path.join(c.config.upload_dir, f"{case.id}__{filename}")
    uploaded.save(target)

    document = c.extraction.register_document(case, target)
    c.cases.save(case)
    return jsonify(document_json(document)), 201


# ==========================================================================
# Extraction — UC-03
# ==========================================================================
@bp.post("/documents/<document_id>/extractions")
def run_extraction(document_id: str):
    """POST /api/documents/{id}/extractions — UC-03.

    Synchronous. NFR-03 allows 90 seconds per document, which a browser will
    wait for. The day OCR on a 40-page scan pushes past that, this becomes a
    background job returning 202 with a polling URL — and *only this function*
    changes, because nothing below it knows it is being called from HTTP.
    """
    c = container()
    document = _need(c.documents.get(document_id), document_id)
    case = _need(c.cases.get(document.case_id), document.case_id)
    author = request.args.get("author", "analyst")

    run = c.extraction.run_extraction(case, document, author=author)
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


@bp.patch("/fields/<field_id>")
def correct_field(field_id: str):
    """PATCH /api/fields/{id} — UC-04. Corrects, then reruns every check."""
    c = container()
    payload = request.get_json(silent=True) or {}
    run = _need(c.extractions.find_by_field(field_id), field_id)

    outcomes = c.validation.correct_field(
        run=run,
        field_id=field_id,
        new_amount=str(payload.get("amount")),
        author=str(payload.get("author") or "analyst"),
    )
    field = next(f for f in run.fields if f.id == field_id)
    return jsonify({"field": field_json(field), "checks": [check_json(o) for o in outcomes]})


@bp.post("/extractions/<run_id>/validation")
def validate(run_id: str):
    """POST /api/extractions/{id}/validation — UC-06.

    A refusal returns 409 with the failing checks listed; see
    ``api/errors.py``. That path is not an error in the code — it is the
    system doing its job.
    """
    c = container()
    payload = request.get_json(silent=True) or {}
    run = _need(c.extractions.get(run_id), run_id)
    document = _need(c.documents.get(run.document_id), run.document_id)
    case = _need(c.cases.get(document.case_id), document.case_id)

    dataset = c.validation.validate(
        case, run, supervisor=str(payload.get("supervisor") or "supervisor")
    )
    c.cases.save(case)
    return jsonify(dataset_json(dataset)), 201


# ==========================================================================
# Analysis — FR-15 to FR-18
# ==========================================================================
@bp.post("/datasets/<dataset_id>/analysis")
def analyse(dataset_id: str):
    """POST /api/datasets/{id}/analysis — ratios and interpretations."""
    c = container()
    dataset = _need(c.datasets.get(dataset_id), dataset_id)
    run = _need(c.extractions.get(dataset.extraction_id), dataset.extraction_id)
    document = _need(c.documents.get(run.document_id), run.document_id)
    case = _need(c.cases.get(document.case_id), document.case_id)

    results, interpretations = c.analysis.analyse(case, dataset)
    c.cases.save(case)
    by_code = {i.ratio_code: i for i in interpretations}
    return jsonify(
        {
            "dataset": dataset_json(dataset),
            "ratios": [ratio_json(r, by_code.get(r.code)) for r in results],
        }
    )


@bp.get("/cases/<case_id>/analysis")
def case_dashboard(case_id: str):
    """GET /api/cases/{id}/analysis — FR-18, the dashboard.

    The ratios are recomputed from the validated dataset rather than read
    back from a table. That is legitimate *only* because of NFR-02: the same
    validated dataset always yields exactly the same ratios, with no external
    call. A system whose ratios depended on a model call could not do this —
    and the fact that this endpoint is trivial to write is itself evidence
    that the deterministic design was the right one.
    """
    c = container()
    case = _need(c.cases.get(case_id), case_id)

    for document in case.documents:
        for run in c.extractions.list_for_document(document.id):
            dataset = c.datasets.find_by_extraction(run.id)
            if dataset is None:
                continue
            results, interpretations = c.analysis.analyse(case, dataset)
            by_code = {i.ratio_code: i for i in interpretations}
            return jsonify(
                {
                    "case": case_json(case),
                    "dataset": dataset_json(dataset),
                    "ratios": [ratio_json(r, by_code.get(r.code)) for r in results],
                    "checks": [check_json(o) for o in run_all(dataset.statement())],
                }
            )

    return jsonify({"case": case_json(case), "dataset": None, "ratios": [], "checks": []})


@bp.get("/cases/<case_id>/export")
def export_case(case_id: str):
    """GET /api/cases/{id}/export — FR-19 (priority: should).

    *** YOUR EXERCISE, and a late one ***: this is a "should", not a "must".
    Build it in week 6 if weeks 3 to 5 went well, and not before. A missing
    export costs you a bullet point; a missing evaluation costs you the
    thesis (dossier §3.3, arbitration rule).
    """
    return jsonify({"error": "not_implemented", "detail": "FR-19 — see the docstring"}), 501


# ==========================================================================
# Evaluation — Part D
# ==========================================================================
@bp.post("/evaluations")
def run_evaluation():
    """POST /api/evaluations — FR-21, the sensitivity campaign of §19.2.

    Give it a ground-truth statement and it perturbs every item, recomputes
    every ratio, and reports what moved and what the checks would have caught.

    Body::

        {"ground_truth": {"BK": "100", "BT": "20", ...},
         "items": ["CP", "XI"],                 # optional, defaults to all
         "perturbations": ["0.01", "0.05", "0.10"]}   # optional
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
    return jsonify(
        {
            "cells": matrix.to_rows(),
            "criticality": {
                code: str(matrix.criticality(code))
                for code in (items or sorted(ground_truth.codes()))
            },
            "interception_rate": str(interception) if interception is not None else None,
        }
    )


@bp.get("/evaluations/<evaluation_id>")
def get_evaluation(evaluation_id: str):
    """GET /api/evaluations/{id} — FR-21, reading back a stored campaign.

    *** YOUR EXERCISE ***: campaigns are computed but not persisted. Decide
    whether they need to be. An argument for: week 7 results must be quotable
    in the thesis months later. An argument against: the computation is
    deterministic and takes two seconds, so storing its *input* is enough.
    Both are defensible — write down which you chose and why.
    """
    return jsonify({"error": "not_implemented", "detail": "see the docstring"}), 501
