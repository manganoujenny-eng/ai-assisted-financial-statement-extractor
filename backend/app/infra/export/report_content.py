"""What the exported reports say — one reading, shared by the PDF and Excel.

``build_report()`` turns the validated results (ratios, checks, year
comparison, the approved AI commentary) into the content of a report, in
the screen's language. ``pdf_report.py`` and ``spreadsheet.py`` only lay it
out, so the two files always say the same thing.

The summary at the top is written by fixed rules, never by a model, and
says only what the figures support:

* **Verdict** — the key figures, the overall picture (how many strengths,
  how many weaknesses) and how far the figures can be trusted.
* **Strengths / weaknesses** — a ratio is called good or bad only against
  a documented reference (R1 and R3: 1.0) or by its sign (a profit, a
  loss, negative equity). R2, R4 and R5 have no documented reference, so
  their level is never judged (BR-14): they go to the points of attention.
  A ratio that moved 10 % or more since the previous year is a trend (all
  five read "higher is better"); so is revenue moving 5 % or more.
* **What the figures can be relied on for** — who validated them, the
  checks, how many items the analyst corrected or keyed by hand, which
  engine read the statement, and whether the AI commentary is approved.
* **Points of attention** — ratios not computable, ratios without a
  reference, failed warnings, no previous year.

The AI commentary is included only once an analyst approved it (BR-13),
marked as written with AI assistance.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation

#: A ratio that moved at least this much (in %) since the previous year.
TREND_PERCENT = Decimal("10")
#: Revenue that moved at least this much (in %).
REVENUE_PERCENT = Decimal("5")

TEXTS = {
    "en": {
        # --- headings ---
        "brand": "EB-PARTNERS AUDIT — SYSCOHADA financial analysis",
        "title": "Financial analysis report",
        "summary": "Summary", "keyFigures": "Key figures",
        "strengths": "Strengths", "weaknesses": "Weaknesses",
        "reliance": "What the figures can be relied on for",
        "attention": "Points of attention",
        "ratiosDetail": "Ratios in detail", "checks": "Consistency checks",
        "amounts": "Validated amounts (FCFA)", "ai": "AI commentary",
        "method": "How this report is built",
        "none": "None.",
        # --- the case ---
        "client": "Client", "year": "Fiscal year", "analyst": "Analyst",
        "validatedBy": "Validated by", "validatedOn": "Validated on", "status": "Status",
        "generatedOn": "Generated on",
        # --- tables ---
        "ratio": "Ratio", "value": "Value", "reading": "Reading", "meaning": "What it measures",
        "interpretation": "Interpretation", "previous": "Previous year", "change": "Change",
        "check": "Check", "severity": "Severity", "result": "Result", "detail": "Detail",
        "code": "Code", "item": "Item", "yearN": "Year {year}",
        "passed": "passed", "failed": "failed", "BLOCKING": "blocking", "WARNING": "warning",
        "good": "favourable", "bad": "unfavourable", "neutral": "no reference", "na": "not computable",
        "noComparison": "No previous year available.",
        # --- key figures ---
        "kf.XB": "Revenue", "kf.XI": "Net income", "kf.BZ": "Total balance sheet", "kf.CP": "Equity",
        # --- the verdict ---
        "v.open": "The {year} accounts of {client}, validated by {validator}, show revenue of {revenue} FCFA and a net {result} of {income} FCFA.",
        "v.openNoRevenue": "The {year} accounts of {client} were validated by {validator}.",
        "v.profit": "profit", "v.loss": "loss",
        "v.allGood": "Overall, none of the measured indicators shows a weakness.",
        "v.allBad": "Overall, the measured indicators point to weaknesses that call for attention.",
        "v.mixed": "Overall, the picture is mixed: {strengths} strength(s) and {weaknesses} weakness(es).",
        "v.nothing": "The measured indicators allow no overall judgement.",
        "v.checks": "The figures passed {passed} of {total} consistency checks.",
        "v.caution": "They were validated despite failing check(s) {codes}: read the results with caution.",
        # --- strengths and weaknesses ---
        "s.R1": "Liquidity: current assets and cash cover the short-term debts (R1 = {value}, reference {threshold}).",
        "w.R1": "Liquidity: current assets and cash do not cover the short-term debts (R1 = {value}, below the {threshold} reference).",
        "s.R3": "Funding: fixed assets are financed by stable resources (R3 = {value}, reference {threshold}).",
        "w.R3": "Funding: part of the fixed assets is financed by short-term resources (R3 = {value}, below the {threshold} reference).",
        "s.profit": "The company made a profit: net margin of {value} % (R4).",
        "w.loss": "The company made a loss: net margin of {value} % (R4).",
        "w.negativeEquity": "Negative equity: accumulated losses exceed the capital (R5 not computable).",
        "s.trend": "{name} ({code}) improved from {previous} to {current} ({change} %).",
        "w.trend": "{name} ({code}) fell from {previous} to {current} ({change} %).",
        "s.revenue": "Revenue grew by {change} % ({previous} → {current} FCFA).",
        "w.revenue": "Revenue fell by {change} % ({previous} → {current} FCFA).",
        # --- reliance ---
        "r.validated": "Every figure was read from the statement, checked by the analyst against the source document and validated by {validator} on {when}.",
        "r.allChecks": "All {total} consistency checks passed: the balance sheet balances, subtotals and net income agree, and no required item is missing.",
        "r.failedCheck": "{code} {label} failed: {message}",
        "r.acknowledged": "{code} {label} failed and the supervisor validated anyway: {message}",
        "r.corrections": "{corrected} figure(s) corrected by the analyst and {keyed} entered by hand; the extractor's original proposals are kept.",
        "r.noCorrection": "No figure needed correcting after extraction.",
        "r.engine": "Statement read by: {engine}.",
        "engine.RULE_BASED": "the rule-based extractor", "engine.LLM": "Claude (text)",
        "engine.LLM_VISION": "Claude (page images)",
        "r.aiApproved": "The AI commentary below was read and approved by {name}.",
        "r.aiDraft": "An AI commentary exists but has not been approved: it is not part of this report.",
        # --- attention ---
        "a.notComputable": "{name} ({code}) could not be computed: {reason}.",
        "a.noReference": "{list}: no documented reference exists, so their level is not judged here. Compare them with companies of the same sector before drawing a conclusion.",
        "a.warning": "Warning {code} {label}: {message}",
        "a.noPrevious": "No previous year is available: trends cannot be assessed.",
        "a.general": "Ratios summarise the statements; they do not replace reading the notes to the accounts or knowing the company's sector.",
        # --- method ---
        "m.text": "Ratios are computed by fixed rules from validated figures only, never from unchecked data. A ratio is called favourable or unfavourable only against a documented reference. The AI commentary, when present, was written with AI assistance and approved by an analyst.",
        "aiNote": "Written with AI assistance ({model}), read and approved by {name} on {when}.",
        "ai.overview": "Overview", "ai.diagnosis": "Diagnosis", "ai.checks": "Reliability of the figures",
        "ai.comparison": "Compared with the previous year", "ai.recommendations": "Recommendations",
        "ai.attention": "Points of attention",
        "footer": "Page {page} / {pages} · generated on {when}",
        # --- rule-based interpretation sentences (as on the dashboard) ---
        "notComputable": "{name} could not be computed: {reason}. No value is shown rather than a value that would be wrong.",
        "noReference": "{name} stands at {value}. No documented reference is available for this ratio, so no judgement is expressed.",
        "above": "{name} stands at {value}, at or above the {threshold} reference.",
        "below": "{name} stands at {value}, below the {threshold} reference.",
        "aboveCoverage": "{name} stands at {value}, at or above the {threshold} coverage reference.",
        "belowCoverage": "{name} stands at {value}, below the {threshold} coverage reference.",
        "reason.missing": "missing item(s): {items}", "reason.zero": "zero denominator",
        "reason.undefined": "undefined arithmetic operation", "reason.negative": "negative equity",
        # --- names ---
        "R1": "Current ratio", "R2": "Equity ratio", "R3": "Stable funding coverage",
        "R4": "Net margin", "R5": "Return on equity",
        "meaning.R1": "Can current assets and cash pay the debts due within a year?",
        "meaning.R2": "The share of long-term financing that comes from the owners rather than lenders.",
        "meaning.R3": "Are fixed assets financed by long-term resources (equity and financial debt)?",
        "meaning.R4": "The profit kept from every 100 of revenue.",
        "meaning.R5": "The return earned on the owners' capital.",
        "CHK001": "Balance sheet equilibrium", "CHK002": "Subtotal consistency",
        "CHK003": "Net income consistency", "CHK004": "Completeness",
        "CHK005": "Plausible signs on assets and revenue",
        # --- sheet names (Excel: at most 31 characters) ---
        "sheet.summary": "Summary", "sheet.ratios": "Ratios", "sheet.checks": "Checks",
        "sheet.amounts": "Validated data", "sheet.ai": "AI commentary",
    },
    "fr": {
        "brand": "EB-PARTNERS AUDIT — analyse financière SYSCOHADA",
        "title": "Rapport d'analyse financière",
        "summary": "Synthèse", "keyFigures": "Chiffres clés",
        "strengths": "Points forts", "weaknesses": "Points faibles",
        "reliance": "Ce sur quoi les chiffres permettent de s'appuyer",
        "attention": "Points d'attention",
        "ratiosDetail": "Les ratios en détail", "checks": "Contrôles de cohérence",
        "amounts": "Montants validés (FCFA)", "ai": "Commentaire IA",
        "method": "Comment ce rapport est construit",
        "none": "Aucun.",
        "client": "Client", "year": "Exercice", "analyst": "Analyste",
        "validatedBy": "Validé par", "validatedOn": "Validé le", "status": "État",
        "generatedOn": "Généré le",
        "ratio": "Ratio", "value": "Valeur", "reading": "Lecture", "meaning": "Ce qu'il mesure",
        "interpretation": "Interprétation", "previous": "Exercice précédent", "change": "Évolution",
        "check": "Contrôle", "severity": "Gravité", "result": "Résultat", "detail": "Détail",
        "code": "Code", "item": "Poste", "yearN": "Exercice {year}",
        "passed": "réussi", "failed": "échoué", "BLOCKING": "bloquant", "WARNING": "avertissement",
        "good": "favorable", "bad": "défavorable", "neutral": "sans référence", "na": "non calculable",
        "noComparison": "Aucun exercice précédent disponible.",
        "kf.XB": "Chiffre d'affaires", "kf.XI": "Résultat net", "kf.BZ": "Total du bilan",
        "kf.CP": "Capitaux propres",
        "v.open": "Les comptes {year} de {client}, validés par {validator}, font apparaître un chiffre d'affaires de {revenue} FCFA et un {result} net de {income} FCFA.",
        "v.openNoRevenue": "Les comptes {year} de {client} ont été validés par {validator}.",
        "v.profit": "bénéfice", "v.loss": "déficit",
        "v.allGood": "Dans l'ensemble, aucun des indicateurs mesurés ne présente de faiblesse.",
        "v.allBad": "Dans l'ensemble, les indicateurs mesurés révèlent des faiblesses qui demandent de l'attention.",
        "v.mixed": "Dans l'ensemble, le tableau est contrasté : {strengths} point(s) fort(s) et {weaknesses} point(s) faible(s).",
        "v.nothing": "Les indicateurs mesurés ne permettent pas de jugement d'ensemble.",
        "v.checks": "Les chiffres ont réussi {passed} des {total} contrôles de cohérence.",
        "v.caution": "Ils ont été validés malgré l'échec du ou des contrôles {codes} : lisez les résultats avec prudence.",
        "s.R1": "Liquidité : l'actif circulant et la trésorerie couvrent les dettes à court terme (R1 = {value}, référence {threshold}).",
        "w.R1": "Liquidité : l'actif circulant et la trésorerie ne couvrent pas les dettes à court terme (R1 = {value}, sous la référence de {threshold}).",
        "s.R3": "Financement : les immobilisations sont financées par des ressources stables (R3 = {value}, référence {threshold}).",
        "w.R3": "Financement : une partie des immobilisations est financée par des ressources à court terme (R3 = {value}, sous la référence de {threshold}).",
        "s.profit": "L'entreprise est bénéficiaire : marge nette de {value} % (R4).",
        "w.loss": "L'entreprise est déficitaire : marge nette de {value} % (R4).",
        "w.negativeEquity": "Capitaux propres négatifs : les pertes cumulées dépassent le capital (R5 non calculable).",
        "s.trend": "{name} ({code}) s'est amélioré, de {previous} à {current} ({change} %).",
        "w.trend": "{name} ({code}) s'est dégradé, de {previous} à {current} ({change} %).",
        "s.revenue": "Le chiffre d'affaires a progressé de {change} % ({previous} → {current} FCFA).",
        "w.revenue": "Le chiffre d'affaires a reculé de {change} % ({previous} → {current} FCFA).",
        "r.validated": "Chaque chiffre a été lu dans l'état financier, vérifié par l'analyste face au document source et validé par {validator} le {when}.",
        "r.allChecks": "Les {total} contrôles de cohérence sont réussis : le bilan est équilibré, les sous-totaux et le résultat net concordent, et aucun poste requis ne manque.",
        "r.failedCheck": "{code} {label} a échoué : {message}",
        "r.acknowledged": "{code} {label} a échoué et le superviseur a validé malgré tout : {message}",
        "r.corrections": "{corrected} chiffre(s) corrigé(s) par l'analyste et {keyed} saisi(s) à la main ; les propositions d'origine de l'extracteur sont conservées.",
        "r.noCorrection": "Aucun chiffre n'a dû être corrigé après l'extraction.",
        "r.engine": "État financier lu par : {engine}.",
        "engine.RULE_BASED": "l'extracteur à règles", "engine.LLM": "Claude (texte)",
        "engine.LLM_VISION": "Claude (images des pages)",
        "r.aiApproved": "Le commentaire IA ci-dessous a été relu et approuvé par {name}.",
        "r.aiDraft": "Un commentaire IA existe mais n'a pas été approuvé : il ne fait pas partie de ce rapport.",
        "a.notComputable": "{name} ({code}) n'a pas pu être calculé : {reason}.",
        "a.noReference": "{list} : aucune référence documentée n'existe, leur niveau n'est donc pas jugé ici. Comparez-les à des entreprises du même secteur avant de conclure.",
        "a.warning": "Avertissement {code} {label} : {message}",
        "a.noPrevious": "Aucun exercice précédent n'est disponible : les tendances ne peuvent pas être appréciées.",
        "a.general": "Les ratios résument les états financiers ; ils ne remplacent ni la lecture des notes annexes ni la connaissance du secteur de l'entreprise.",
        "m.text": "Les ratios sont calculés par des règles fixes à partir des seuls chiffres validés, jamais de données non vérifiées. Un ratio n'est dit favorable ou défavorable que face à une référence documentée. Le commentaire IA, quand il figure, a été rédigé avec l'aide de l'IA et approuvé par un analyste.",
        "aiNote": "Rédigé avec l'aide de l'IA ({model}), relu et approuvé par {name} le {when}.",
        "ai.overview": "Vue d'ensemble", "ai.diagnosis": "Diagnostic", "ai.checks": "Fiabilité des chiffres",
        "ai.comparison": "Comparaison avec l'exercice précédent", "ai.recommendations": "Recommandations",
        "ai.attention": "Points d'attention",
        "footer": "Page {page} / {pages} · généré le {when}",
        "notComputable": "{name} n'a pas pu être calculé : {reason}. Aucune valeur n'est affichée plutôt qu'une valeur qui serait fausse.",
        "noReference": "{name} s'établit à {value}. Aucune référence documentée n'existe pour ce ratio, donc aucun jugement n'est porté.",
        "above": "{name} s'établit à {value}, au niveau ou au-dessus de la référence de {threshold}.",
        "below": "{name} s'établit à {value}, en dessous de la référence de {threshold}.",
        "aboveCoverage": "{name} s'établit à {value}, au niveau ou au-dessus de la référence de couverture de {threshold}.",
        "belowCoverage": "{name} s'établit à {value}, en dessous de la référence de couverture de {threshold}.",
        "reason.missing": "poste(s) manquant(s) : {items}", "reason.zero": "dénominateur nul",
        "reason.undefined": "opération arithmétique indéfinie", "reason.negative": "capitaux propres négatifs",
        "R1": "Ratio de liquidité générale", "R2": "Ratio d'autonomie financière",
        "R3": "Couverture par les ressources stables", "R4": "Marge nette",
        "R5": "Rentabilité des capitaux propres",
        "meaning.R1": "L'actif circulant et la trésorerie peuvent-ils payer les dettes à moins d'un an ?",
        "meaning.R2": "La part du financement à long terme apportée par les propriétaires plutôt que par les prêteurs.",
        "meaning.R3": "Les immobilisations sont-elles financées par des ressources longues (capitaux propres et dettes financières) ?",
        "meaning.R4": "Le bénéfice conservé sur chaque 100 de chiffre d'affaires.",
        "meaning.R5": "Le rendement obtenu sur les capitaux des propriétaires.",
        "CHK001": "Équilibre du bilan", "CHK002": "Cohérence des sous-totaux",
        "CHK003": "Cohérence du résultat net", "CHK004": "Exhaustivité",
        "CHK005": "Signes plausibles sur l'actif et le chiffre d'affaires",
        "sheet.summary": "Synthèse", "sheet.ratios": "Ratios", "sheet.checks": "Contrôles",
        "sheet.amounts": "Données validées", "sheet.ai": "Commentaire IA",
    },
}

KEY_FIGURES = ("XB", "XI", "BZ", "CP")


# --- formatting ---------------------------------------------------------------
def decimal(value) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def number(value, lang: str, decimals: int | None = None) -> str:
    """1,234,567.89 in English, 1 234 567,89 in French. Without
    ``decimals``, keeps the decimals the value was given with."""
    figure = decimal(value)
    if figure is None:
        return "—" if value in (None, "") else str(value)
    if decimals is None:
        exponent = figure.as_tuple().exponent
        decimals = max(0, -exponent) if isinstance(exponent, int) else 0
    text = f"{figure:,.{decimals}f}"
    if lang == "fr":
        text = text.replace(",", " ").replace(".", ",")
    return text


def when(value, lang: str) -> str:
    if not value:
        return "—"
    moment = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    return moment.strftime("%d/%m/%Y %H:%M" if lang == "fr" else "%Y-%m-%d %H:%M")


def _signed(value: Decimal, lang: str) -> str:
    text = number(value.quantize(Decimal("0.1")), lang, 1)
    return text if value < 0 else f"+{text}"


# --- the rule-based interpretation sentence (as the dashboard shows it) --------
def interpretation_text(t: dict, ratio: dict, lang: str) -> str:
    interpretation = ratio.get("interpretation") or {}
    name = t.get(ratio["code"], ratio.get("name") or ratio["code"])
    value = f"{number(ratio.get('value'), lang)} {ratio.get('unit') or ''}".strip()
    template = interpretation.get("template_id")
    if template == "T_NOT_COMPUTABLE" or ratio.get("status") != "COMPUTED":
        return t["notComputable"].format(name=name, reason=reason_text(t, ratio.get("reason")))
    if template == "T_FACTUAL_NO_REFERENCE":
        return t["noReference"].format(name=name, value=value)
    if template == "T_COMPARED_TO_THRESHOLD":
        threshold = interpretation.get("threshold_applied")
        above = decimal(ratio.get("value")) >= decimal(threshold)
        key = ("above" if above else "below") + ("Coverage" if ratio["code"] == "R3" else "")
        return t[key].format(name=name, value=value, threshold=number(threshold, lang))
    return interpretation.get("text") or ""


def reason_text(t: dict, reason: str | None) -> str:
    reason = reason or ""
    if reason.lower().startswith("missing item(s):"):
        return t["reason.missing"].format(items=reason.split(":", 1)[1].strip())
    return {"zero denominator": t["reason.zero"],
            "undefined arithmetic operation": t["reason.undefined"],
            "negative equity": t["reason.negative"]}.get(reason.strip().lower(), reason)


def _reading(ratio: dict) -> str:
    """good / bad / neutral / na — what the summary may say of its level."""
    if ratio.get("status") != "COMPUTED":
        return "na"
    interpretation = ratio.get("interpretation") or {}
    if interpretation.get("template_id") == "T_COMPARED_TO_THRESHOLD":
        threshold = decimal(interpretation.get("threshold_applied"))
        return "good" if decimal(ratio.get("value")) >= threshold else "bad"
    return "neutral"


# --- the report -----------------------------------------------------------------
def build_report(case: dict, dataset: dict, ratios: list[dict], checks: list[dict],
                 comparison: dict | None = None, ai: dict | None = None,
                 labels=lambda code: code, language: str = "en",
                 reliability: dict | None = None, generated_at: datetime | None = None) -> dict:
    lang = language if language in TEXTS else "en"
    t = TEXTS[lang]
    reliability = reliability or {}
    amounts = dataset.get("amounts") or {}
    prior = dataset.get("prior_year_amounts") or {}
    year = int(case["fiscal_year"])
    by_code = {r["code"]: r for r in ratios}
    name = lambda code: t.get(code, by_code.get(code, {}).get("name") or code)  # noqa: E731

    strengths: list[str] = []
    weaknesses: list[str] = []
    attention: list[str] = []

    # Levels, against a documented reference only.
    for code in ("R1", "R3"):
        ratio = by_code.get(code)
        reading = _reading(ratio) if ratio else "na"
        if reading in ("good", "bad"):
            threshold = number((ratio.get("interpretation") or {}).get("threshold_applied"), lang)
            line = t[("s." if reading == "good" else "w.") + code].format(
                value=number(ratio["value"], lang), threshold=threshold)
            (strengths if reading == "good" else weaknesses).append(line)

    # Profit or loss: a sign is a fact, not a judgement.
    r4 = by_code.get("R4")
    if r4 and r4.get("status") == "COMPUTED" and decimal(r4["value"]) is not None:
        margin = decimal(r4["value"])
        if margin > 0:
            strengths.append(t["s.profit"].format(value=number(r4["value"], lang)))
        elif margin < 0:
            weaknesses.append(t["w.loss"].format(value=number(r4["value"], lang)))
    r5 = by_code.get("R5")
    if r5 and r5.get("status") != "COMPUTED" and "negative equity" in (r5.get("reason") or "").lower():
        weaknesses.append(t["w.negativeEquity"])

    # Trends: every ratio reads "higher is better".
    for row in (comparison or {}).get("ratios") or []:
        change = decimal(row.get("percent_change"))
        if change is None or abs(change) < TREND_PERCENT:
            continue
        line = t["s.trend" if change > 0 else "w.trend"].format(
            name=name(row["code"]), code=row["code"],
            previous=number(row.get("previous_value"), lang),
            current=number(row.get("current_value"), lang), change=_signed(change, lang))
        (strengths if change > 0 else weaknesses).append(line)

    revenue, revenue_before = decimal(amounts.get("XB")), decimal(prior.get("XB"))
    if revenue is not None and revenue_before:
        change = (revenue - revenue_before) / abs(revenue_before) * 100
        if abs(change) >= REVENUE_PERCENT:
            line = t["s.revenue" if change > 0 else "w.revenue"].format(
                change=number(abs(change).quantize(Decimal("0.1")), lang, 1),
                previous=number(revenue_before, lang, 0), current=number(revenue, lang, 0))
            (strengths if change > 0 else weaknesses).append(line)

    # Points of attention.
    for ratio in ratios:
        if ratio.get("status") != "COMPUTED" and not (
            ratio["code"] == "R5" and "negative equity" in (ratio.get("reason") or "").lower()
        ):
            attention.append(t["a.notComputable"].format(
                name=name(ratio["code"]), code=ratio["code"], reason=reason_text(t, ratio.get("reason"))))
    unreferenced = [f"{name(r['code'])} ({r['code']})" for r in ratios if _reading(r) == "neutral"]
    if unreferenced:
        attention.append(t["a.noReference"].format(list=", ".join(unreferenced)))
    for check in checks:
        if not check.get("passed") and check.get("severity") == "WARNING":
            attention.append(t["a.warning"].format(
                code=check["code"], label=t.get(check["code"], check.get("label")),
                message=check.get("message") or ""))
    if not comparison or not comparison.get("ratios"):
        attention.append(t["a.noPrevious"])
    attention.append(t["a.general"])

    # What the figures can be relied on for.
    validator = dataset.get("validated_by") or "—"
    reliance = [t["r.validated"].format(validator=validator,
                                        when=when(dataset.get("validated_at"), lang))]
    acknowledged = set(reliability.get("acknowledged") or [])
    blocking_failed = [c for c in checks if not c.get("passed") and c.get("severity") == "BLOCKING"]
    if not blocking_failed and all(c.get("passed") for c in checks):
        reliance.append(t["r.allChecks"].format(total=len(checks)))
    for check in blocking_failed:
        key = "r.acknowledged" if check["code"] in acknowledged else "r.failedCheck"
        reliance.append(t[key].format(code=check["code"], label=t.get(check["code"], check.get("label")),
                                      message=check.get("message") or ""))
    corrected, keyed = int(reliability.get("corrected") or 0), int(reliability.get("keyed") or 0)
    reliance.append(t["r.corrections"].format(corrected=corrected, keyed=keyed)
                    if corrected or keyed else t["r.noCorrection"])
    if reliability.get("engine"):
        engine = reliability["engine"]
        reliance.append(t["r.engine"].format(engine=t.get(f"engine.{engine}", engine)))
    approved = bool(ai and ai.get("status") == "APPROVED" and ai.get("sections"))
    if approved:
        reliance.append(t["r.aiApproved"].format(name=ai.get("approved_by") or "—"))
    elif ai and ai.get("status") == "DRAFT":
        reliance.append(t["r.aiDraft"])

    # The verdict.
    income = decimal(amounts.get("XI"))
    if revenue is not None and income is not None:
        verdict = [t["v.open"].format(
            year=year, client=case.get("client"), validator=validator,
            revenue=number(revenue, lang, 0),
            result=t["v.profit"] if income >= 0 else t["v.loss"],
            income=number(abs(income), lang, 0))]
    else:
        verdict = [t["v.openNoRevenue"].format(year=year, client=case.get("client"),
                                               validator=validator)]
    if strengths and not weaknesses:
        verdict.append(t["v.allGood"])
    elif weaknesses and not strengths:
        verdict.append(t["v.allBad"])
    elif strengths and weaknesses:
        verdict.append(t["v.mixed"].format(strengths=len(strengths), weaknesses=len(weaknesses)))
    else:
        verdict.append(t["v.nothing"])
    verdict.append(t["v.checks"].format(passed=sum(1 for c in checks if c.get("passed")),
                                        total=len(checks)))
    failed_acknowledged = [c["code"] for c in blocking_failed if c["code"] in acknowledged]
    if blocking_failed:
        verdict.append(t["v.caution"].format(
            codes=", ".join(failed_acknowledged or [c["code"] for c in blocking_failed])))

    # The detail.
    previous_by_code = {r["code"]: r for r in (comparison or {}).get("ratios") or []}
    ratio_rows = []
    for ratio in ratios:
        previous = previous_by_code.get(ratio["code"], {})
        change = decimal(previous.get("percent_change"))
        ratio_rows.append({
            "code": ratio["code"],
            "name": name(ratio["code"]),
            "value": (f"{number(ratio.get('value'), lang)} {ratio.get('unit') or ''}".strip()
                      if ratio.get("status") == "COMPUTED" else "—"),
            "number": decimal(ratio.get("value")) if ratio.get("status") == "COMPUTED" else None,
            "unit": ratio.get("unit") or "",
            "reading": _reading(ratio),
            "reading_text": t[_reading(ratio)],
            "meaning": t.get(f"meaning.{ratio['code']}", ""),
            "interpretation": interpretation_text(t, ratio, lang),
            "previous": number(previous.get("previous_value"), lang) if previous else "—",
            "change": f"{_signed(change, lang)} %" if change is not None else "—",
        })
    check_rows = [{
        "code": c["code"], "label": t.get(c["code"], c.get("label")),
        "severity": t.get(c.get("severity"), c.get("severity")),
        "passed": bool(c.get("passed")),
        "result": t["passed"] if c.get("passed") else t["failed"],
        "message": "" if c.get("passed") else (c.get("message") or ""),
    } for c in checks]
    amount_rows = [{
        "code": code, "label": labels(code),
        "current": decimal(amounts.get(code)), "previous": decimal(prior.get(code)),
    } for code in sorted(set(amounts) | set(prior))]
    key_figures = [{
        "code": code, "label": t[f"kf.{code}"],
        "current": number(amounts.get(code), lang, 0) if code in amounts else "—",
        "previous": number(prior.get(code), lang, 0) if code in prior else None,
    } for code in KEY_FIGURES if code in amounts]

    ai_block = None
    if approved:
        sections = ai["sections"]
        paragraphs = [(t[f"ai.{key}"], sections[key])
                      for key in ("overview", "diagnosis") if sections.get(key)]
        ratio_notes = sections.get("ratios") or {}
        if isinstance(ratio_notes, list):  # older drafts: a list of {code, commentary}
            ratio_notes = {r.get("code"): r.get("commentary") for r in ratio_notes}
        paragraphs += [(f"{code} — {name(code)}", text) for code, text in ratio_notes.items() if text]
        paragraphs += [(t[f"ai.{key}"], sections[key])
                       for key in ("checks", "comparison") if sections.get(key)]
        lists = [(t[f"ai.{key}"], list(sections[key]))
                 for key in ("recommendations", "attention") if sections.get(key)]
        ai_block = {
            "note": t["aiNote"].format(model=ai.get("model") or "—",
                                       name=ai.get("approved_by") or "—",
                                       when=when(ai.get("approved_at"), lang)),
            "paragraphs": paragraphs,
            "lists": lists,
        }

    return {
        "lang": lang,
        "t": t,
        "headings": {key: t[key] for key in (
            "summary", "keyFigures", "strengths", "weaknesses", "reliance", "attention",
            "ratiosDetail", "checks", "amounts", "ai", "method")},
        "title": t["title"],
        "subtitle": f"{case.get('client')} · {t['year']} {year}",
        "facts": [
            (t["client"], str(case.get("client") or "—")),
            (t["year"], str(year)),
            (t["analyst"], case.get("analyst") or "—"),
            (t["validatedBy"], validator),
            (t["validatedOn"], when(dataset.get("validated_at"), lang)),
            (t["generatedOn"], when(generated_at or datetime.now(), lang)),
        ],
        "year": year,
        "previous_year": (comparison or {}).get("previous_year") or (year - 1 if prior else None),
        "key_figures": key_figures,
        "verdict": " ".join(verdict),
        "strengths": strengths,
        "weaknesses": weaknesses,
        "reliance": reliance,
        "attention": attention,
        "ratios": ratio_rows,
        "checks": check_rows,
        "amounts": amount_rows,
        "has_prior": bool(prior),
        "ai": ai_block,
        "method": t["m.text"],
    }