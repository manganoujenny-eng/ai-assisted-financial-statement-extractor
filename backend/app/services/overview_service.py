"""The supervisor's view across every analyst (item 5).

Read-only and side-effect free: nothing here moves a case, writes the audit
or calls a model. Ratios are recomputed from each case's current validated
dataset with the same rule-based engine the dashboard uses, so the numbers
here can never disagree with a case's own dashboard.

"Current" means the most recently validated dataset of a case that is
VALIDATED or ANALYSED now — a reopened case is back under review and its
earlier figures are not a current result.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal
from statistics import median

from ..domain import entities as E
from ..domain.checks import run_all
from ..domain.interpretation import THRESHOLDS
from ..domain.ratios import compute_all

IN_PROGRESS = {E.EXTRACTED, E.UNDER_REVIEW, E.SUBMITTED}
DONE = {E.VALIDATED, E.ANALYSED}


def _latest_validated(extractions, datasets, case_id):
    best_run, best_dataset = None, None
    for run in extractions.list_for_case(case_id):
        dataset = datasets.find_by_extraction(run.id)
        if dataset is not None and (
            best_dataset is None or dataset.validated_at > best_dataset.validated_at
        ):
            best_run, best_dataset = run, dataset
    return best_run, best_dataset


def _fmt(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value.quantize(Decimal("0.01")), "f")


def build_overview(cases, extractions, datasets, ai_analyses, users) -> dict:
    rows = []
    ratio_values: dict[str, list[Decimal]] = defaultdict(list)
    ratio_meta: dict[str, dict] = {}
    not_computable: Counter = Counter()
    check_failures: Counter = Counter()
    check_labels: dict[str, str] = {}

    for case in cases.list():
        runs = extractions.list_for_case(case.id)
        latest_run = runs[-1] if runs else None
        run, dataset = _latest_validated(extractions, datasets, case.id)
        current = dataset if case.status in DONE else None

        quality_run = run if current is not None else latest_run
        fields = quality_run.fields if quality_run is not None else []
        keyed = sum(1 for f in fields if f.is_keyed)
        corrected = sum(1 for f in fields if not f.is_keyed and f.was_corrected)
        proposed = sum(1 for f in fields if not f.is_keyed)

        row = {
            "id": case.id,
            "client": case.client,
            "fiscal_year": case.fiscal_year,
            "analyst": case.analyst,
            "status": case.status,
            "created_at": case.created_at.isoformat(),
            "documents": len(case.documents),
            "latest_extraction_id": latest_run.id if latest_run else None,
            "latest_extraction_status": latest_run.status if latest_run else None,
            "failure_reason": latest_run.failure_reason if latest_run else None,
            "validated_by": current.validated_by if current else None,
            "validated_at": current.validated_at.isoformat() if current else None,
            "failed_blocking_checks": [],
            "ai_status": None,
            "ratios": {},
            "fields_proposed": proposed,
            "fields_corrected": corrected,
            "fields_keyed": keyed,
        }

        if current is not None:
            for outcome in run_all(current.statement()):
                check_labels[outcome.code] = outcome.label
                if not outcome.passed:
                    check_failures[outcome.code] += 1
                    if outcome.is_blocking_failure:
                        row["failed_blocking_checks"].append(outcome.code)

            for result in compute_all(current.statement()):
                ratio_meta[result.code] = {"name": result.name, "unit": result.unit}
                if result.is_computed and result.value is not None:
                    ratio_values[result.code].append(result.value)
                    row["ratios"][result.code] = str(result.value)
                else:
                    not_computable[result.code] += 1
                    row["ratios"][result.code] = None

            ai = ai_analyses.latest_for_dataset(current.id)
            row["ai_status"] = ai.status if ai else None

        rows.append(row)

    # --- per analyst -------------------------------------------------------
    # Grouped case-insensitively: "helena" typed on one case before item 5
    # and the user "Helena" are the same person.
    by_analyst: dict[str, dict] = {}
    known = {u.full_name.casefold(): u for u in users.list()}
    names: dict[str, str] = {}
    for r in rows:
        key = (r["analyst"] or "").strip().casefold()
        names.setdefault(key, known[key].full_name if key in known else (r["analyst"] or "").strip())
    for key, user in known.items():
        if user.role == E.ROLE_ANALYST and user.active:
            names.setdefault(key, user.full_name)
    for key, name in sorted(names.items(), key=lambda item: item[1].casefold()):
        mine = [r for r in rows if (r["analyst"] or "").strip().casefold() == key]
        proposed = sum(r["fields_proposed"] for r in mine)
        corrected = sum(r["fields_corrected"] for r in mine)
        by_analyst[key] = {
            "analyst": name or None,
            "role": known[key].role if key in known else None,
            "active": known[key].active if key in known else None,
            "cases": len(mine),
            "by_status": dict(Counter(r["status"] for r in mine)),
            "in_progress": sum(1 for r in mine if r["status"] in IN_PROGRESS),
            "awaiting_validation": sum(1 for r in mine if r["status"] == E.SUBMITTED),
            "validated": sum(1 for r in mine if r["status"] in DONE),
            "validated_with_failures": sum(1 for r in mine if r["failed_blocking_checks"]),
            "ai_drafts_pending": sum(1 for r in mine if r["ai_status"] == E.AI_DRAFT),
            "fields_proposed": proposed,
            "fields_corrected": corrected,
            "fields_keyed": sum(r["fields_keyed"] for r in mine),
            "correction_rate": (
                _fmt(Decimal(corrected) * 100 / Decimal(proposed)) if proposed else None
            ),
        }

    # --- ratio statistics across current results -----------------------------
    ratio_stats = []
    for code in sorted(ratio_meta):
        values = sorted(ratio_values.get(code, []))
        threshold = THRESHOLDS.get(code)
        ratio_stats.append(
            {
                "code": code,
                "name": ratio_meta[code]["name"],
                "unit": ratio_meta[code]["unit"],
                "computed": len(values),
                "not_computable": not_computable.get(code, 0),
                "min": _fmt(values[0]) if values else None,
                "median": _fmt(Decimal(median(values))) if values else None,
                "mean": _fmt(sum(values) / len(values)) if values else None,
                "max": _fmt(values[-1]) if values else None,
                "threshold": str(threshold.value) if threshold else None,
                "below_threshold": (
                    sum(1 for v in values if v < threshold.value) if threshold else None
                ),
            }
        )

    validated_rows = [r for r in rows if r["status"] in DONE]
    return {
        "totals": {
            "cases": len(rows),
            "by_status": dict(Counter(r["status"] for r in rows)),
            # Submitted by the analyst: the only cases a supervisor can validate.
            "awaiting_validation": sum(1 for r in rows if r["status"] == E.SUBMITTED),
            "validated": len(validated_rows),
            "validated_with_failures": sum(1 for r in validated_rows if r["failed_blocking_checks"]),
            "ai_drafts_pending": sum(1 for r in rows if r["ai_status"] == E.AI_DRAFT),
            "extraction_failed": sum(1 for r in rows if r["status"] == E.EXTRACTION_FAILED),
            "analysts": sum(1 for u in known.values() if u.role == E.ROLE_ANALYST and u.active),
        },
        "queues": {
            "awaiting_validation": [r for r in rows if r["status"] == E.SUBMITTED],
            "validated_with_failures": [r for r in validated_rows if r["failed_blocking_checks"]],
            "ai_drafts_pending": [r for r in rows if r["ai_status"] == E.AI_DRAFT],
            "extraction_failed": [r for r in rows if r["status"] == E.EXTRACTION_FAILED],
        },
        "analysts": list(by_analyst.values()),
        "ratios": ratio_stats,
        "checks": [
            {"code": code, "label": check_labels.get(code, code), "failed": check_failures[code]}
            for code in sorted(check_labels)
        ],
        "cases": rows,
    }