"""InsightService — AI commentary on a validated analysis (item 4).

The split of work, stated once:

* **Rule-based** (deterministic, auditable): extraction, the consistency
  checks, the ratios, and the template interpretation of each ratio. None
  of that changes here.
* **Language model**: commentary *about* those results — an overview, a
  sentence or two per ratio, what the checks mean for reliability, what the
  year-on-year comparison shows, and points of attention.

Three rules keep the second part safe:

1. **Figures only** (NFR-04). ``build_payload`` sends validated amounts,
   ratios, check results and the comparison — labelled N and N-1, with no
   client name, no fiscal year and no document. Nothing else leaves.
2. **Draft until approved** (BR-13). What the model writes is stored as a
   DRAFT. It becomes part of the analysis only when a named analyst
   approves it (``approve``), and the model's original text is kept beside
   the approved one.
3. **Never blocks the analysis.** If the model is unavailable or answers
   nonsense, the AI analysis is recorded as FAILED with the reason; the
   validated dataset, ratios and templates are untouched.
"""

from __future__ import annotations

from ..domain import entities as E
from ..domain.ports import AiAnalysisRepository, AnalysisWriter, AuditLog
from ..domain.syscohada import label_of

SECTION_KEYS = ("overview", "ratios", "checks", "comparison", "attention")
MAX_SECTION_CHARS = 4000


def build_payload(
    amounts: dict,
    prior_year_amounts: dict,
    ratios: list[dict],
    checks: list[dict],
    year_comparison: dict | None,
) -> dict:
    """Everything the model may see. Figures only — see module docstring.

    ``ratios`` and ``checks`` are the same JSON shapes the dashboard
    receives (``ratio_json`` / ``check_json``), so the model comments on
    exactly what the analyst sees.
    """
    codes = sorted(set(amounts) | set(prior_year_amounts))
    return {
        "currency": "FCFA",
        "framework": "SYSCOHADA revised",
        "items": [
            {
                "code": code,
                "label": label_of(code),
                "N": amounts.get(code),
                "N-1": prior_year_amounts.get(code),
            }
            for code in codes
        ],
        "ratios": [
            {
                "code": r.get("code"),
                "name": r.get("name"),
                "status": r.get("status"),
                "value": r.get("value"),
                "unit": r.get("unit"),
                "reason": r.get("reason"),
                "items_used": r.get("items_used"),
                "template_interpretation": (r.get("interpretation") or {}).get("text"),
                "documented_threshold": (r.get("interpretation") or {}).get(
                    "threshold_applied"
                ),
            }
            for r in ratios
        ],
        "checks": [
            {
                "code": ch.get("code"),
                "label": ch.get("label"),
                "severity": ch.get("severity"),
                "passed": ch.get("passed"),
                "gap": ch.get("gap"),
                "message": ch.get("message"),
            }
            for ch in checks
        ],
        "comparison": (
            [
                {
                    "code": row.get("code"),
                    "name": row.get("name"),
                    "unit": row.get("unit"),
                    "N": row.get("current_value"),
                    "N-1": row.get("previous_value"),
                    "change": row.get("change"),
                    "percent_change": row.get("percent_change"),
                }
                for row in (year_comparison or {}).get("ratios", [])
            ]
            if year_comparison
            else None
        ),
    }


def clean_sections(sections: object, ratio_codes: set[str] | None = None) -> dict:
    """The hard boundary for commentary, model-written or analyst-edited.

    Same idea as ClaudeStructurer._parse: the shape is right or it is
    refused. No repair, no salvage of half an answer.
    """
    if not isinstance(sections, dict):
        raise ValueError("commentary must be an object")

    def text(key: str) -> str:
        value = sections.get(key) or ""
        if not isinstance(value, str):
            raise ValueError(f"'{key}' must be text")
        value = value.strip()
        if len(value) > MAX_SECTION_CHARS:
            raise ValueError(f"'{key}' is longer than {MAX_SECTION_CHARS} characters")
        return value

    ratios_in = sections.get("ratios") or {}
    if isinstance(ratios_in, list):  # the model answers a list of {code, commentary}
        ratios_in = {
            str(entry.get("code", "")).strip().upper(): entry.get("commentary", "")
            for entry in ratios_in
            if isinstance(entry, dict)
        }
    if not isinstance(ratios_in, dict):
        raise ValueError("'ratios' must map a ratio code to its commentary")

    ratios_out = {}
    for code, commentary in ratios_in.items():
        code = str(code).strip().upper()
        if ratio_codes is not None and code not in ratio_codes:
            raise ValueError(f"commentary for an unknown ratio: {code}")
        if not isinstance(commentary, str):
            raise ValueError(f"commentary for {code} must be text")
        ratios_out[code] = commentary.strip()[:MAX_SECTION_CHARS]

    attention_in = sections.get("attention") or []
    if not isinstance(attention_in, list) or not all(
        isinstance(point, str) for point in attention_in
    ):
        raise ValueError("'attention' must be a list of short texts")

    return {
        "overview": text("overview"),
        "ratios": ratios_out,
        "checks": text("checks"),
        "comparison": text("comparison"),
        "attention": [point.strip() for point in attention_in if point.strip()][:10],
    }


class InsightService:
    def __init__(
        self,
        writer: AnalysisWriter | None,
        analyses: AiAnalysisRepository,
        audit: AuditLog,
        unavailable_reason: str = "AI analysis is not configured",
    ) -> None:
        self.writer = writer
        self.analyses = analyses
        self.audit = audit
        self.unavailable_reason = unavailable_reason

    def latest(self, dataset_id: str) -> E.AiAnalysis | None:
        return self.analyses.latest_for_dataset(dataset_id)

    def generate(
        self,
        case: E.AnalysisCase,
        dataset: E.ValidatedDataset,
        payload: dict,
        author: str = "system",
        force: bool = False,
    ) -> E.AiAnalysis:
        """Write (or reuse) the AI draft for this dataset.

        Without ``force``, a dataset that already has a draft or an approved
        commentary keeps it — no second bill for the same figures. ``force``
        regenerates a DRAFT or a FAILED one; an APPROVED commentary is never
        replaced (reopen and re-validate the case for new figures instead).
        """
        existing = self.analyses.latest_for_dataset(dataset.id)
        if existing is not None:
            if existing.status == E.AI_APPROVED:
                return existing
            if existing.status == E.AI_DRAFT and not force:
                return existing

        analysis = E.AiAnalysis(case_id=case.id, dataset_id=dataset.id)
        ratio_codes = {r["code"] for r in payload.get("ratios", []) if r.get("code")}

        if self.writer is None:
            analysis.status = E.AI_FAILED
            analysis.failure_reason = self.unavailable_reason
        else:
            try:
                draft = self.writer.write(payload)
                sections = clean_sections(draft.sections, ratio_codes)
                analysis.generated_sections = sections
                analysis.sections = sections
                analysis.model = draft.model
                analysis.prompt_version = draft.prompt_version
                analysis.cost_usd = draft.cost_usd
            except Exception as exc:  # noqa: BLE001 — recorded, never raised
                analysis.status = E.AI_FAILED
                analysis.failure_reason = str(exc) or exc.__class__.__name__

        self.analyses.add(analysis)
        self.audit.record(
            E.AuditEntry(
                entity="AiAnalysis",
                entity_id=analysis.id,
                action=(
                    "AI_ANALYSIS_FAILED"
                    if analysis.status == E.AI_FAILED
                    else "AI_ANALYSIS_DRAFTED"
                ),
                author=author,
                detail={
                    "dataset_id": dataset.id,
                    "model": analysis.model,
                    "prompt_version": analysis.prompt_version,
                    "cost_usd": str(analysis.cost_usd)
                    if analysis.cost_usd is not None
                    else None,
                    "failure_reason": analysis.failure_reason,
                },
            )
        )
        return analysis

    def approve(
        self, analysis: E.AiAnalysis, sections: dict, author: str
    ) -> E.AiAnalysis:
        ratio_codes = set((analysis.generated_sections or {}).get("ratios", {}))
        analysis.approve(clean_sections(sections, ratio_codes or None), author)
        self.analyses.save(analysis)
        self.audit.record(
            E.AuditEntry(
                entity="AiAnalysis",
                entity_id=analysis.id,
                action="AI_ANALYSIS_APPROVED",
                author=analysis.approved_by,
                detail={
                    "dataset_id": analysis.dataset_id,
                    "edited_by_analyst": analysis.was_edited,
                },
            )
        )
        return analysis