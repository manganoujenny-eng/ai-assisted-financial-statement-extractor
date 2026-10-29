# File guide: what every file does

*Written 22 October 2026 by reading every file of the project; updated 27
October 2026 for the super administrator, the archive, the PDF export, the
supervisors' discussion, case responsibility and "Read with AI". Folders that
are generated or installed (`.venv/`, `node_modules/`, `__pycache__/`,
`frontend/dist/`, `.idea/`) are not listed.*

How to read it: the project is a chain. A **document** goes in through the
*frontend*, is read by **document_processing**, structured and checked by
the *backend services* using the rules of the **domain**, stored by
**infra/db**, and shown back to the analyst, the supervisor and the
administrator. Each section below is one link of that chain.

---

## 1. Project root

| File | What it does |
|---|---|
| `README.md` | Front page: what the system does, roles, how to install and run it, the settings, the documentation index. |
| `.env` | **Your** settings and secrets (database, API key, secret key). Git-ignored, never committed, never shared. |
| `.env.example` | The list of every setting with safe example values. Copy it to `.env`. |
| `.gitignore` | What Git must never track: `.env`, the virtual environment, caches, `node_modules`, uploads, the corpus and test documents (client data), the archived files, the SQLite file, the model cache. |
| `requirements.txt` | The Python packages and their exact versions (`pip install -r requirements.txt`): Flask, SQLAlchemy, psycopg, pdfplumber, PyMuPDF, pytesseract, openpyxl, anthropic, pytest, python-dotenv… |
| `pyproject.toml` | Settings for the tools: pytest looks in `tests/` and can import `backend/` and `tests/` (that is why `from app…` works in a test), and the ruff linter rules. |

---

## 2. `backend/`: scripts at the top level

| File | What it does |
|---|---|
| `wsgi.py` | **Starts the backend**: `cd backend` then `python wsgi.py` → `http://127.0.0.1:5000`. Calls `create_app()`. |
| `create_superadmin.py` | Creates the **super administrator**, once (refused if one exists); `--reset` gives it a new temporary password, `--show` says who it is. The only way the super administrator is ever created or changed. Audited as `create_superadmin.py`. |
| `create_admin.py` | Fallback for **administrator** accounts (the super administrator normally manages them on the Users page): create, `--reset` (new temporary password), `--deactivate`, `--activate`, `--list`. Every change goes to the audit log as `create_admin.py`. |
| `evaluate_corpus.py` | Runs a **corpus campaign** (week 7) from the command line: extracts every package of `data/corpus/`, compares with the hand readings, prints the results and stores the campaign in the database. `--note`, `--json` (also writes `data/corpus/_results/campaign_….json`), or another corpus folder. Same code as the Campaigns page. |
| `add_users_schema.py` | One-time migration from when sign-in was added: created the `app_user` table, the first supervisor, and an analyst account for every analyst name already on a case. Already run; kept for the record. |
| `reset_stranded_cases.py` | One-time repair from an earlier schema change: puts every case that has no extraction run back to CREATED so it can be extracted again. Already run; kept for the record. |
| `test_loader.py` | Your original test harness for `document_processing`: runs the seven pipeline stages on the PKG001 test files, prints each stage and writes the JSON result to `data/extracted/`. Not part of the application or of pytest. |

---

## 3. `backend/document_processing/`: the original extractor

Your own code from weeks 1–3, reused by the application through
`infra/pdf/readers.py` without being rewritten. Detail in
`EXTRACTION-PIPELINE.md`.

| File | What it does |
|---|---|
| `document_loader.py` | Entry point: detects the type from the extension and opens the file with the PDF or the Excel loader. Anything else (e.g. `.docx`) is refused. |
| `pdf_loader.py` | Everything PDF: opens it (PyMuPDF), decides native vs scanned, extracts the text, extracts the tables (pdfplumber), and for scanned pages runs **OCR** (Tesseract) in parallel (`OCR_WORKERS`) and rebuilds a table from the word positions (`ocr_page_table`, `words_to_table`). `read_pdf()` does it all; `probe_pdf()` only counts pages and detects a scan. |
| `excel_loader.py` | Opens a workbook with `data_only=True` (formula cells give their computed value) and turns each sheet into text and a table of rows. |
| `normarlize.py` | Numbers: turns `"6 746 235 223"` or `"-"` into a number, merges the header rows, and decides which columns hold money (by header keywords such as NET, BRUT, EXERCICE, with a content-based cross-check). The spelling of the file name is intentional. |
| `structure.py` | Turns a table into SYSCOHADA line items: finds the REF columns (or the column where the two-letter codes recur when OCR lost the word "REF"), splits ACTIF/PASSIF sides, detects how many header rows there are, reads the year N and N-1 values by position, and indexes everything by code. |
| `output_writer.py` | Builds and saves the JSON result used by `test_loader.py` (`data/extracted/`). |

---

## 4. `backend/app/`: the application

### 4.1 Wiring

| File | What it does |
|---|---|
| `__init__.py` | **The composition root.** `build_container()` chooses every concrete piece: SQL or in-memory storage, rule-based or Claude structurer, the "Read with AI" reader (only with an API key), AI commentary on or off, the archive and the discussion repositories, and wires the services. `create_app()` builds the Flask app (session cookie, upload limit, error handlers, the CORS header for the dev frontend). The only file that knows which adapter is used. |
| `config.py` | Reads the settings from `.env` into a `Config` object (storage, database URL, structurer, model, prices, effort, budget, AI commentary, "Read with AI" page limit, upload folder and size, archive folder, sign-in, secret key, CORS origin). |

### 4.2 `api/`: the HTTP layer (thin on purpose)

| File | What it does |
|---|---|
| `__init__.py` | Registers the blueprints (`routes`, `auth`, `users`, `admin`) and the sign-in check that runs before every request. |
| `routes.py` | The main endpoints, each reading the request, calling a service and returning JSON: health (also says whether "Read with AI" is available); cases (create, list, edit, delete); documents (upload, delete, serve the file, Excel preview); extraction (`{"engine": "vision"}` = Read with AI); fields (list, correct, add a keyed item); submission, validation, correction request, reopen; history; supervisors list; notifications (including unread discussions); analysis (only the case's analyst or the supervisor it is assigned to: `_require_analysis_actor`), AI commentary (regenerate, approve: the case's analyst only); the case discussion (supervisors); supervisor overview; my cases; export (`?format=xlsx` or `pdf`, `&lang=`); evaluations (sensitivity, corpus campaign, list, read). |
| `auth.py` | Sign-in (`/api/auth/login`, `logout`, `me`, change my name, change my password), the users endpoints (`/api/users`; only the super administrator may manage administrators), and the guards: `require_login`, `require_analyst`, `require_supervisor`, `require_admin` (administrator or super administrator), `require_user_manager`, `require_case_owner`. `actor()` gives the signed-in person's name, the only name ever recorded. |
| `admin.py` | The administration area, administrator only: overview, audit log (filters, pages, CSV), corpus (packages and files; deleting archives them), sensitivity test on a package, delete a campaign (archived), the **archive** (list, restore, purge), read-only database browser (passwords and archive payloads never leave). |
| `serialisation.py` | Turns entities into the JSON the frontend reads: **the contract** in one place. Amounts leave as strings, never as floats. |
| `errors.py` | Turns an exception into the right HTTP answer: business rule → 409, bad value or failed extraction → 422, unknown id → 404, sign-in failed → 401, anything unexpected → 500 without leaking details. |

### 4.3 `services/`: orchestration (no accounting rule here)

| File | What it does |
|---|---|
| `__init__.py` | Package marker with the layer's rule. |
| `extraction_service.py` | **Runs an extraction** over all the documents of a case: read (PDF/Excel adapter), structure (rule-based or Claude; or, for "Read with AI", the PDFs go straight to the vision reader), validate each proposed item against the schema (rejected ones are recorded), run the checks, store the run, its fields and the audit entry. Records the cost and the failure reason. |
| `validation_service.py` | **Review and validation**: correct a field (the proposal is kept), add a keyed item, submit to a supervisor, validate (refused while a blocking check fails unless acknowledged), send back with a correction request, reopen. Re-runs every check after each change. |
| `analysis_service.py` | Computes the five ratios and their template interpretations **from a validated dataset only** (BR-01). No model call. |
| `insight_service.py` | **AI commentary**: builds the payload (validated figures, ratios, checks, N vs N-1, never the client's name), asks the model in the screen's language, stores the answer as a DRAFT, and records the analyst's approval (with the edited text, while keeping the original). |
| `case_service.py` | Editing and deleting cases and documents, with the rules: an analyst deletes what has no validated result; a supervisor deletes only ANALYSED cases they validated; a deleted document is detached from the history cleanly. Every deletion is first copied to the archive (with the case's discussion). |
| `user_service.py` | Accounts: create, rename, reset password, deactivate, reactivate, delete (archived). Passwords hashed (Werkzeug). The rules on who manages whom (the super administrator manages administrators; nobody manages the super administrator), and the protections (last active supervisor, no self-deactivation, no role change). |
| `archive_service.py` | **The archive**: before anything is deleted (case with all its runs, datasets, commentaries and messages; document; account; campaign; corpus file or package) it is encoded to JSON and kept, and corpus files are moved to `ARCHIVE_DIR`. `restore()` puts it back with the same ids; `purge()` deletes it for good. Both audited. |
| `overview_service.py` | The supervisor's cross-analyst view: work queues, each analyst's activity, ratio statistics across all current validated results, the checks that fail most. Read-only. |
| `evaluation_service.py` | **Part D measurements**: the sensitivity matrix (perturb each item by 1/5/10 %, recompute, did a check notice?), item criticality, interception rate, and the four indicators of week 7: silent false positives, field accuracy, ratio accuracy (within 1 %), amplification coefficient. |
| `corpus_campaign.py` | **The week 7 campaign** over the corpus folder: reads each annotation workbook, rejects a hand reading that fails a blocking check, extracts the package, measures it item by item and ratio by ratio, and produces the stored campaign (with every field, ratio and check, and the fingerprint of every file). |

### 4.4 `domain/`: the accounting rules (depends on nothing)

| File | What it does |
|---|---|
| `__init__.py` | Package marker with the purity rule (NFR-06). |
| `value_objects.py` | `Amount` (exact Decimal in CFA francs, refuses floats, rounding rules of BR-15) and `ItemCode` (a valid two-letter SYSCOHADA code). |
| `statement.py` | `FinancialStatement`: code → Amount for one year. The only shape the checks and ratios ever receive. |
| `syscohada.py` | The catalogue of codes in scope, with labels, and `REQUIRED_CODES` (the 11 items the ratios and checks need). |
| `entities.py` | The objects with identity and their rules: `AnalysisCase` and its lifecycle (`ALLOWED_TRANSITIONS`), `SourceDocument`, `ExtractionRun`, `ExtractedField` (proposed / corrected / validated / keyed), `ExtractionRejection`, `ValidatedDataset` (years N and N-1), `AuditEntry`, `AiAnalysis` (draft / approved / failed), `User` and the four roles (analyst, supervisor, administrator, super administrator), `EvaluationCampaign` (corpus / sensitivity), `ArchiveEntry`, `CaseComment` (a discussion message, at most 2000 characters), `DomainError`. |
| `checks.py` | The five consistency checks CHK001–CHK005, each reporting passed or failed, severity, the gap in francs and a message; `run_all()` runs the registry. |
| `ports.py` | The interfaces the domain needs from outside (repositories, document reader, structurer, commentary writer, audit log, users, campaigns, archive, discussion messages). Infrastructure implements them. |
| `ratios/__init__.py` | Exposes the engine (`compute_all`, `REGISTRY`). |
| `ratios/definition.py` | `RatioDefinition`: code, name, family, formula, required items, unit, reading direction, calculator. |
| `ratios/engine.py` | Runs every ratio and enforces the shared rules once: missing item or zero denominator → NOT_COMPUTABLE with its reason, the items used are kept, rounding. Also keeps the exact (unrounded) value used by the evaluation. |
| `ratios/r01_current_ratio.py` | R1 = (BK + BT) / (DP + DT). |
| `ratios/r02_equity_ratio.py` | R2 = CP / (CP + DD). |
| `ratios/r03_stable_funding.py` | R3 = (CP + DD) / AZ, with AZ net (consistent with BZ). |
| `ratios/r04_net_margin.py` | R4 = XI / XB × 100. |
| `ratios/r05_return_on_equity.py` | R5 = XI / CP × 100; negative equity → not computable (your design decision). |
| `interpretation/__init__.py` | `interpret()`: one ratio result → one sentence from a template, with the threshold applied. |
| `interpretation/templates.py` | The three templates (not computable / factual, no reference / compared to a threshold) and the thresholds: R1 = 1.0 and R3 = 1.0 with their sources; R2, R4, R5 deliberately none. |

### 4.5 `infra/`: everything the domain refuses to know

| File | What it does |
|---|---|
| `__init__.py` | Package marker. |
| `pdf/readers.py` | `PdfReader` and `ExcelReader`: adapters that call `document_processing` and return the `RawDocument` the services expect (text, tables, page count, scanned or not). |
| `llm/rule_based.py` | `RuleBasedStructurer`: the default structurer. Uses `structure.py` to turn the tables into proposed items. Free, offline, reproducible: the thesis baseline. |
| `llm/claude_structurer.py` | `ClaudeStructurer`: Claude reads the document text and proposes the items (`STRUCTURER=llm`). Strict schema check, one retry, cost tracking, budget cap, cache. |
| `llm/claude_vision.py` | `ClaudeVisionStructurer`: **Read with AI**. Renders each PDF page as a PNG image (long side 1568 px, at most `VISION_MAX_PAGES`) and asks Claude to read the items off the images. Inherits the structurer's schema check, one retry, cost, budget cap and cache (keyed on the page images). Engine `LLM_VISION`. |
| `llm/claude_analyst.py` | `ClaudeAnalyst`: Claude writes the commentary **about** validated figures (never proposes a figure). Checks the JSON it returns, one retry, cost and budget, language from the screen. |
| `llm/cache.py` | Stores model answers on disk by fingerprint (document + prompt version + model), so the same call is never paid twice. |
| `llm/prompts/v1.md` | The structurer's prompt (version 1): the codes to extract, the rules (NET column, dashes, no guessing) and the JSON schema. |
| `llm/prompts/vision_v1.md` | The Read with AI prompt: the same codes and rules as `v1.md`, but reading page images (`source_page` = image number). |
| `llm/prompts/analysis_v1.md`, `analysis_v2.md`, `analysis_v3.md` | The commentary prompts. Kept side by side so versions stay comparable; **v3** is in use (an advisor's reading: diagnosis, what each ratio means, recommendations, points of attention). |
| `db/models.py` | The SQLAlchemy tables (16): `analysis_case`, `document`, `extraction_run`, `extracted_field`, `check_result`, `validated_dataset`, `ratio_result`, `interpretation`, `audit_log`, `ai_analysis`, `app_user`, `evaluation_campaign`, `evaluation_package`, `archive_entry`, `case_comment`, `case_discussion_read`. |
| `db/repositories.py` | The SQL repositories: translate rows ↔ entities for cases, documents, extractions, datasets, audit log (with search and filters), AI analyses, users, campaigns, archive, discussion messages and who has read them. |
| `db/memory.py` | The same repositories in memory (`STORAGE=memory`, and the tests). |
| `db/session.py` | Database engine and session; SQLite file `data/prototype.db` when `DATABASE_URL` is empty; `create_schema()` creates missing tables. |
| `export/spreadsheet.py` | The Excel export of an analysis (FR-19): case information, the ratios with their interpretation, the checks, and the validated dataset on a second sheet. |
| `export/pdf_report.py` | The **PDF report** of an analysis (PyMuPDF), in English or French: case, ratios with interpretation, checks, N vs N-1, the approved AI commentary when there is one, the validated items, "Page x / y" footer. |
| `db/__init__.py`, `export/__init__.py`, `llm/__init__.py`, `pdf/__init__.py` | Empty package markers. |

---

## 5. `frontend/`: the interface (React + Vite)

### 5.1 Top level

| File | What it does |
|---|---|
| `package.json` | The frontend's packages (React, React Router, Vite) and its commands: `npm run dev`, `npm run build`. |
| `package-lock.json` | The exact installed versions (generated by npm; do not edit). |
| `vite.config.js` | Dev server on port 5173 and the **proxy**: every `/api/…` call goes to Flask on port 5000. |
| `index.html` | The single HTML page: title, favicon, the Poppins and Roboto fonts, and the `root` element React fills. |
| `public/brand/eb-audit-symbol.png` | The EB-Partners Audit symbol (header, login page, favicon). |

### 5.2 `src/`

| File | What it does |
|---|---|
| `main.jsx` | Starts React: language provider, router, the stylesheet, then `App`. |
| `App.jsx` | Checks who is signed in (login page otherwise), draws the header (brand, menus by role, language, notifications, account, sign out) and chooses the pages: the administrator gets the administration routes, analysts and supervisors the case routes. |
| `api/client.js` | **The only place that calls the backend.** One named function per endpoint; handles errors, sends the screen's language, builds the download links (document, Excel or PDF export, audit CSV), says who is an administrator / super administrator, and sets the time limits of long operations (extraction, Read with AI, AI commentary). |
| `styles/app.css` | All the styling: colour tokens, layout, header, cards, tables, pills, review screen, dashboard, charts, dialogs, administration pages, phone and laptop sizes. |
| `i18n/index.jsx` | The language system: `t('key')`, plurals, number and date formatting in the chosen language, remembered in the browser. `asDate()` reads the backend's times as UTC, so they show in local time. |
| `i18n/en.js`, `i18n/fr.js` | Every visible text, in English and in French, with the same keys. |
| `i18n/interpretation.js` | Rebuilds the backend's template interpretation sentence in the screen's language, from the template and threshold the backend sends. |

### 5.3 `src/pages/`

| File | Who | What it does |
|---|---|---|
| `LoginPage.jsx` | everyone | Sign-in form beside the EB-Partners Audit panel. |
| `CasesPage.jsx` | analyst, supervisor | The list of cases. An analyst creates a case, uploads documents, runs or retries the extraction, **Read with AI** for a PDF (after a confirmation), edits or deletes; everyone opens the review or the dashboard. |
| `ReviewPage.jsx` | analyst, supervisor | **The review workspace**: source document (PDF viewer or Excel viewer) beside the extracted items; correct an item, key a missing one, see the history and the checks; the analyst submits to a chosen supervisor, the supervisor validates or sends back; supervisors see the case's discussion. |
| `DashboardPage.jsx` | analyst, supervisor | The analysis: the five ratios with their interpretation and inputs, the checks, year N vs N-1 (charts and table), the AI commentary panel (actions only for the person the case is assigned to), export as **PDF** or **Excel**, and the discussion for supervisors. |
| `MyCasesPage.jsx` | analyst, supervisor | An analyst's own cases with where each stands; a supervisor's validation work (waiting for them, validated by them). |
| `SupervisorPage.jsx` | supervisor | Every analyst's work: queues, activity, extraction quality, ratio spread across all validated cases, the checks that fail most. |
| `UsersPage.jsx` | supervisor, administrator | Accounts: add, rename, reset password, deactivate, reactivate, delete (analysts for a supervisor; supervisors and analysts for an administrator; administrators too for the super administrator). |
| `AccountPage.jsx` | everyone | My name and my password. |
| `AdminOverviewPage.jsx` | administrator | The whole system on one page: key figures, cases along the workflow, accounts, extractions and AI cost, latest campaign, settings (secrets shown only as set / not set), latest activity. |
| `AdminAuditPage.jsx` | administrator | The audit log: who did what, when, on what; filters, details, CSV download. |
| `AdminCampaignsPage.jsx` | administrator | Evaluation: manage the corpus packages and files, run a corpus campaign, run a sensitivity test, charts of all campaigns, stored campaigns (open, delete). |
| `AdminArchivePage.jsx` | administrator | **The archive**: everything deleted, by kind, who deleted it and when, with Restore and Purge (confirmed). |
| `AdminDataPage.jsx` | administrator | Read-only database browser: the tables grouped by theme, their rows with search and pages. |

### 5.4 `src/components/`

| File | What it does |
|---|---|
| `BrandMark.jsx` | The EB-Partners Audit symbol and name. |
| `StatusPill.jsx` | One coloured label per status, the same everywhere. |
| `NotificationBell.jsx` | The bell: cases waiting for this supervisor, cases sent back to this analyst, and unread discussion messages. Refreshes every 30 seconds and when a discussion is read. |
| `CaseDiscussion.jsx` | The supervisors' thread on one case: messages oldest first, send with Ctrl+Enter, refreshes every 20 seconds, marks the thread read. |
| `BusyOverlay.jsx` | Covers the screen during an extraction or an AI commentary, shows the time spent against the limit, and turns into an error with "Reload" if the limit passes. |
| `DangerDialog.jsx` | The red confirmation dialog for hard-to-undo actions (delete, validate despite failing checks, delete a campaign). |
| `ChecksPanel.jsx` | The consistency checks of an extraction, blocking failures first, with their gap and message. |
| `AddItemForm.jsx` | Keys in an item the extractor missed (recorded as KEYED). |
| `ExcelSourceViewer.jsx` | Shows an uploaded Excel workbook (sheet tabs, rows and columns) beside the items. |
| `YearComparisonChart.jsx` | Year N vs N-1 bars, per ratio and for the key amounts. |
| `RatioSpread.jsx` | Supervisor dashboard: one strip per ratio, a dot per validated case, the median and the documented reference. |
| `AiCommentaryPanel.jsx` | The AI commentary: draft (editable, approve), approved (read-only, by whom), failed (reason, try again). |
| `AdminBits.jsx` | Small shared pieces of the admin pages: stat tile, pager, percentage and file-size formats, audit texts. |
| `CampaignTrend.jsx` | Charts of all corpus campaigns: field and ratio accuracy over time, silent false positives per campaign. |
| `CampaignDetail.jsx` | One campaign opened: headline figures and their meaning, each package item by item and ratio by ratio, checks, the sensitivity matrix, criticality bars, delete. |

---

## 6. `tests/`: pytest (278 tests)

`pytest` from the project folder runs them all. No test calls a real model
or needs PostgreSQL; the SQL tests use a temporary SQLite database.

| File | Tests |
|---|---|
| `conftest.py` | Shared fixtures: `BALANCED`, a hand-made statement that balances and passes every check, and the app built with sign-in off. |
| **unit/domain/** | |
| `test_value_objects.py` | `Amount` and `ItemCode`: exactness, refusal of floats, rounding, code format. |
| `test_checks.py` | CHK001–CHK005, passing and failing, gaps and messages. |
| `test_ratios.py` | The engine and R1–R5, values computed by hand, not-computable cases. |
| `test_entities_and_purity.py` | The case lifecycle, the correction rules, and **the architecture test** (the domain imports nothing external). |
| **unit/services/** | |
| `test_validation_service.py` | Reopen, acknowledgement of failing checks, submit → send back → submit, no validation without submission. |
| `test_add_field_and_insight.py` | Keyed items and the AI commentary service (payload without client data, draft, approval, failure). |
| **unit/infra/** | |
| `test_memory_repositories.py` | The in-memory repositories return the latest validated dataset, like the SQL ones. |
| `test_sql_document_repository.py` | A document's page count and scan flag really reach the database. |
| `test_sql_evaluation_repository.py` | Campaigns stored, read back, listed newest first, deleted with their packages. |
| **unit/** | |
| `test_document_structurer.py` | `structure.py` on real-shaped tables (header not on the first row, REF lost by OCR). |
| `test_pdf_ocr_table.py` | Rebuilding a table from OCR word positions. |
| `test_extraction_service.py` | Items the schema rejects are recorded, not lost. |
| `test_claude_structurer.py` | The Claude structurer with a fake API: parsing, one retry after a bad answer. |
| `test_vision_reading.py` | Read with AI with a fake API: page images sent, page limit, never paid twice, one retry. |
| `test_opus_and_language.py` | What is sent to the model (model, effort) and how the answer is read; the commentary language. |
| `test_evaluation.py` | The sensitivity matrix and criticality. |
| `test_evaluation_metrics.py` | Week 7 indicators: silent false positives, field and ratio accuracy, amplification. |
| `test_corpus_campaign.py` | The corpus campaign on small annotation workbooks with a fake extractor. |
| **integration/** | |
| `test_api_end_to_end.py` | The whole chain over HTTP: upload → extract → correct → validate → analyse → export, with fake reader and structurer. |
| `test_intergration_api.py` | Keyed items and the AI commentary through the API. |
| `test_users_and_roles.py` | Sign-in, roles, who may do what, user management, supervisor overview. |
| `test_user_admin_rules.py` | Who manages whom. |
| `test_supervisor_my_cases.py` | Assigning a submission to one supervisor; My cases for a supervisor. |
| `test_evaluation_api.py` | The evaluation routes store and read back campaigns. |
| `test_admin_area.py` | The administrator: users, audit log, overview, corpus, database browser, sensitivity test, deleting a campaign, refused everything on cases. |
| `test_superadmin.py` | The super administrator: created once, manages administrators, cannot be managed from the screens. |
| `test_archive.py` | Every kind of deletion is archived, restored with the same ids, or purged (memory and SQL). |
| `test_export_formats.py` | Export as Excel or PDF, in English or French; an unknown format is refused. |
| `test_case_responsibility.py` | Only the person a case is assigned to acts on it: the analysis is run by the case's analyst or its validator; only the owner drafts the AI commentary again and approves it; the dashboard says who may act. |
| `test_case_discussion.py` | The supervisors' discussion: supervisors only, no empty or over-long message, unread messages in the bell until the thread is opened, archived and restored with the case, every message audited (memory and SQL). |
| `test_read_with_ai.py` | Read with AI through the API: only the case's analyst, needs the model and a PDF, the run is an ordinary LLM_VISION run. |

---

## 7. `data/`

Client documents live here, so most of this folder is git-ignored.

| Folder | What it holds |
|---|---|
| `test_documents/PKG001/` | Your first test package (the native PDF, the scanned PDF, the Excel version, and the Word file used to prove `.docx` is refused). Used by `test_loader.py`. |
| `extracted/` | The JSON results written by `test_loader.py`. |
| `uploads/` | The files uploaded through the application (`UPLOAD_DIR`). |
| `corpus/RP001/…` | The evaluation corpus: one folder per package with its statement(s) and **one** annotation workbook (`CORPUS_DIR`). |
| `corpus/_results/` | JSON copies of campaigns run with `evaluate_corpus.py --json`. |
| `llm_cache/` | Cached model answers, one JSON file per fingerprint (`LLM_CACHE_DIR`). |
| `archive/` | Corpus files that were deleted, kept until restored or purged (`ARCHIVE_DIR`). |
| `prototype.db` | The SQLite database, when `STORAGE=sql` without `DATABASE_URL`. |

---

## 8. `docs/`

| File | What it holds |
|---|---|
| `PROJECT-STATE.md` | What is done, what is open, the history and the working agreement. |
| `FILE-GUIDE.md` | This file. |
| `ARCHITECTURE.md` | The layers, the dependency rule, how a request travels, roles, where each rule lives, the patterns, how to add things. |
| `EXTRACTION-PIPELINE.md` | How `document_processing` reads a statement, its design decisions and known limitations. |
| `DATA-MODEL-REVIEW.md` | The review of your original SQL schema, and the tables added since. |
| `LEARNING-PATH.md` | The supervisor's original plan and exercise list (weeks 2–8). |

---

## 9. Comments in the code that are now out of date

The code behaves correctly; these comments describe an earlier state. Fix
them when you next touch the file (wording only, no behaviour change):

| File | Says | Now |
|---|---|---|
| `frontend/src/pages/AccountPage.jsx` (top) | supervisor accounts come from `create_supervisor.py` | the administrator creates supervisors on Users; only administrators use a script (`create_admin.py`) |
| `frontend/src/pages/MyCasesPage.jsx` (top) | "any supervisor may validate it" | only the supervisor it was submitted to |
| `backend/app/api/routes.py` (`notifications`, `my_cases` docstrings) | every SUBMITTED case / no assignment | the cases assigned to that supervisor |
| `tests/integration/test_user_admin_rules.py` (top) | supervisors are created with `create_supervisor.py` | by the administrator, on screen |
| `backend/reset_stranded_cases.py` (top) | companion of `drop_old_extraction_tables.py` | that script is no longer in the project |
| `backend/app/domain/__init__.py` | the purity test is `test_domain_is_pure.py` | it is `test_entities_and_purity.py` |
| `backend/app/infra/db/models.py` (`analysis_case.analyst`) | run `add_ai_analysis_schema.py` once | that script was already run and is no longer in the project |
| `backend/app/domain/checks.py`, `ratios/__init__.py`, `r03`–`r05`, `claude_structurer.py`, `prompts/v1.md` | "your exercise" / "draft skeleton" | done |
| `backend/app/services/validation_service.py` (top) | "access control proper is out of scope" | sign-in and roles exist (`api/auth.py`) |