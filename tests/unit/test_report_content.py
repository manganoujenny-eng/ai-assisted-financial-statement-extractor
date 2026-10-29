"""What the exported report says: a short reading of the analysis.

Both exports (PDF and Excel) open with the same summary, built here from
the validated results only, by fixed rules, in the screen's language:

* a verdict paragraph (the key figures, the overall picture, how far the
  figures can be trusted);
* strengths and weaknesses — a ratio is called good or bad ONLY against a
  documented reference (R1, R3: 1.0) or by its sign (a profit, a loss,
  negative equity), never by taste (BR-14); trends of 10 % or more on a
  ratio compared with the previous year, and revenue moving 5 % or more;
* what the figures can be relied on for (checks, corrections, who
  validated);
* points of attention (ratios not computable, ratios without a reference,
  failed warnings, no previous year);
* the AI commentary, only once approved (BR-13).
"""

from __future__ import annotations

import copy

from app.infra.export.report_content import build_report

CASE = {"client": "SOCATRANS", "fiscal_year": 2024, "analyst": "Helena Ndongo", "status": "ANALYSED"}
DATASET = {
    "validated_by": "Paul Mbarga", "validated_at": "2026-10-28T09:30:00", "item_count": 14,
    "amounts": {"XB": "1000000", "XI": "52000", "BZ": "800000", "CP": "300000"},
    "prior_year_amounts": {"XB": "900000", "XI": "80000", "BZ": "760000", "CP": "260000"},
}


def _ratio(code, value, template, threshold=None, status="COMPUTED", reason=None, unit=None):
    return {"code": code, "name": code, "status": status, "value": value, "unit": unit,
            "reason": reason,
            "interpretation": {"template_id": template, "threshold_applied": threshold, "text": ""}}


RATIOS = [
    _ratio("R1", "1.40", "T_COMPARED_TO_THRESHOLD", "1.0"),
    _ratio("R2", "0.55", "T_FACTUAL_NO_REFERENCE", "NO_REFERENCE"),
    _ratio("R3", "0.80", "T_COMPARED_TO_THRESHOLD", "1.0"),
    _ratio("R4", "5.2", "T_FACTUAL_NO_REFERENCE", "NO_REFERENCE", unit="%"),
    _ratio("R5", "17.3", "T_FACTUAL_NO_REFERENCE", "NO_REFERENCE", unit="%"),
]
CHECKS = [{"code": f"CHK00{i}", "label": f"check {i}", "severity": "BLOCKING" if i < 5 else "WARNING",
           "passed": True, "message": ""} for i in range(1, 6)]
COMPARISON = {"current_year": 2024, "previous_year": 2023, "ratios": [
    {"code": "R1", "current_value": "1.40", "previous_value": "1.00", "percent_change": "40"},
    {"code": "R2", "current_value": "0.55", "previous_value": "0.54", "percent_change": "1.8"},
    {"code": "R4", "current_value": "5.2", "previous_value": "8.9", "percent_change": "-41.6"},
]}
RELIABILITY = {"engine": "RULE_BASED", "corrected": 2, "keyed": 1, "acknowledged": []}


def _report(lang="en", **changes):
    args = dict(case=CASE, dataset=DATASET, ratios=RATIOS, checks=CHECKS, comparison=COMPARISON,
                ai=None, labels=lambda code: code, language=lang, reliability=RELIABILITY)
    args.update(changes)
    return build_report(**copy.deepcopy(args))


def _all(lines):
    return " ".join(lines)


def test_a_documented_reference_makes_a_strength_or_a_weakness():
    report = _report()
    strengths, weaknesses = _all(report["strengths"]), _all(report["weaknesses"])
    assert "R1" in strengths and "R3" in weaknesses
    assert "profit" in strengths.lower()  # the sign of net income is a fact
    # No reference, no judgement: R2 and R5 are neither good nor bad.
    assert "R2" not in strengths + weaknesses and "R5" not in strengths + weaknesses
    assert "R2" in _all(report["attention"]) and "R5" in _all(report["attention"])


def test_a_loss_and_negative_equity_are_weaknesses():
    ratios = copy.deepcopy(RATIOS)
    ratios[3]["value"] = "-3.1"
    ratios[4] = _ratio("R5", None, "T_NOT_COMPUTABLE", status="NOT_COMPUTABLE", reason="negative equity")
    weaknesses = _all(_report(ratios=ratios)["weaknesses"]).lower()
    assert "loss" in weaknesses and "negative equity" in weaknesses


def test_trends_against_the_previous_year():
    report = _report()
    assert any("R1" in line and "1.00" in line and "1.40" in line for line in report["strengths"])
    assert any("R4" in line and "8.9" in line and "5.2" in line for line in report["weaknesses"])
    # A small move is not a trend.
    assert not any("R2" in line for line in report["strengths"] + report["weaknesses"])
    # Revenue +11 %: a strength.
    assert any("revenue" in line.lower() and "11" in line for line in report["strengths"])


def test_the_verdict_gives_the_key_figures_and_the_overall_picture():
    verdict = _report()["verdict"]
    assert "SOCATRANS" in verdict and "1,000,000" in verdict and "52,000" in verdict
    assert "mixed" in verdict.lower()
    assert "5 of 5" in verdict


def test_what_can_be_relied_on():
    reliance = _all(_report()["reliance"])
    assert "Paul Mbarga" in reliance
    assert "2" in reliance and "corrected" in reliance and "1" in reliance and "by hand" in reliance


def test_validated_despite_a_failing_check_calls_for_caution():
    checks = copy.deepcopy(CHECKS)
    checks[0].update(passed=False, message="BZ and DZ differ by 235")
    report = _report(checks=checks, reliability={**RELIABILITY, "acknowledged": ["CHK001"]})
    assert "caution" in report["verdict"].lower()
    assert "CHK001" in _all(report["reliance"]) and "BZ and DZ differ by 235" in _all(report["reliance"])


def test_without_a_previous_year_there_is_no_trend():
    dataset = {**DATASET, "prior_year_amounts": {}}
    report = _report(comparison=None, dataset=dataset)
    assert any("previous year" in line for line in report["attention"])


def test_the_ai_commentary_only_once_approved():
    draft = {"status": "DRAFT", "sections": {"overview": "Draft text."}}
    report = _report(ai=draft)
    assert report["ai"] is None
    assert "not been approved" in _all(report["reliance"])

    approved = {"status": "APPROVED", "approved_by": "Helena Ndongo", "approved_at": "2026-10-28T10:00:00",
                "model": "claude-opus-5-5", "sections": {"overview": "Approved text.",
                                                          "recommendations": ["Collect receivables."]}}
    ai = _report(ai=approved)["ai"]
    assert ai["note"].startswith("Written with AI assistance")
    assert ("Overview", "Approved text.") in ai["paragraphs"]
    assert ai["lists"][0] == ("Recommendations", ["Collect receivables."])


def test_the_whole_report_in_french():
    report = _report("fr")
    assert report["headings"]["strengths"] == "Points forts"
    assert "liquidité" in _all(report["strengths"]).lower()
    assert "1 000 000" in report["verdict"] and "contrasté" in report["verdict"]
    assert report["ratios"][0]["name"] == "Ratio de liquidité générale"
    assert report["ratios"][0]["meaning"]