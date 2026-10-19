"""Entities -> JSON. One place, one shape.

Why a separate module rather than ``jsonify(entity)``: the JSON the frontend
consumes is a *contract*. Keeping it here means you can see the whole contract
on one screen, and changing a field name is a change you make once, on
purpose, instead of discovering it broke a page.

Amounts leave as **strings**, never as JSON numbers. JSON numbers are IEEE
doubles in every browser: 6746235223.55 survives, but the habit of sending
Decimals through a float does not survive contact with a real balance sheet.
The frontend formats; it does not compute.
"""

from __future__ import annotations

import os
import re

from ..domain import entities as E
from ..domain.checks import CheckOutcome
from ..domain.interpretation import Interpretation
from ..domain.ratios import RatioResult
from ..domain.syscohada import label_of


def case_json(case: E.AnalysisCase) -> dict:
    return {
        "id": case.id,
        "client": case.client,
        "fiscal_year": case.fiscal_year,
        "status": case.status,
        "created_at": case.created_at.isoformat(),
        "analyst": case.analyst,
        "documents": [document_json(d) for d in case.documents],
    }

#: Uploads are stored as "<case id>__<original name>" so two cases can hold
#: files with the same name. The analyst never needs to see that prefix.
_STORED_PREFIX = re.compile(r"^[0-9a-fA-F-]{36}__")

def document_display_name(file_name: str) -> str:
        """'81966f42-…__Compte_de_resultat_SOCATRANS_2023_scan.pdf'
        -> 'Compte_de_resultat_SOCATRANS_2023_scan'."""
        base = _STORED_PREFIX.sub("", file_name or "")
        return os.path.splitext(base)[0] or base

def document_type_label(document: E.SourceDocument) -> str:
        """Native PDF, Scanned PDF or Excel — what the analyst needs to know.

        A PDF with even one page that has to be read by OCR counts as scanned:
        that is what decides how reliable (and how slow) its extraction is.
        """
        if document.doc_type == "XLSX":
            return "Excel"
        if document.doc_type == "PDF":
            if document.is_scanned is True:
                return "Scanned PDF"
            if document.is_scanned is False:
                return "Native PDF"
            return "PDF"
        return document.doc_type or "Document"

def document_json(document: E.SourceDocument) -> dict:
        return {
            "id": document.id,
            "case_id": document.case_id,
            "file_name": document.file_name,
            "display_name": document_display_name(document.file_name),
            "type_label": document_type_label(document),
        "doc_type": document.doc_type,
        "sha256": document.sha256,
        "page_count": document.page_count,
        "is_scanned": document.is_scanned,
        "uploaded_at": document.uploaded_at.isoformat(),
    }

def field_json(field: E.ExtractedField) -> dict:
    return {
        "id": field.id,
        "item_code": field.item_code,
        "document_id": field.document_id,
        "label": label_of(field.item_code),
        "amount": str(field.amount.value),
        "amount_display": str(field.amount),
        "proposed_amount": (
            str(field.proposed_amount.value) if field.proposed_amount else None
        ),
        "was_corrected": field.was_corrected,
        "is_keyed": field.is_keyed,
        "year": field.year,
        "source_page": field.source_page,
        "confidence": str(field.confidence) if field.confidence is not None else None,
        "status": field.status,
        "corrected_by": field.corrected_by,
        "corrected_at": field.corrected_at.isoformat() if field.corrected_at else None,
    }

def run_json(run: E.ExtractionRun, fields: bool = True) -> dict:
    payload = {
        "id": run.id,
        "case_id": run.case_id,
        "document_ids": list(run.document_ids),
        "engine": run.engine,
        "model": run.model,
        "prompt_version": run.prompt_version,
        "status": run.status,
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "failure_reason": run.failure_reason,
        "field_count": len(run.fields),
    }
    if fields:
        payload["fields"] = [field_json(f) for f in run.fields]
    return payload


def check_json(outcome: CheckOutcome) -> dict:
    return {
        "code": outcome.code,
        "label": outcome.label,
        "severity": outcome.severity,
        "passed": outcome.passed,
        "gap": str(outcome.gap) if outcome.gap is not None else None,
        "message": outcome.message,
        "items_used": list(outcome.items_used),
    }


def ratio_json(result: RatioResult, interpretation: Interpretation | None = None) -> dict:
    payload = {
        "code": result.code,
        "name": result.name,
        "status": result.status,
        "value": str(result.value) if result.value is not None else None,
        "unit": result.unit,
        "reason": result.reason,
        # BR-04 — what the value was built from travels with the value.
        # The dashboard shows it, and the propagation analysis reads it.
        "items_used": list(result.items_used),
        "inputs": result.inputs,
    }
    if interpretation is not None:
        payload["interpretation"] = {
            "text": interpretation.text,
            "template_id": interpretation.template_id,
            "threshold_applied": interpretation.threshold_applied,
            "reference_source": interpretation.reference_source,
        }
    return payload

def ai_analysis_json(analysis: E.AiAnalysis | None) -> dict | None:
    if analysis is None:
        return None
    return {
        "id": analysis.id,
        "case_id": analysis.case_id,
        "dataset_id": analysis.dataset_id,
        "status": analysis.status,
        "sections": analysis.sections,
        "generated_sections": analysis.generated_sections,
        "was_edited": analysis.was_edited,
        "model": analysis.model,
        "prompt_version": analysis.prompt_version,
        # "analysis-v2/fr" -> "fr". Older commentaries (analysis-v1) were
        # always written in English.
        "language": (
            analysis.prompt_version.split("/", 1)[1]
            if analysis.prompt_version and "/" in analysis.prompt_version
            else ("en" if analysis.prompt_version else None)
        ),
        "cost_usd": str(analysis.cost_usd) if analysis.cost_usd is not None else None,
        "failure_reason": analysis.failure_reason,
        "generated_at": analysis.generated_at.isoformat(),
        "approved_by": analysis.approved_by,
        "approved_at": analysis.approved_at.isoformat() if analysis.approved_at else None,
    }

def dataset_json(dataset: E.ValidatedDataset) -> dict:
    return {
        "id": dataset.id,
        "extraction_id": dataset.extraction_id,
        "validated_by": dataset.validated_by,
        "validated_at": dataset.validated_at.isoformat(),
        "item_count": len(dataset.amounts),
    }