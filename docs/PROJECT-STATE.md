# SYSCOHADA Extractor — Project State & Continuity Log

**Generated:** 12 October 2026, by direct inspection of the live codebase at
`C:\Users\HP\PycharmProjects\Financial Project` (this session is linked to that
machine). Everything in sections 3–7 below was read from the actual current
files on disk today, not reconstructed from chat history. Section 8 condenses
the five ChatGPT transcripts you had exported (Aug 6 – Oct 2); it is historical
record, kept for the thesis, and is **not** used as the source of truth for
"what's done" — the live code is.

**Why this file exists:** you asked that nothing be lost again, and that
nothing be invented. The safest way to guarantee both is a single file, in
your own repo, that states exactly what the code currently does, updated by
reading the code — not by remembering a conversation. Keep this file in
`docs/` alongside `ARCHITECTURE.md`, `LEARNING-PATH.md` and
`DATA-MODEL-REVIEW.md`, and ask whoever picks this project up next (me,
ChatGPT, or your supervisor) to read it first and re-verify it against the
code before trusting it.

---

## 1. Project identity

- **Working title:** AI-Assisted Extraction and Deterministic Financial
  Analysis of SYSCOHADA Financial Statements.
- **Organisation:** EB Partners / EB Audit & Advisory, Douala, Cameroon.
- **Governed by:** the supervisor's "Scoping and Design Dossier v2.0" (cited
  throughout the code as "the dossier", with section numbers — §3.2, §11.1,
  §18.1, etc. — that correspond to real sections of that document).
- **Research question (verbatim, from the dossier):** *"To what extent can
  AI-assisted extraction, deterministic ratio computation and human
  validation reliably transform a SYSCOHADA reporting package into usable
  financial indicators, and how does an extraction error propagate to those
  indicators?"*
- **Repo:** `ai-assisted-financial-statement-extractor` on GitHub, branches
  `main` (supervisor), `supervisor`, `test_corpus_campaign.py` (yours).
- **Explicit exclusions (dossier):** cash flow statement, notes to accounts,
  statement of changes in equity, multi-year/sector benchmarking, financial
  scoring, free-form AI commentary, IFRS/non-OHADA frameworks, ERP
  integration, production deployment, real non-anonymised client data.

---

## 2. How the project actually unfolded (one paragraph, so the rest makes sense)

You built a first version yourself in Weeks 1–3 (scoping, corpus planning,
a from-scratch `pdf_loader.py`/`document_processing` package). Around
**29 Sep 2026**, your supervisor restructured the whole backend into a
hexagonal/layered architecture and pushed it to `main`, wrapping your
existing `document_processing` code as an adapter rather than replacing it.
From that point on, the work became "exercises": `pytest -rs` originally
reported **52 passed, 18 skipped**, and the 18 skips were a self-documenting
to-do list, each marked `*** YOUR EXERCISE ***` in the code with a docstring
explaining the rule it must satisfy. Everything below is organised around
that exercise list, because that is how the actual repository is organised.

---

## 3. Architecture (verified against the live code today)

```
FRONTEND (React + Vite)
     |
API (Flask controllers — backend/app/api/)
     |
SERVICES (orchestration — backend/app/services/)
     |
DOMAIN (accounting rules — backend/app/domain/) — depends on nothing external
     |
  +--------+--------+---------------+
  v        v        v               v
checks.py ratios/  interpretation/  statement.py / syscohada.py / value_objects.py
```

Dependency rule (enforced by a real test, not just a convention):
`tests/unit/domain/test_entities_and_purity.py::test_the_domain_layer_depends_on_nothing_external`
walks every module under `app/domain` via `ast` and fails if any of
`flask, sqlalchemy, pdfplumber, fitz, pymupdf, openpyxl, pytesseract, PIL,
requests, anthropic, document_processing` is imported there. If you ever
need to touch this test to make it pass, the fix is to move the offending
code to `infra/`, not to widen the allow-list.

**Backend layout (as it exists today):**

```
backend/
  document_processing/        <- your original extractor, untouched
    pdf_loader.py, excel_loader.py, structure.py, normarlize.py,
    document_loader.py, output_writer.py
  app/
    __init__.py                <- composition root: build_container(), create_app()
    config.py                  <- Config dataclass, reads env vars
    api/
      routes.py                <- Flask blueprint, all HTTP endpoints
      serialisation.py         <- entity -> JSON, the frontend contract
      errors.py
    domain/
      entities.py              <- AnalysisCase, SourceDocument, ExtractionRun,
                                   ExtractedField, ExtractionRejection,
                                   ValidatedDataset, AuditEntry, DomainError
      value_objects.py         <- Amount, ItemCode
      statement.py             <- FinancialStatement
      syscohada.py             <- SYSCOHADA code catalogue, REQUIRED_CODES
      checks.py                <- CHK001-CHK005
      ratios/
        definition.py, engine.py,
        r01_current_ratio.py ... r05_return_on_equity.py
      interpretation/
        templates.py           <- Threshold, Interpretation, interpret()
    infra/
      pdf/readers.py           <- PdfReader, ExcelReader (DocumentReader port)
      llm/
        claude_structurer.py, rule_based.py, cache.py, prompts/v1.md
      db/
        models.py, repositories.py, memory.py, session.py
      export/
        spreadsheet.py          <- FR-19, openpyxl
    services/
      extraction_service.py, validation_service.py,
      analysis_service.py, evaluation_service.py
frontend/src/
  pages/        CasesPage.jsx, ReviewPage.jsx, DashboardPage.jsx
  components/   ChecksPanel.jsx, StatusPill.jsx, ExcelSourceViewer.jsx
  api/client.js
  styles/app.css
tests/
  unit/domain/   test_checks.py, test_ratios.py, test_value_objects.py,
                 test_entities_and_purity.py
  unit/services/ test_validation_service.py
  unit/          test_claude_structurer.py, test_extraction_service.py,
                 test_evaluation.py
  integration/   test_api_end_to_end.py
docs/            ARCHITECTURE.md, DATA-MODEL-REVIEW.md, LEARNING-PATH.md
```

---

## 4. Status, verified against the live code today

| Week / area | Deliverable | Status | Evidence |
|---|---|---|---|
| Week 1 | Scoping note | ✅ Done | Project definition, 5-ratio reduction, pipeline agreed (dossier v2.0) |
| Week 2 | Test corpus (20–30 packages) + annotations + ground truth | ⚠️ **Not actually built** | `data/test_documents/` contains only **one** package (`PKG001`: 2 PDFs + 1 xlsx). No `annotations/` or `ground_truth/` folders exist anywhere in the repo. The 20–30-package corpus, the annotation spreadsheets, and the manually-calculated reference ratios described at length in your planning conversations were **planned but never created on disk.** |
| Week 3 | PDF ingestion / document processing | ✅ Done (superseded) | `document_processing/` exists and is wrapped by `infra/pdf/readers.py` (`PdfReader`, `ExcelReader`) |
| Week 3 (post-restructure) | R2, R3, R4, R5 ratio calculators | ✅ Done | `domain/ratios/r02..r05_*.py` all implemented, no `NotImplementedError` |
| Week 3 (post-restructure) | CHK002, CHK003, CHK004 | ✅ Done | `domain/checks.py` — all 5 checks (CHK001–CHK005) implemented |
| Week 4 | Prompt `v1.md` | ✅ Done | `infra/llm/prompts/v1.md`, versioned, rules documented |
| Week 4 | `ClaudeStructurer._call_model` | ✅ Done (code complete) | `infra/llm/claude_structurer.py` — real Anthropic call wired, cost accounting, one retry with validation-error feedback. **Never actually invoked against the real API** — no `ANTHROPIC_API_KEY` was available during development; all tests mock `anthropic.Anthropic`. |
| Week 4 (Exercise #10) | Record what the schema rejected | ✅ Done | `ExtractionRejection` entity exists; `extraction_service.py::_to_fields` returns `(fields, rejections)` |
| Week 5, Ex. 11 | Thresholds or documented absence | ✅ Done | `templates.py`: R1 = 1.0, R3 = 1.0 (both sourced), R2/R4/R5 deliberately `None` after multi-source research — see §5 below |
| Week 5, Ex. 12 | Serve the source document | ✅ Done | `GET /api/documents/<id>/file` (PDF/XLSX/XLS, correct mimetypes) |
| Week 5, Ex. 13 | What "reopen" invalidates | ✅ Done | `ValidationService.reopen()`; `AnalysisService` (see below) refuses analysis while `UNDER_REVIEW` |
| Week 6, Ex. 14 | Side-by-side source document (FR-10) | ✅ Done, and extended | `ReviewPage.jsx` embeds the PDF via `<iframe src={getDocumentFileUrl(...)}>`; **Excel documents get a dedicated `ExcelSourceViewer.jsx`** (sheet tabs, row/column table) backed by a new `GET /api/documents/<id>/preview` route — this is beyond what any of the five chat transcripts describe having been finished |
| Week 6, Ex. 15 | Export (FR-19) | ✅ Done | `GET /api/cases/<id>/export` returns a real `.xlsx` via `infra/export/spreadsheet.py`; `DashboardPage.jsx` has a working "Export analysis as spreadsheet" button |
| FR-15–18 | Ratio dashboard, interpretation drill-down | ✅ Done | `DashboardPage.jsx`: ratio cards (COMPUTED/NOT_COMPUTABLE), "View details"/"View reason", interpretation text + cited reference, calculation inputs table |
| FR-20 | Year-over-year (N vs N-1) comparison | ✅ Done | `ValidatedDataset` now carries `prior_year_amounts` (this is new relative to every transcript — see §7); `GET /api/cases/<id>/analysis` computes a real N-1 comparison, preferring N-1 from the same validated package and falling back to a separately-validated prior-year case for the same client; `DashboardPage.jsx`'s `YearComparison` renders it, or "Prior-year data not available" when there is none |
| FR-21 | Sensitivity / error-injection campaign (§19.2) | ✅ Done (pre-built by supervisor) | `EvaluationService.sensitivity_matrix()` — perturb an item by 1/5/10%, recompute every ratio, flag whether checks would have caught it. `POST /api/evaluations` exposes it; `client.js` has `runSensitivity()`. **No frontend page renders it yet** — there's no "Evaluation" tab in the React app. |
| FR-21 (persistence) | `GET /api/evaluations/<id>` | ❌ Stub | Returns `501 not_implemented`; explicit open exercise: "campaigns are computed but not persisted — decide whether they need to be, and document the choice" |
| §18.1 (Part D) | `field_accuracy()` | ❌ Not implemented | `evaluation_service.py` — `raise NotImplementedError`, **zero tests exist** |
| §18.1 (Part D) | `ratio_accuracy()` | ❌ Not implemented | same file, same status |
| §18.1 (Part D) | `amplification_coefficient()` | ❌ Not implemented | same file, same status |
| §18.1 (Part D) | `silent_false_positives()` | ❌ Not implemented, **flagged "implement this one first — the most important indicator"** | same file, same status |
| Week 7–8 | Replay corpus, inject errors, write thesis results | ❌ Cannot start yet | Blocked on both the missing corpus/ground truth (Week 2) and the four Part D methods above |

**Bottom line:** the interface (Weeks 1–6) is further along than any single
chat transcript shows — DashboardPage, the Excel side-by-side viewer, export,
and year-over-year comparison are all finished and working in the code on
your machine right now. The part that is genuinely not started is **Part D**:
the four evaluation metrics, and — more fundamentally — the **test corpus and
ground truth that Part D needs to run against, which was planned in detail
but never actually built.**

---

## 5. Domain rules of record (exact, current)

**Case lifecycle** (`domain/entities.py`):
`CREATED → EXTRACTING → {EXTRACTED | EXTRACTION_FAILED}`;
`EXTRACTION_FAILED → EXTRACTING`; `EXTRACTED → {UNDER_REVIEW, VALIDATED,
EXTRACTING}`; `UNDER_REVIEW → {VALIDATED, EXTRACTING}`;
`VALIDATED → {ANALYSED, UNDER_REVIEW}`; `ANALYSED → {UNDER_REVIEW}` (reopening
invalidates the computed results — enforced by `AnalysisService`, not by
deleting anything).

**Field status:** `PROPOSED → CORRECTED` (via `ExtractedField.correct()`,
refuses once `VALIDATED`) `→ VALIDATED_FIELD`; `KEYED` for hand-entered
fields.

**The five ratios (final formulas, as implemented):**

| Code | Name | Formula | Threshold |
|---|---|---|---|
| R1 | Current ratio | (BK + BT) / (DP + DT) | **1.0**, documented (methodological note) |
| R2 | Equity ratio | CP / (CP + DD) | None — insufficient trustworthy evidence for this exact formula |
| R3 | Stable funding coverage | (CP + DD) / AZ (net fixed assets) | **1.0**, documented (converging prudential/regional sources) |
| R4 | Net margin | XI / XB × 100 | None — sources found were sector/listing-specific, not general |
| R5 | Return on equity | XI / CP × 100, raises on negative equity → NOT_COMPUTABLE | None — no sufficiently universal benchmark found |

R2/R4/R5 were deliberately left without a threshold after you corrected an
earlier draft that had assigned numbers from weakly-matching sources — see
your own quote in §9. This is a defensible, intentional methodological
choice, not an unfinished task.

**SYSCOHADA code catalogue** (`domain/syscohada.py`) — the 11 required codes:
`AZ` (fixed assets/net), `BK` (current assets), `BT` (cash, asset side), `BZ`
(total assets), `CP` (equity), `DD` (financial debt), `DP` (current
liabilities), `DT` (cash, liability side), `DZ` (total liabilities+equity),
`XB` (revenue), `XI` (net income). `BU`, `DV` (currency translation
differences) and `CJ`/`XG` exist in the catalogue but are optional / not
required.

**Consistency checks** (`domain/checks.py`), all implemented:
- CHK001 — balance-sheet equilibrium, `AZ+BK+BT(+BU) = BZ` and
  `CP+DD+DP+DT(+DV) = DZ`.
- CHK002 — subtotal consistency (same equation, re-expressed per the
  dossier's definition).
- CHK003 — net income consistency, `XI == CJ`.
- CHK004 — completeness (all `REQUIRED_CODES` present).
- CHK005 — plausible signs (negative `AZ/BK/BT/BZ/XB` → WARNING, not
  blocking).

**Interpretation** — exactly three templates, enforced by
`test_nothing_is_ever_generated_freely`: `T_NOT_COMPUTABLE`,
`T_FACTUAL_NO_REFERENCE`, `T_COMPARED_TO_THRESHOLD`. No other sentence shape
can ever reach the dashboard.

---

## 6. Database (verified)

Storage is switched by `STORAGE=memory|sql` + `DATABASE_URL`
(`backend/app/config.py`, loaded via `load_dotenv()`). No migrations tool
(Alembic) — `Base.metadata.create_all()` only, by design, "not this week."

**Tables (`infra/db/models.py`):** `analysis_case`, `document`,
`extraction_run`, `extracted_field`, `check_result`, `validated_dataset`,
`ratio_result`, `interpretation`, `audit_log`.

**Resolving the open "Postgres enum" question from earlier in this project:**
there are **no native Postgres ENUM types anywhere in this schema.** Every
status/category column (`status`, `engine`, `doc_type`, `severity`,
`ratio_code`, etc.) is a plain `String`, constrained only by Python-level
string constants in `domain/entities.py`. This is confirmed directly from
today's `models.py` — there's nothing to "fix" or reconcile with an old
`analysis_status` enum; the current schema never adopted DB-level enums at
all. Worth a one-line mention in the thesis as a known limitation if you
want to be thorough, but it is not blocking anything.

**Confirmed but worth knowing:** `ratio_result`, `interpretation` and
`check_result` tables exist in the schema but **nothing writes to them** —
`repositories.py` has no `SqlRatioResultRepository`/`SqlCheckResultRepository`.
Ratios, checks and interpretations are recomputed on every request from the
`ValidatedDataset` (which *is* persisted) rather than stored. This is
consistent with the architecture ("pure computation, no repository needed")
but means there is currently no historical record of what a dashboard showed
on a given date if the underlying ratio formulas later change — a thesis-worthy
observation if you discuss traceability over time.

**`ValidatedDataset` now carries two fiscal years** (this is new relative to
everything in the chat transcripts): `amounts` (year N) and
`prior_year_amounts` (year N-1), stored together in the existing
`validated_dataset.amounts` JSON column as `{"N": {...}, "N-1": {...}}`, with
a backward-compatibility read path in `repositories.py` for any older row
that still holds year-N amounts directly. This is what makes the FR-20
year-comparison feature work from a single upload when the source document
includes both years' columns.

---

## 7. What's genuinely open right now

In order of what blocks what:

1. **The test corpus and ground truth (Week 2 deliverable) do not exist.**
   Only one real package (`PKG001`) is on disk. Part D (§18.1) cannot be
   meaningfully evaluated without a corpus with known-correct values to
   compare against. This is the single biggest gap between the dossier's
   plan and the current repository, and it's worth raising with your
   supervisor explicitly rather than assuming a smaller corpus is fine.
2. **Four evaluation methods are unimplemented** in `evaluation_service.py`:
   `field_accuracy`, `ratio_accuracy`, `amplification_coefficient`,
   `silent_false_positives` (in that dependency order — amplification needs
   the first two; the dossier itself flags `silent_false_positives` as the
   one to implement first because it's the project's headline risk
   indicator). Each has a precise docstring spec already written for you
   (quoted in full in the file) and zero tests.
3. **`GET /api/evaluations/<id>` is a 501 stub** — a real design decision
   (persist campaign results, or just the inputs, since the computation is
   deterministic and cheap) is still open and explicitly deferred to you.
4. **No frontend page renders the sensitivity campaign** (FR-21) — the
   backend endpoint and the `client.js` call exist, but there's no
   "Evaluation" tab/page in `frontend/src/pages/`.
5. Two smaller, non-blocking items: the rule-based-structurer-vs-corpus
   baseline comparison that Week 4 asked for ("before spending money on
   Claude, measure what the rule-based structurer already gets right") was
   never formally run — **except for one real, measured data point now on
   record** (below); and the real Anthropic API has never actually been
   called (previously blocked on your supervisor obtaining a key — worth
   confirming that's no longer the case before Week 7 corpus replay, since
   that's real cost).

   **One measured rule-based failure, with cause (13 Oct 2026).** `client4`'s
   document (`ETAT_FINANCIER_TEST2.pdf`, a genuinely scanned 2-page PDF —
   confirmed directly via pdfplumber: 0 native text characters, 0 detected
   tables, 1 embedded image, on both pages) fails `RuleBasedStructurer` with
   `"no usable item found in the document"`, even after two real fixes:
   - `document_processing/pdf_loader.py` gained `ocr_page_table()` /
     `words_to_table()`: Tesseract's word-level `image_to_data` output is
     reconstructed into the same row/column grid shape
     `pdfplumber.extract_tables()` returns, so a scanned page can reach
     `find_side_start_columns()`/`extract_line_items()` at all. Previously
     OCR only ever fed `pages_text` — never `document.tables` — which is
     the literal reason every scanned document failed outright, independent
     of OCR quality.
   - `document_processing/structure.py`'s `find_side_start_columns()` gained
     a fallback: when the literal word `"REF"` doesn't survive OCR, it looks
     for a column where the two-letter SYSCOHADA codes themselves (AA, AB,
     AC…) recur instead.

   Both are real and tested (10 new unit tests:
   `tests/unit/test_pdf_ocr_table.py`, plus additions to
   `tests/unit/test_document_structure.py`), and neither touches the
   native-PDF path — confirmed client1/client2/client3/SOCATRANS still
   extract exactly as before (198/198/188/198 fields respectively,
   unchanged). Neither rescues this specific file: on
   `ETAT_FINANCIER_TEST2.pdf`, the word positions recovered from OCR are
   scrambled badly enough (page skew/resolution — not a code defect) that
   no column, REF or otherwise, survives as a clean, recurring structure.
   Example — the actual reconstructed row for what should be one
   balance-sheet line item:
   `['559', '819911', '169 382 179', None, '437 732 419', None, '+ -}',
   '452948 553', '119', None, None]`

   Kept as a documented limitation rather than chased further with more
   rule-based engineering, per `infra/llm/rule_based.py`'s own docstring:
   *"The language model earns its place on the documents this class fails
   on: unusual layouts, scans, non-standard labels."* This is exactly that
   case, now with a real measurement behind it rather than an assumption —
   a legitimate §11.1 data point, not a bug to keep fixing.

---

## 8. Condensed chronological history (from your 5 ChatGPT exports)

This is historical context for the thesis narrative, not a status source —
section 4 is the status source. Dates are as they appear in the transcripts.

- **Aug 6:** Early, explicitly-provisional brainstorm of 10 "Data
  Analytics & Dashboard" business-idea themes for EB Partners (bilingual,
  caveated as needing confirmation against a separate internal chat).
- **Aug 25:** Summary of the *original* v1 scoping doc — Balance Sheet +
  Income Statement only, year N only, **ratios explicitly out of scope**.
- **Sep 9:** Pivot — after reading "ratio finance.txt", ratios became the
  project's core, which directly contradicted the v1 scope's exclusion of
  ratios and its "year N only" limit (Activity-type ratios need N-1).
- **Sep 11:** Supervisor's "Scoping and Design Dossier v2.0" read and
  explained in full: the 5-ratio reduction (from an original ~13 candidates),
  the four evaluation constructs (field accuracy, ratio accuracy,
  amplification coefficient, item criticality/sensitivity), "silent false
  positive" as the headline risk concept, and the explicit warning: *"If the
  complete chain is not working by the end of Week 5, reduce the interface
  rather than reducing the evaluation."* This dossier is what resolved the
  v1-vs-pivot tension in (2) above — ratios are now central and explicitly
  scoped.
- **Sep 14:** Week 1 presentation finalised as an 8-slide deck tied to the
  dossier's Week 1 milestone. Week 2 (corpus/ground truth) concepts defined.
  A proposal to also use the Trial Balance/General Ledger for validation was
  raised and then explicitly dropped — summarized statements only.
- **Sep 18 – Sep 22:** Week 2 planning in full detail: dataset inventory
  schema, annotation procedure, Confirmed/Ambiguous/Missing/To-be-verified
  statuses, the ground-truth verification checklist, and the first full
  statement of all five ratio formulas with a worked numeric example. **(Per
  §4/§7 above, this plan was never executed on disk beyond one package.)**
- **Sep 23–25:** Week 3 kickoff — first `pdf_loader.py`, PyCharm/venv setup,
  an emergency 9-slide PPTX built same-day for a presentation deadline.
- **Sep 25 (evening) – Sep 28:** GitHub repository created and pushed;
  supervisor added as collaborator; a `.gitignore` bug (hiding
  `data/extracted/` from Git, though PyCharm still showed it locally) found
  and fixed.
- **Sep 29, 9:54 AM — the major pivot:** supervisor restructured the entire
  project into the hexagonal architecture described in §3, pushed to `main`,
  created the `test_corpus_campaign.py` branch for your work, and reframed the remaining work as
  the 18-skipped-test exercise list.
- **Sep 29 (afternoon) – Oct 2:** the bulk of the real implementation work —
  PostgreSQL setup (port turned out to be 5433, not 5432; fixed via
  `$env:STORAGE`/`$env:DATABASE_URL` in the same PowerShell session before
  `python wsgi.py`), CHK002–004, R2–R5 (including the negative-equity design
  decision on R5 — your own, documented, first "genuinely yours" design
  decision on the project), the Week 4 `ClaudeStructurer` (`_call_model`,
  prompt `v1.md`, file-based response cache, cost model at $2/$10 per
  million input/output tokens), Exercise #10 (rejection tracking), and the
  Week 5 Exercise 11 threshold research — three rounds of source-gathering,
  ending with you correctly rejecting an over-eager first attempt that had
  assigned numbers to R2/R4/R5 from weakly-matching sources (quoted in §9).
  This transcript ends mid-Exercise 12, waiting on two pasted files.
- **(continuing, per the two later transcripts not re-summarised here since
  they're already fully captured in this session's memory):** Exercise 12
  (serve document) and Exercise 13 (reopen/invalidate) completed with a full
  TDD cycle; Week 6 Exercise 14 (ReviewPage iframe) and a live
  `document_processing` import-path bug (Flask must start from inside
  `backend/`) fixed; PostgreSQL persistence made permanent via
  `load_dotenv()` in `config.py`; Exercise 15 (export) completed, including
  a real bug where `dataset_json()` deliberately omits `amounts` and the
  exporter needs `{**dataset_json(dataset), "amounts": dataset.amounts}`.
- **Beyond all five transcripts:** the Excel side-by-side viewer, the FR-20
  year-comparison logic with `prior_year_amounts`, and the full DashboardPage
  were built and are working in the code today, but no transcript you
  exported documents how — this happened either in a conversation not
  exported, or directly. Worth knowing for your own records, not something
  to redo.

---

## 9. Verbatim lessons — how you've asked this project to be run

These are your own words from the transcripts, correcting an earlier
assistant. They are the actual working agreement for this project and apply
here too:

> "all your response more reference the discussion on the referenced chat no
> assumption" — ground every claim in the actual code or actual prior output,
> never invent.

> "i have already send that output so refers yourself and let continue" /
> "i have already send you all this information what is inside all this
> folder. why are you turning around asking the same thing" — don't re-ask
> for information already given; look it up.

> "you are not given exact source i dont want you to force a threshold ... if
> you cannot trust enough the different sources to assign a threshold let us
> just not put it" — when evidence is weak, say so and leave the gap
> documented, rather than filling it to look complete.

> "remember inside the LEARNING-PATH.md after the week3 ... we were expected
> we had the week4" — follow the supervisor's declared sequencing; don't
> opportunistically fix unrelated TODOs out of order.

> "nooh your are not still in page this is not the status of all the ratio
> there are some with threshold and some without" — get partial-status claims
> exactly right (some ratios have thresholds, some don't — say which).

> "week 14 was already completed how can we start week 15 without completing
> week 14" — don't let exercise/week numbering drift from the supervisor's
> actual list.

This document (§4 especially) was built by re-reading the actual files for
exactly this reason — every status claim above is traceable to a specific
file and, where relevant, a specific line.

---

## 10. Open decisions for you (and, where noted, your supervisor)

1. **Corpus gap.** Is a 1-package corpus acceptable for the evaluation
   chapter, or does the 20–30-package corpus need to be built before Part D
   can proceed? This changes the critical path significantly and is worth
   raising with your supervisor directly rather than deciding alone.
2. **Evaluation campaign persistence** (`GET /api/evaluations/<id>`) — store
   full results, or just the inputs (since recomputation is cheap and
   deterministic)? Either is defensible; the exercise asks you to choose and
   write down why.
3. **Evaluation UI** — does FR-21 need its own page in the React app for the
   live demo, or is the API response (already working) sufficient for the
   defense?
4. **Anthropic API key** — confirm whether your supervisor has now obtained
   one, since Week 7's corpus replay is the first point real API cost
   appears.

I'm ready to start on whichever of these you want — most naturally
`silent_false_positives()` first (per the dossier's own instruction and
because it needs no corpus beyond `PKG001` plus a couple of hand-crafted test
statements to prove it works), with the corpus-size conversation with your
supervisor happening in parallel.

---

## 11. Fixes applied since 12 Oct 2026 (verified against live code)

Five real bugs, found and fixed since this file was last generated, each
with its own test proving the bug was real (reverted and confirmed failing
before being fixed) rather than assumed:

1. **Stale-row pattern across repository lookups.** The bug that caused a
   dashboard/export/reopen to show a stale validated dataset after a case
   was reopened and re-validated (`find_by_extraction` returning the first
   matching row instead of the most recently validated one) turned out to
   be a repeated shape, not a one-off: the same "assumes exactly one row,
   no ordering" mistake was present in `InMemoryDatasetRepository` as well
   as the SQL one fixed earlier. Consolidated into one
   `_latest_validated_dataset(c, case)` helper in `app/api/routes.py`, used
   by `reopen_case()`, `case_dashboard()` (including the FR-20 prior-year
   fallback) and `export_case()` (which also gained a guard against
   silently returning `None`/crashing when no dataset exists yet).
   Evidence: `tests/unit/infra/test_memory_repositories.py`,
   `tests/integration/test_api_end_to_end.py::test_dashboard_reopen_and_export_use_the_most_recently_validated_run`.

2. **`SOCATRANS_2023.xlsx` failed extraction outright.**
   `document_processing/structure.py`'s `find_side_start_columns()` only
   ever checked `table[0]` for the literal cell `"REF"`, assuming every
   spreadsheet's header sits on row 0. Real documents (SOCATRANS) open
   with a title line, an entity/ID block and a disclaimer sentence first.
   Fixed to scan forward for the first row that actually contains `"REF"`.
   Confirmed directly: 0 extracted items → 198, all consistency checks
   passing. Evidence: `tests/unit/test_document_structure.py`.

3. **CHK002's gap reported as `0` instead of `0.00`.** The passing branch
   of `check_subtotal_consistency` in `domain/checks.py` returned a plain
   `gap=0` instead of a properly quantized `Decimal`, breaking BR-15's
   "amounts rounded to two decimals" rule inconsistently with every other
   check. Fixed to reuse the already-quantized zero. Evidence:
   `tests/unit/domain/test_checks.py::test_passing_gap_is_quantized_to_two_decimals_like_every_other_check`.

4. **No way to retry a failed extraction from the UI.** `CasesPage.jsx`
   gated the upload control on `!latestExtraction`, so once any run
   existed on a document — even a failed one — there was no way to
   re-trigger extraction on it (this is exactly what client4/client5 hit).
   Added a "Retry extraction" button, shown when the latest extraction's
   status is `EXTRACTION_FAILED`, with `failure_reason` as a tooltip. This
   needed `app/api/routes.py`'s `list_cases()` fixed too — it built each
   extraction entry by hand, omitting `failure_reason`,
   `prompt_version`, `started_at`, `finished_at`; now uses
   `run_json(run, fields=False)`, which already carries all of them.

5. **`document.page_count` / `is_scanned` never persisted.**
   `ExtractionService.run_extraction()` learns both only once the reader
   has actually opened the file, and set them directly on the in-memory
   `SourceDocument` — but `DocumentRepository` (the port) had no `save()`
   method at all, so the mutation never reached the database. Every
   document, including ones whose extraction succeeded, reported
   `page_count=null`, `is_scanned=null` forever. This is what hid, for a
   while, the real reason client4 kept failing: the UI had no way to show
   "this is a scan" because the field never reached it.
   `InMemoryDocumentRepository` happened to look fine by accident (it
   stores the exact same Python object by reference, so the mutation was
   "already" visible without a save call) — which is why the bug only
   showed up against the real SQL-backed database. Fixed: `save()` added
   to the `DocumentRepository` port and both adapters
   (`InMemoryDocumentRepository`, `SqlDocumentRepository`), called from
   `run_extraction()`. Evidence:
   `tests/unit/infra/test_sql_document_repository.py` — written specifically
   because the in-memory test couldn't have caught this bug at all, for the
   reference-semantics reason above.

See §7 item 5 for the related, still-open finding on client4's actual scan
(the OCR-to-table reconstruction and REF-tolerance fallback, and why
neither rescues that specific file).