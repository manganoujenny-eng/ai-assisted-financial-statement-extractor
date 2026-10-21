"""The week 7 campaign: every corpus package, extracted and measured (§18.1).

The four measurements of ``EvaluationService`` compare ONE extraction with
ONE ground truth. This module runs them over the whole corpus:

    data/corpus/
        RP001/
            ETAT_FINANCIER_TEST1.pdf      <- the document(s), any name
            annotation_RP001.xlsx         <- your hand reading
        RP002/
            ...

For each package folder:

1. read the hand reading from the annotation workbook (sheet "Annotation",
   the columns "code" and "Value", found by their header — not by position);
2. check the hand reading itself: the reference must pass every blocking
   consistency check, otherwise it is REJECTED and left out of the results
   (a wrong reference makes the extractor look wrong when it is right — the
   RP001 lesson: gross instead of net AZ, a loss read as a profit);
3. extract the document(s) with the same readers and structurer the
   application uses;
4. measure: field accuracy, ratio accuracy, amplification coefficient,
   silent false positives;
5. run the sensitivity matrix (§19.2) on the reference.

Then the corpus summary. Field and ratio accuracy are POOLED (all fields of
all packages together), not averaged per package: a package with 15 items
and one with 14 weigh what they contain. The per-package figures are kept
next to it, so both readings are available for the thesis.

Which items are judged: those the system actually reads — the required
items, plus CJ, BU and DV that the checks use. The other lines you annotated
(BA, BB, BG, XG...) are compared too and reported, but outside the four
measurements, so that every package is judged on the same list of items.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable

from ..domain import entities as E
from ..domain.checks import has_blocking_failure, run_all
from ..domain.ratios import compute_all
from ..domain.statement import FinancialStatement
from ..domain.syscohada import REQUIRED_CODES
from ..domain.value_objects import Amount
from .evaluation_service import EvaluationService, _ratio_agrees, _wrong_values

#: The items the four measurements judge (see the module docstring).
JUDGED_CODES: tuple[str, ...] = tuple(REQUIRED_CODES) + ("CJ", "BU", "DV")

#: The corpus folder: <project>/data/corpus, or CORPUS_DIR in .env.
DEFAULT_CORPUS = Path(__file__).resolve().parents[3] / "data" / "corpus"

#: Files ignored when looking for the documents of a package.
DOCUMENT_SUFFIXES = (".pdf", ".xlsx", ".xls")


class AnnotationError(ValueError):
    """The annotation workbook cannot be read as a ground truth."""


# --- 1. the hand reading ------------------------------------------------
@dataclass
class Annotation:
    path: Path
    year: int | None
    amounts: dict[str, Decimal]  # every annotated line, code -> amount
    problems: list[str] = field(default_factory=list)

    def judged(self) -> FinancialStatement:
        return FinancialStatement.from_dict(
            {c: v for c, v in self.amounts.items() if c in JUDGED_CODES},
            fiscal_year=self.year,
        )


def _number(value) -> Decimal | None:
    """An amount cell: a number, or a text such as "7 969 151 104"."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    text = str(value).replace("\u00a0", "").replace("\u202f", "").replace(" ", "")
    text = text.replace(",", ".") if text.count(",") == 1 and "." not in text else text.replace(",", "")
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def load_annotation(path: str | Path) -> Annotation:
    """Read the sheet "Annotation" of a workbook in the RP001 format."""
    from openpyxl import load_workbook  # noqa: PLC0415 — only the campaign needs it

    path = Path(path)
    workbook = load_workbook(path, data_only=True, read_only=True)
    try:
        sheet = next(
            (ws for ws in workbook.worksheets if ws.title.strip().lower() == "annotation"),
            workbook.worksheets[0],
        )
        rows = list(sheet.iter_rows(values_only=True))
    finally:
        workbook.close()

    # The header row is the one holding both "code" and "Value".
    header_index = code_col = value_col = year_col = None
    for index, row in enumerate(rows):
        names = [str(c).strip().lower() if c is not None else "" for c in row]
        if "code" in names and any(n.startswith("value") for n in names):
            header_index = index
            code_col = names.index("code")
            value_col = next(i for i, n in enumerate(names) if n.startswith("value"))
            year_col = names.index("year") if "year" in names else None
            break
    if header_index is None:
        raise AnnotationError(f'{path.name}: no header row with "code" and "Value"')

    amounts: dict[str, Decimal] = {}
    years: Counter = Counter()
    problems: list[str] = []
    for number, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
        cells = list(row) + [None] * (max(code_col, value_col, year_col or 0) + 1 - len(row))
        raw_code = cells[code_col]
        if raw_code is None or not str(raw_code).strip():
            continue
        code = str(raw_code).strip().upper()
        if len(code) != 2 or not code.isalpha():
            problems.append(f"row {number}: {raw_code!r} is not a SYSCOHADA code")
            continue
        value = _number(cells[value_col])
        if value is None:
            problems.append(f"row {number}: {code} has no readable amount ({cells[value_col]!r})")
            continue
        if code in amounts and amounts[code] != value:
            problems.append(
                f"row {number}: {code} annotated twice with different amounts "
                f"({amounts[code]} and {value}) - the first is kept"
            )
            continue
        amounts[code] = value
        if year_col is not None and cells[year_col] is not None:
            try:
                years[int(cells[year_col])] += 1
            except (TypeError, ValueError):
                pass

    year = years.most_common(1)[0][0] if years else None
    return Annotation(path=path, year=year, amounts=amounts, problems=problems)


# --- 3. the extraction --------------------------------------------------
@dataclass
class Extraction:
    """What the system read for year N, all documents of the package together."""

    amounts: dict[str, Decimal]
    engine: str
    rejected: int = 0  # proposals the schema refused (§11.1)
    failure: str | None = None


Extractor = Callable[[list[Path]], Extraction]


def application_extractor(structurer=None, readers=None) -> Extractor:
    """The readers and structurer the application uses (rule-based by default)."""
    from ..infra.llm.rule_based import RuleBasedStructurer  # noqa: PLC0415
    from ..infra.pdf.readers import default_readers  # noqa: PLC0415

    structurer = structurer or RuleBasedStructurer()
    readers = readers or default_readers()

    def extract(documents: list[Path]) -> Extraction:
        amounts: dict[str, Decimal] = {}
        found_in: dict[str, str] = {}
        rejected = 0
        for document in documents:
            reader = next((r for r in readers if r.supports(str(document))), None)
            if reader is None:
                return Extraction({}, structurer.engine, failure=f"no reader for {document.name}")
            structured = structurer.structure(reader.read(str(document)))
            for item in structured.items:
                if item.year != "N":
                    continue
                code = str(item.item_code).strip().upper()
                try:
                    amount = Amount(item.amount).value
                except (ValueError, TypeError):
                    rejected += 1
                    continue
                if len(code) != 2 or not code.isalpha():
                    rejected += 1
                    continue
                if code in found_in and found_in[code] != document.name:
                    # The application refuses this run (ExtractionService):
                    # the campaign records the same failure.
                    return Extraction(
                        {}, structurer.engine,
                        failure=f"{code} found in both {found_in[code]} and {document.name}",
                    )
                found_in[code] = document.name
                amounts[code] = amount
        if not amounts:
            return Extraction({}, structurer.engine, rejected, "no usable item found")
        return Extraction(amounts, structurer.engine, rejected)

    return extract


# --- 4. one package -----------------------------------------------------
@dataclass
class PackageResult:
    package: str
    documents: list[str]
    annotation: str
    status: str  # EVALUATED | REFERENCE_REJECTED | EXTRACTION_FAILED | UNREADABLE
    reason: str | None = None
    annotation_problems: list[str] = field(default_factory=list)
    judged_fields: int = 0
    wrong_fields: list[dict] = field(default_factory=list)
    ratios: int = 0
    wrong_ratios: list[dict] = field(default_factory=list)
    field_accuracy: Decimal | None = None
    ratio_accuracy: Decimal | None = None
    amplification: Decimal | None = None
    silent_false_positives: list[str] = field(default_factory=list)
    checks_failed_on_extraction: list[str] = field(default_factory=list)
    other_lines: dict = field(default_factory=dict)
    criticality: dict[str, Decimal] = field(default_factory=dict)
    interception_rate: Decimal | None = None
    interception_cells: tuple[int, int] = (0, 0)  # (intercepted, measurable)


def _ratio_row(result) -> dict:
    return {
        "status": result.status,
        "value": str(result.measured) if result.measured is not None else None,
        "reason": result.reason,
    }


def evaluate_package(
    folder: Path, extract: Extractor, evaluation: EvaluationService | None = None
) -> PackageResult:
    evaluation = evaluation or EvaluationService()
    annotations = sorted(p for p in folder.iterdir() if p.suffix.lower() in (".xlsx", ".xls")
                         and "annotation" in p.name.lower() and not p.name.startswith("~$"))
    documents = sorted(p for p in folder.iterdir() if p.suffix.lower() in DOCUMENT_SUFFIXES
                       and p not in annotations and not p.name.startswith("~$"))
    result = PackageResult(
        package=folder.name,
        documents=[d.name for d in documents],
        annotation=annotations[0].name if annotations else "",
        status="UNREADABLE",
    )
    if len(annotations) != 1:
        result.reason = (f"{len(annotations)} annotation workbooks - put exactly one file "
                         'whose name contains "annotation" in the folder')
        return result
    if not documents:
        result.reason = "no document (PDF or Excel) next to the annotation"
        return result

    # 1-2. the hand reading, and its own consistency.
    try:
        annotation = load_annotation(annotations[0])
    except AnnotationError as exc:
        result.reason = str(exc)
        return result
    result.annotation_problems = annotation.problems
    truth = annotation.judged()
    outcomes = run_all(truth)
    if has_blocking_failure(outcomes):
        result.status = "REFERENCE_REJECTED"
        result.reason = "the hand reading fails: " + "; ".join(
            f"{o.code} {o.message}" for o in outcomes if o.is_blocking_failure
        )
        return result

    # 3. the extraction.
    extraction = extract(documents)
    if extraction.failure:
        result.status = "EXTRACTION_FAILED"
        result.reason = extraction.failure
        return result
    extracted_all = FinancialStatement.from_dict(extraction.amounts, fiscal_year=annotation.year)
    extracted = FinancialStatement.from_dict(
        {c: v for c, v in extraction.amounts.items() if c in JUDGED_CODES},
        fiscal_year=annotation.year,
    )

    # 4. the four measurements.
    result.status = "EVALUATED"
    result.judged_fields = len(truth)
    wrong = set(_wrong_values(extracted, truth)) | set(extracted.missing(truth.codes()))
    result.wrong_fields = [
        {
            "code": code,
            "truth": str(truth[code].value),
            "extracted": str(extracted[code].value) if extracted.get(code) is not None else None,
        }
        for code in sorted(wrong)
    ]
    mine = {r.code: r for r in compute_all(extracted)}
    reference = compute_all(truth)
    result.ratios = len(reference)
    result.wrong_ratios = [
        {"code": t.code, "truth": _ratio_row(t), "extracted": _ratio_row(mine[t.code])}
        for t in reference
        if not _ratio_agrees(mine.get(t.code), t)
    ]
    result.field_accuracy = evaluation.field_accuracy(extracted, truth)
    result.ratio_accuracy = evaluation.ratio_accuracy(extracted, truth)
    result.amplification = evaluation.amplification_coefficient(
        result.field_accuracy, result.ratio_accuracy
    )
    result.silent_false_positives = evaluation.silent_false_positives(extracted, truth)
    result.checks_failed_on_extraction = [o.code for o in run_all(extracted) if not o.passed]

    # The other annotated lines: compared, reported, not measured.
    others = {c: v for c, v in annotation.amounts.items() if c not in JUDGED_CODES}
    different = [
        {"code": c, "truth": str(v),
         "extracted": str(extracted_all[c].value) if extracted_all.get(c) is not None else None}
        for c, v in sorted(others.items())
        if extracted_all.get(c) is None or extracted_all[c].value != v
    ]
    result.other_lines = {"annotated": len(others), "identical": len(others) - len(different),
                          "different": different}

    # 5. the sensitivity matrix on the reference.
    matrix = evaluation.sensitivity_matrix(truth)
    result.criticality = {code: matrix.criticality(code) for code in sorted(truth.codes())}
    result.interception_rate = matrix.interception_rate()
    measurable = [c for c in matrix.cells if c.is_measurable]
    result.interception_cells = (sum(1 for c in measurable if c.intercepted_by_checks),
                                 len(measurable))
    return result


# --- the whole corpus ---------------------------------------------------
@dataclass
class CampaignResult:
    corpus: str
    engine: str
    packages: list[PackageResult]
    inputs: dict[str, str]  # file -> sha256, so the campaign can be replayed

    @property
    def evaluated(self) -> list[PackageResult]:
        return [p for p in self.packages if p.status == "EVALUATED"]

    def summary(self) -> dict:
        done = self.evaluated
        fields = sum(p.judged_fields for p in done)
        wrong_fields = sum(len(p.wrong_fields) for p in done)
        ratios = sum(p.ratios for p in done)
        wrong_ratios = sum(len(p.wrong_ratios) for p in done)
        field_acc = Decimal(fields - wrong_fields) / Decimal(fields) if fields else None
        ratio_acc = Decimal(ratios - wrong_ratios) / Decimal(ratios) if ratios else None
        amplification = (
            EvaluationService().amplification_coefficient(field_acc, ratio_acc)
            if field_acc is not None and ratio_acc is not None
            else None
        )
        criticality: dict[str, list[Decimal]] = {}
        for p in done:
            for code, value in p.criticality.items():
                criticality.setdefault(code, []).append(value)
        intercepted = sum(p.interception_cells[0] for p in done)
        measurable = sum(p.interception_cells[1] for p in done)
        return {
            "packages": len(self.packages),
            "evaluated": len(done),
            "reference_rejected": [p.package for p in self.packages if p.status == "REFERENCE_REJECTED"],
            "extraction_failed": [p.package for p in self.packages if p.status == "EXTRACTION_FAILED"],
            "unreadable": [p.package for p in self.packages if p.status == "UNREADABLE"],
            "fields_judged": fields,
            "fields_wrong": wrong_fields,
            "field_accuracy": field_acc,
            "ratios_judged": ratios,
            "ratios_wrong": wrong_ratios,
            "ratio_accuracy": ratio_acc,
            "amplification": amplification,
            "silent_false_positives": [
                {"package": p.package, "code": code}
                for p in done for code in p.silent_false_positives
            ],
            "criticality": dict(sorted(
                ((code, sum(v) / Decimal(len(v))) for code, v in criticality.items()),
                key=lambda pair: -pair[1],
            )),
            "interception_rate": Decimal(intercepted) / Decimal(measurable) if measurable else None,
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_campaign(corpus: str | Path, extract: Extractor | None = None,
                 engine: str | None = None) -> CampaignResult:
    corpus = Path(corpus)
    if not corpus.is_dir():
        raise FileNotFoundError(f"corpus folder not found: {corpus}")
    extract = extract or application_extractor()
    evaluation = EvaluationService()
    folders = sorted(p for p in corpus.iterdir()
                     if p.is_dir() and not p.name.startswith(("_", ".")))
    packages = [evaluate_package(folder, extract, evaluation) for folder in folders]
    inputs = {
        str(f.relative_to(corpus)).replace("\\", "/"): _sha256(f)
        for folder in folders for f in sorted(folder.iterdir())
        if f.is_file() and not f.name.startswith("~$")
    }
    return CampaignResult(corpus=str(corpus), engine=engine or "RULE_BASED",
                          packages=packages, inputs=inputs)



# --- exercise 20: the campaign as it is stored -------------------------
def json_safe(value):
    """Plain JSON: Decimal -> str, dataclass -> dict, tuple -> list."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if hasattr(value, "__dataclass_fields__"):
        return {k: json_safe(getattr(value, k)) for k in value.__dataclass_fields__}
    if isinstance(value, Path):
        return str(value)
    return value


def to_entity(
    campaign: CampaignResult, author: str | None = None, note: str | None = None
) -> E.EvaluationCampaign:
    """The campaign as the EvaluationRepository keeps it."""
    return E.EvaluationCampaign(
        kind=E.CAMPAIGN_CORPUS,
        summary=json_safe(campaign.summary()),
        engine=campaign.engine,
        corpus=campaign.corpus,
        author=author,
        note=note,
        inputs=json_safe(campaign.inputs),
        packages=json_safe(campaign.packages),
    )