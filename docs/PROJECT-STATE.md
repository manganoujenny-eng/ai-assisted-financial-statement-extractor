# SYSCOHADA Extractor: Project State and Continuity Log

**First generated:** 12 October 2026. **Updated:** 22 October 2026, and on
27 October 2026 for the six changes of §12 (super administrator, archive,
PDF export, supervisors' discussion, case responsibility, Read with AI), again by
reading every file of the live codebase at
`C:\Users\HP\PycharmProjects\Financial Project`, not by remembering a
conversation. Sections 3–7 and 10 state what the code does today. Section 8
is the history, section 9 the working agreement, sections 10–12 the fixes
and the work done since the first version of this file.

**Why this file exists:** you asked that nothing be lost again, and that
nothing be invented. The safest way to guarantee both is a single file, in
your own repo, that states exactly what the code currently does, updated by
reading the code. Ask whoever picks this project up next (me, another
assistant, or your supervisor) to read it first and re-verify it against the
code before trusting it.

Companion documents: `FILE-GUIDE.md` (what every file does),
`ARCHITECTURE.md` (why it is arranged this way), `EXTRACTION-PIPELINE.md`,
`DATA-MODEL-REVIEW.md`, `LEARNING-PATH.md`.

---

## 1. Project identity

- **Working title:** AI-Assisted Extraction and Deterministic Financial
  Analysis of SYSCOHADA Financial Statements.
- **Project Title:** AI-Assisted Financial Statement Extractor
- **Organisation:** EB Partners / EB Audit & Advisory, Douala, Cameroon.
- **Governed by:** the supervisor's "Scoping and Design Dossier v2.0" (cited
  throughout the code as "the dossier", with section numbers such as §3.2,
  §11.1, §18.1 that correspond to real sections of that document).
- **Research question (verbatim, from the dossier):** *"To what extent can
  AI-assisted extraction, deterministic ratio computation and human
  validation reliably transform a SYSCOHADA reporting package into usable
  financial indicators, and how does an extraction error propagate to those
  indicators?"*
- **Repo:** `ai-assisted-financial-statement-extractor` on GitHub, branches
  `main` (supervisor), `supervisor`, `test` (yours).
- **Explicit exclusions (dossier):** cash flow statement, notes to accounts,
  statement of changes in equity, multi-year/sector benchmarking, financial
  scoring, free-form AI commentary *as a conclusion* (the commentary that
  exists is a draft an analyst must approve, see §5), IFRS/non-OHADA
  frameworks, ERP integration, production deployment, real non-anonymised
  client data.

---

## 2. How the project actually unfolded

I built a first version myself in weeks 1–3 (scoping, corpus planning,
a from-scratch `document_processing` package). Around **29 Sep 2026** your
supervisor restructured the backend into a hexagonal/layered architecture
and pushed it to `main`, wrapping your `document_processing` code as an
adapter rather than replacing it. From then on the work became "exercises":
`pytest -rs` reported **52 passed, 18 skipped**, the 18 skips being a
self-documenting to-do list, each marked `*** YOUR EXERCISE ***`.

All of those exercises are now done (weeks 3–7). Beyond them, the
prototype grew the features a real firm needs to use it: sign-in and three
roles, supervisor assignment and notifications, an AI commentary that an
analyst approves, French and English screens, and an administration area
that replaces pgAdmin and the command line. **Today: 237 tests, all
passing, none skipped.**

---

## 3. Architecture (verified 22 Oct 2026)

```
FRONTEND (React + Vite)       pages by role, api/client.js, i18n (en/fr)
     |
API (Flask, backend/app/api/) routes.py · auth.py (sign-in, roles) · admin.py
     |
SERVICES (orchestration)      extraction · validation · analysis · insight (AI)
     |                        case · user · archive · overview · evaluation · corpus_campaign
DOMAIN (accounting rules)     entities + lifecycle · checks · ratios ·
     |                        interpretation · statement · syscohada · ports
INFRA                         pdf readers · rule-based / Claude structurer · Claude vision ·
                              Claude analyst · cache · SQL + in-memory repos · Excel / PDF export
```

The dependency rule is enforced by a real test:
`tests/unit/domain/test_entities_and_purity.py::test_the_domain_layer_depends_on_nothing_external`
walks every module under `app/domain` and fails if `flask`, `sqlalchemy`,
`pdfplumber`, `fitz`, `pymupdf`, `openpyxl`, `pytesseract`, `PIL`,
`requests`, `anthropic` or `document_processing` is imported there. If you
ever need to touch this test to make it pass, the fix is to move the
offending code to `infra/`, not to widen the allow-list.

Full layout, file by file: `FILE-GUIDE.md`. Reasons and rule locations:
`ARCHITECTURE.md`.

---

## 4. Status, verified against the live code (22 Oct 2026)

| Week / area | Deliverable | Status | Evidence |
|---|---|---|---|
| Week 1 | Scoping note | ✅ Done | Project definition, 5-ratio reduction, pipeline agreed (dossier v2.0) |
| Week 2 | Test corpus (20–30 packages) + ground truth | ⚠️ **1 package** | `data/corpus/RP001/` holds one statement and its hand reading (`annotation_RP001_1.xlsx`). The 20–30 packages are still to be built; the whole evaluation chain is ready for them. |
| Week 3 | Document processing | ✅ Done | `document_processing/`, wrapped by `infra/pdf/readers.py` |
| Week 3 | R2–R5 | ✅ Done | `domain/ratios/r02..r05_*.py`; R5 refuses negative equity (your decision) |
| Week 3 | CHK002, CHK003, CHK004 | ✅ Done | `domain/checks.py`, all five checks |
| Week 4 | Prompt `v1.md`, `_call_model`, rejections | ✅ Done | `infra/llm/claude_structurer.py`, `prompts/v1.md`, `ExtractionRejection` |
| Week 5 | Ex. 11 thresholds | ✅ Done | R1 = 1.0, R3 = 1.0 (sourced); R2, R4, R5 deliberately none |
| Week 5 | Ex. 12 serve the document, Ex. 13 reopen | ✅ Done | `GET /api/documents/<id>/file`; `ValidationService.reopen()` |
| Week 6 | Ex. 14 side-by-side review | ✅ Done | `ReviewPage.jsx`: PDF in an iframe, Excel in `ExcelSourceViewer.jsx` |
| Week 6 | Ex. 15 export | ✅ Done | `GET /api/cases/<id>/export?format=xlsx|pdf`, `infra/export/spreadsheet.py`, `infra/export/pdf_report.py` |
| FR-15–20 | Dashboard, interpretation, N vs N-1 | ✅ Done | `DashboardPage.jsx`, `YearComparisonChart.jsx` |
| Week 7 | Ex. 16 silent false positives | ✅ Done | `EvaluationService.silent_false_positives` + tests |
| Week 7 | Ex. 17 field accuracy | ✅ Done | exact to the franc; a missing field counts as wrong |
| Week 7 | Ex. 18 ratio accuracy | ✅ Done | within 1 % of the ground-truth ratio, on the **unrounded** value |
| Week 7 | Ex. 19 amplification coefficient | ✅ Done | ratio error rate ÷ field error rate; none when no field is wrong |
| Week 7 | Ex. 20 persist campaigns | ✅ Done | tables `evaluation_campaign`, `evaluation_package`; `GET /api/evaluations/<id>`; deletable by the administrator, traced in the audit |
| Week 7 | Corpus campaign | ✅ Done | `services/corpus_campaign.py`, `evaluate_corpus.py`, Administration → Campaigns. One CLI run is on disk: `data/corpus/_results/campaign_20261020_160543.json` |
| FR-21 | Sensitivity test | ✅ Done | `EvaluationService.sensitivity_matrix()`, run per package from Campaigns, item × ratio matrix shown |
| Week 8 | Writing | ⏳ Open | No new feature planned; see §7 |

---

## 5. Domain rules of record (exact, current)

**Case lifecycle** (`domain/entities.py`, `ALLOWED_TRANSITIONS`):

```
CREATED → EXTRACTING → EXTRACTED | EXTRACTION_FAILED
EXTRACTION_FAILED → EXTRACTING                    (retry; the failed run is kept)
EXTRACTED    → UNDER_REVIEW | SUBMITTED | EXTRACTING
UNDER_REVIEW → SUBMITTED | EXTRACTING
SUBMITTED    → VALIDATED | UNDER_REVIEW           (validate, or send back)
VALIDATED    → ANALYSED | UNDER_REVIEW            (reopening is traced)
ANALYSED     → UNDER_REVIEW                       (reopening invalidates the results)
```

Nothing is validated that the analyst has not first submitted (§6.2). The
analyst chooses the supervisor at submission; only that supervisor is
notified and may validate or send back. A supervisor who is no longer active
releases their cases to every supervisor.

**Field status:** `PROPOSED → CORRECTED → VALIDATED`; `KEYED` for an item
entered by hand (never proposed, so it does not distort the accuracy
figures). The proposed amount is never overwritten (BR-10).

**Roles:** ANALYST (prepares their own cases), SUPERVISOR (validates the
cases submitted to them, manages analysts, sees everyone's work, deletes
analysed cases they validated, discuss any case), ADMIN (runs the system:
accounts, audit, data, corpus, campaigns, archive; never prepares nor
validates), SUPERADMIN (exactly one, created by `create_superadmin.py`:
everything an administrator does, plus managing administrators). Only the
person a case is assigned to acts on it.

**The five ratios:**

| Code | Name | Formula | Threshold |
|---|---|---|---|
| R1 | Current ratio | (BK + BT) / (DP + DT) | **1.0**, documented |
| R2 | Equity ratio | CP / (CP + DD) | None, deliberately |
| R3 | Stable funding coverage | (CP + DD) / AZ (net) | **1.0**, documented |
| R4 | Net margin | XI / XB × 100 | None, deliberately |
| R5 | Return on equity | XI / CP × 100; negative equity → NOT_COMPUTABLE | None, deliberately |

R2/R4/R5 were deliberately left without a threshold after you rejected an
earlier draft that had assigned numbers from weakly matching sources (your
own words in §9). A methodological choice, not an unfinished task.

**Required items (11):** AZ, BK, BT, BZ, CP, DD, DP, DT, DZ, XB, XI. The
campaign also judges CJ, BU and DV when the hand reading has them.

**Consistency checks** (`domain/checks.py`):

- CHK001, blocking: balance sheet equilibrium, BZ = DZ, to the franc.
- CHK002, blocking: subtotals, AZ + BK + BT (+ BU) = BZ and
  CP + DD + DP + DT (+ DV) = DZ (BU, DV counted only when present).
- CHK003, blocking: net income consistency, XI = CJ.
- CHK004, blocking: completeness, every required item present.
- CHK005, warning: plausible signs.

A check whose items are missing is reported as passed with an explicit
message: the absence is CHK004's business, and failing twice would make one
problem look like two.

**Interpretation:** exactly three templates (`T_NOT_COMPUTABLE`,
`T_FACTUAL_NO_REFERENCE`, `T_COMPARED_TO_THRESHOLD`), enforced by a test.
The frontend rebuilds the same sentence in French or English from the
template and threshold the backend sends.

**AI commentary** (`services/insight_service.py`, prompt `analysis_v3.md`):
written *about* validated figures, never proposing one; receives no client
name, year or document (NFR-04); written in the screen's language; stored as
a DRAFT and shown as part of the analysis only once an analyst approves it,
the original text being kept beside any edit (BR-13).

---

## 6. Database (verified)

Storage: `STORAGE=memory|sql` + `DATABASE_URL` (PostgreSQL in your `.env`;
SQLite `data/prototype.db` when empty). No migration tool (Alembic):
`create_all()` creates missing tables and never alters an existing one;
column additions were done once with `add_users_schema.py`.

**Tables (16, `infra/db/models.py`):** `analysis_case`, `document`,
`extraction_run`, `extracted_field`, `check_result`, `validated_dataset`,
`ratio_result`, `interpretation`, `audit_log`, `ai_analysis`, `app_user`,
`evaluation_campaign`, `evaluation_package`, `archive_entry`,
`case_comment`, `case_discussion_read` (the last three are created by
`create_all` at the first start after 27 Oct; nothing to migrate).

- No native PostgreSQL ENUM anywhere: status and role columns are plain
  strings, constrained by the constants and the state machine in
  `domain/entities.py`.
- `ratio_result`, `interpretation` and `check_result` exist but nothing
  writes to them: ratios, checks and interpretations are recomputed from the
  stored `validated_dataset` at each request. Exact and cheap, but a
  dashboard from a past date is not frozen if a formula changes later (a
  traceability point worth one sentence in the thesis).
- `validated_dataset.amounts` holds both years: `{"N": {...}, "N-1": {...}}`.
- `app_user` stores password **hashes** only (Werkzeug); the data browser
  never shows them.
- `evaluation_campaign` has the headline figures in their own columns (so
  they can be queried in SQL) and the full summary as JSON;
  `evaluation_package` has one row per package. Deleting a campaign deletes
  its packages (cascade) and leaves an audit entry.

---

## 7. What is genuinely open now

In order of importance for the thesis:

1. **The corpus.** One package (RP001) out of the 20–30 the dossier plans.
   Everything else is ready: add a folder per package with its statement and
   one annotation workbook (Administration → Campaigns, or directly in
   `data/corpus/`), then run a campaign. Worth confirming with your
   supervisor what size is acceptable.
2. **The baseline comparison (§11.1).** Run the corpus campaign with
   `STRUCTURER=rule_based` and again with `STRUCTURER=llm`, and compare
   field accuracy, ratio accuracy and silent false positives. This needs an
   API key and costs money (the cache prevents paying twice).
3. **The non-code exercises** (`LEARNING-PATH.md`): the failure typology
   (§19.3), whether the model's stated confidence predicts its errors, the
   R5 and AZ paragraphs, and the four limitations stated at the defence.
4. **The XI/XG sign** of the income statement operator column (see
   `EXTRACTION-PIPELINE.md`). CHK003 catches a mismatch with CJ when CJ is
   present.
5. **~~One missing guard~~ — fixed 27 Oct.** Approving and redrafting the
   AI commentary now require the case's analyst; running the analysis
   requires the case's analyst or its validator
   (`test_case_responsibility.py`).
5b. **Read with AI on the corpus.** Measuring the vision reader on the
   badly scanned packages (e.g. `ETAT_FINANCIER_TEST2.pdf`) would make a
   strong paragraph of §19; it needs an API key and costs money (cached).
6. **Small clean-up:** a few comments describe an earlier state; listed in
   `FILE-GUIDE.md` §9. In `checks.py`, CHK002 reports severity WARNING when
   it passes and BLOCKING when it fails (harmless, since a passed check
   blocks nothing, but inconsistent with the other checks).
7. **Week 8: writing.** No new feature. Anything unfinished becomes a stated
   limitation (§20).

---

## 8. Condensed chronological history

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
  created the `test` branch for your work, and reframed the remaining work as
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

- **13 – 22 Oct (this repository, dates from the files):** see §12 for
  the detail. In short: OCR tables for scanned PDFs (13–14 Oct); the AI
  commentary and "My cases" (item 4, 14–15 Oct); keyed items; French and
  English screens and the EB-Partners Audit look (15 Oct); sign-in, roles
  and notifications (item 5, 14–19 Oct); supervisor assignment, the
  supervisor dashboard charts and prompt `analysis-v3` on Claude Opus 5.5
  (19 Oct); week 7 indicators and the corpus campaign (20–21 Oct); the
  administrator role and the administration area (21–22 Oct).

---


## 09. Open decisions for you (and, where noted, your supervisor)

1. **Corpus size.** How many packages are enough for the evaluation chapter?
   Raise it with your supervisor (§7.1).
2. **Rule-based vs language model.** Whether to run the paid comparison of
   §7.2, on how many packages, within which budget (`MAX_COST_USD`).
3. **Which campaigns go in the thesis.** Campaigns can now be deleted; keep
   the ones you quote, and note the fingerprints of the files they read.
4. **Stored vs recomputed ratios** (§6): keep recomputation (and say so), or
   start writing `ratio_result` for a frozen history.

---

## 10. Fixes applied between 12 and 13 Oct 2026 (verified against live code)

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
   passing. Evidence: `tests/unit/test_document_structurer.py`.

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

The related finding on client4's scanned file (`ETAT_FINANCIER_TEST2.pdf`):
the OCR-to-table reconstruction and the REF fallback were added (§12), and
neither rescues that specific file, whose OCR word positions are too
scrambled (skew, resolution) for any column to survive. Kept as a documented
limitation (`EXTRACTION-PIPELINE.md`): exactly the kind of document the
language-model structurer is meant to handle, and where the analyst can key
the items in by hand.

---

## 11. Work done since 13 Oct 2026 (verified against the live code)

Grouped by subject; dates are the files' modification dates. Each item came
with its tests, written first.

**Scanned PDFs (13–14 Oct).** OCR word positions rebuilt into tables
(`pdf_loader.ocr_page_table`, `words_to_table`), the REF-column fallback in
`structure.py`, OCR in parallel (`OCR_WORKERS`). Tests:
`test_pdf_ocr_table.py`, `test_document_structurer.py`.

**Keyed items (14–15 Oct).** An analyst can enter an item the extractor
missed (`ValidationService.add_field`, `AddItemForm.jsx`); it is stored as
KEYED, audited, and every check reruns.

**AI commentary, item 4 (14–19 Oct).** `InsightService` +
`infra/llm/claude_analyst.py`: after an analysis, a model writes a
commentary on the validated figures, ratios, checks and N vs N-1, stored as
a DRAFT (`ai_analysis` table), edited and approved by the analyst, original
kept. Prompts `analysis_v1` → `v2` → `v3` (v3, 19 Oct: an advisor's
reading with a diagnosis and recommendations; the model is not given the
code's thresholds). On Claude Opus 5.5 with an effort setting
(`LLM_EFFORT`) and a cost cap. Tests: `test_add_field_and_insight.py`,
`test_intergration_api.py`, `test_opus_and_language.py`.

**My cases (item 4).** `GET /api/my-cases`, `MyCasesPage.jsx`: an analyst's
own cases; a supervisor's validation work.

**Languages and look (15 Oct).** Every screen in English and French
(`i18n/`), the AI commentary in the screen's language, the EB-Partners
Audit brand (`BrandMark.jsx`, `public/brand/`), shared status pills and
danger dialogs.

**Sign-in and roles, item 5 (14–19 Oct).** `app_user` table, hashed
passwords, signed session cookie, `api/auth.py` guards; every recorded name
comes from the session. Analysts prepare only their own cases; supervisors
validate and manage analysts. Submission (`SUBMITTED` state) before
validation, correction requests, the notification bell, the supervisor
dashboard (`SupervisorPage.jsx`, `RatioSpread.jsx`), account page. One-time
migration `add_users_schema.py`. Tests: `test_users_and_roles.py`,
`test_user_admin_rules.py`.

**Supervisor assignment (19 Oct).** The analyst picks the supervisor at
submission; only that supervisor is notified and may decide; only the
validator may send back or delete afterwards. Test:
`test_supervisor_my_cases.py`.

**Case management (15 Oct).** Edit and delete cases and documents
(`CaseService`) with the rules on validated results; a blocking overlay
during long operations with a time limit (`BusyOverlay.jsx`, 21 Oct).

**Week 7 (20–21 Oct).** Exercises 16–19 in `EvaluationService`; ratios
measured on their unrounded value (`RatioResult.exact` / `measured`) so that
rounding to one decimal does not distort the 1 % tolerance; the corpus
campaign (`services/corpus_campaign.py`) reading the annotation workbook
format of RP001; `evaluate_corpus.py`; exercise 20, campaigns stored in
`evaluation_campaign` / `evaluation_package` and read back through
`/api/evaluations`. Tests: `test_evaluation_metrics.py`,
`test_corpus_campaign.py`, `test_evaluation_api.py`,
`test_sql_evaluation_repository.py`.

**Administrator and administration area (21–22 Oct).** Third role, ADMIN,
created only with `create_admin.py`. Pages: Overview (the whole system),
Users (supervisors and analysts), Audit log (filters by who, action, kind of
element, dates, text; detail; CSV), Campaigns (corpus packages and files,
run a campaign, sensitivity test per package, trend charts, every package
item by item and ratio by ratio with the cause of each wrong ratio,
deleting a campaign), Data (read-only browser of every table, grouped and
explained). The audit now also records case creation, sign-out, the author
of an upload and every corpus and campaign action. Test:
`test_admin_area.py`.

---

## 12. Work done on 27 Oct 2026 (verified against the live code; 278 tests)

Six requests, each with its tests written first; all on the machine.

**Case responsibility.** Only the person a case is assigned to acts on it:
the analysis is run by the case's analyst or its validator
(`_require_analysis_actor`), the AI commentary is redrafted and approved by
the case's analyst only, and the dashboard receives `can_comment` so the
other users see why the buttons are missing. Test:
`test_case_responsibility.py`.

**Super administrator.** Fourth role, SUPERADMIN, exactly one, created only
with `create_superadmin.py` (`--reset`, `--show`). It does everything an
administrator does and is the only account that manages administrators
from the Users page; nobody manages it from the screens. Test:
`test_superadmin.py`.

**Archive.** Every deletion (case with everything under it, document,
account, campaign, corpus file or package) is first kept in `archive_entry`
by `services/archive_service.py`; corpus files are moved to `ARCHIVE_DIR`.
Administration → Archive lists them; Restore puts them back with the same
ids, Purge deletes them for good. Both audited. The user who deleted still
sees it as deleted. Test: `test_archive.py`.

**Export as PDF or Excel.** The dashboard offers both; the PDF
(`infra/export/pdf_report.py`, PyMuPDF) is in the screen's language and
includes the AI commentary only once approved. Test:
`test_export_formats.py`.

**Supervisors' discussion.** One thread per case (`case_comment`), open to
supervisors only, on the review page and the dashboard; unread messages
appear in the bell (`case_discussion_read`); every message is audited; the
thread is archived and restored with its case. Test:
`test_case_discussion.py`. Also fixed on the way: times were shown one hour
off (the backend stores UTC without a zone; `asDate()` now reads them as
UTC), and the header no longer overflows for administrators and
supervisors in French.

**Read with AI.** When the OCR cannot read a scan, the case's analyst
presses Read with AI on the Cases page; a confirmation recalls NFR-04 and
the cost. `infra/llm/claude_vision.py` sends the page images (at most
`VISION_MAX_PAGES`, default 12) to Claude with `prompts/vision_v1.md`; the
answer goes through the same schema check, retry, budget cap and cache as
the text structurer, and becomes an ordinary extraction run (engine
`LLM_VISION`) reviewed and validated as usual. Offered only when
`ANTHROPIC_API_KEY` is set. Tests: `test_vision_reading.py`,
`test_read_with_ai.py`.
