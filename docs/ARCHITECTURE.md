# Architecture

The layout follows dossier §17.2. This document explains *why* each boundary
is where it is: a structure you can justify is a structure you can defend at
the viva, and a structure you only inherited is one you will break the first
time you are in a hurry.

*Updated 22 October 2026 to the current code (sign-in and roles, AI
commentary, the administration area, the week 7 evaluation). For what each
individual file does, see `FILE-GUIDE.md`.*

```
backend/
  document_processing/     the original extractor (PDF, OCR, Excel, tables)
  app/
    __init__.py            composition root: the only file that picks adapters
    config.py              settings, read from .env
    api/                   Flask controllers: read the request, call, serialise
      routes.py              cases, documents, extraction, review, analysis
      auth.py                sign-in, roles, user accounts
      admin.py               the administration area (administrator only)
      serialisation.py       entity -> JSON, the frontend contract
      errors.py              exception -> HTTP status
    services/              orchestration: one service per use case family
    domain/                the accounting rules. Depends on nothing.
      value_objects.py       Amount, ItemCode
      entities.py            AnalysisCase ... User, EvaluationCampaign + lifecycle
      statement.py           code -> Amount, the only shape the rules see
      syscohada.py           the catalogue of codes in scope
      checks.py              CHK001..CHK005
      ratios/                one module per ratio + the engine
      interpretation/        templates and thresholds
      ports.py               the interfaces the domain requires
    infra/
      pdf/                   adapters over document_processing
      llm/                   rule-based structurer, Claude adapters, cache, prompts
      db/                    SQLAlchemy models + repositories, in-memory repositories
      export/                the Excel export and the PDF report
  wsgi.py                  python wsgi.py -> http://127.0.0.1:5000
frontend/                  React + Vite: pages, components, api/client.js, i18n
tests/
  unit/                    no network, no database server, no real PDF
  integration/             the whole chain over HTTP, with fake adapters
docs/
```

---

## The one rule

**Dependencies point inward.** `api` may import `services`; `services` may
import `domain`; `domain` imports nothing but the Python standard library.

That is not taste. It is requirement NFR-06, and
`tests/unit/domain/test_entities_and_purity.py` fails the build if it is ever
broken: it parses every module under `domain/` and looks at the imports
(`flask`, `sqlalchemy`, `pdfplumber`, `fitz`, `openpyxl`, `pytesseract`,
`anthropic`, `document_processing` and others are refused there).

### Why it is worth the discipline

1. **The sensitivity analysis of Part D.** Section 19.2 perturbs every item by
   three percentages and recomputes every ratio: several hundred complete
   computations. Because the domain needs no database and no network, a
   whole sensitivity test finishes in well under a second, which is why the
   administrator can run one from a button.
2. **Swapping the model for another.** `STRUCTURER=llm` in `.env` and nothing
   else changes. `backend/app/__init__.py` (`build_container`) is the only
   file that names a concrete adapter.
3. **The baseline comparison the thesis needs.** `RuleBasedStructurer` and
   `ClaudeStructurer` implement the same port, so a corpus campaign can be
   run with either and the two compared without a single `if`.

---

## How a request travels

```
browser (React page)
  -> frontend/src/api/client.js          one named function per endpoint
  -> Vite proxy /api -> Flask :5000
  -> api/auth.py  before every request:  signed in? right role? own case?
  -> api/routes.py or api/admin.py       read the request
  -> services/…                          orchestrate, audit
  -> domain/…                            decide (checks, ratios, transitions)
  -> infra/db/…                          store (SQL or in memory)
  <- api/serialisation.py                amounts leave as strings
```

An error never crosses a layer as a crash: `api/errors.py` turns a
`DomainError` into 409, a bad payload into 422, an unknown id into 404, a
missing sign-in into 401 and a wrong role into 403.

---

## Identity and roles

Sign-in is on by default (`AUTH_REQUIRED=true`). `POST /api/auth/login`
stores the user's id in Flask's signed session cookie (12 hours). From then
on, **every name the system records comes from the session, never from the
request**: a case's analyst, `corrected_by`, `validated_by`, `approved_by`
and every audit author. A browser cannot claim to be someone else.

| Guard (`api/auth.py`) | Who passes | Used for |
|---|---|---|
| `require_analyst` | analysts | create, upload, extract, correct, key, submit, reopen |
| `require_case_owner` | the analyst who owns the case | the same actions, on that case only |
| `require_supervisor` | supervisors | validate, send back, the cross-analyst overview, the case discussion |
| assignee / validator checks (`routes.py`) | the supervisor the case was submitted to / who validated it | validate, send back, delete |
| `_require_analysis_actor` (`routes.py`) | the case's analyst, or the supervisor who validated it | run the analysis |
| `require_analyst` + `require_case_owner` | the case's analyst | redraft and approve the AI commentary |
| `require_user_manager` | supervisors and the administrators | the Users page |
| `require_admin` | the administrator and the super administrator | everything under `/api/admin` (including the archive), corpus campaigns |

**Only the person a case is assigned to acts on it.** Every other supervisor
may read the case and write in its discussion, but every action is refused
(403); the dashboard receives `can_comment` so the screen hides what the
backend would refuse anyway.

The rules on accounts live in `services/user_service.py`, not in the routes:
the super administrator (exactly one, created by `create_superadmin.py`)
manages the administrators; an administrator manages supervisors and
analysts; a supervisor manages analysts only; nobody manages the super
administrator from the screens; roles are fixed once an account exists, the
last active supervisor is kept, and nobody deactivates themselves.

**Nothing is deleted outright.** Every service that deletes (cases,
documents, accounts, campaigns, corpus files) first hands the object to
`ArchiveService`, which encodes it as JSON in `archive_entry` (and moves a
corpus file to `ARCHIVE_DIR`). An administrator restores it with the same
ids, or purges it.

The dossier's separation of duties (§6.2: *the one who corrects is not the
one who validates*) is therefore enforced twice: by the case lifecycle
(nothing is validated that was not submitted) and by the roles (only an
analyst corrects, only a supervisor validates).

---

## Where each business rule lives

Keep this table beside you when you are unsure where to put something. The
question is never "where would this be convenient?" but "what kind of thing
is it?".

| Rule | Where it is enforced |
|---|---|
| BR-01 no ratio from unvalidated data | `AnalysisService.analyse` takes a `ValidatedDataset` and nothing else |
| BR-02 missing item → NOT_COMPUTABLE | `ratios/engine.py`, before the calculator is called |
| BR-03 zero denominator → NOT_COMPUTABLE | `ratios/engine.py`, catching `ZeroDivisionError` |
| BR-04 keep the items used | `RatioResult.items_used`, serialised and shown |
| BR-05..09 the checks | `domain/checks.py` |
| BR-10 a correction keeps the proposal | `ExtractedField.correct`; the repository never updates `proposed_amount` |
| BR-11 rerun every check | `ValidationService.correct_field` and `add_field` |
| BR-12 no validation while blocking | `ValidationService.validate`: refused unless the supervisor explicitly acknowledges the failing checks, which is recorded |
| BR-13 no free text as a conclusion | `interpretation/templates.py` (three templates, no fourth path); the AI commentary is a separate DRAFT until an analyst approves it (`InsightService`) |
| BR-14 no judgement without a reference | `THRESHOLDS`; an absent threshold produces a factual sentence |
| BR-15 rounding | `value_objects.py`, applied once in the engine |
| Case lifecycle (§15) | `ALLOWED_TRANSITIONS` in `domain/entities.py` |
| Separation of duties (§6.2) | the lifecycle (SUBMITTED before VALIDATED) + the role guards in `api/auth.py` |
| NFR-04 figures only to the model | `InsightService.build_payload`: no client name, no year, no document |
| NFR-08 never pay twice, capped budget | `infra/llm/cache.py` (by fingerprint) and `max_cost_usd` in each Claude adapter |
| FR-22 traceability | the audit log, written by every service and the admin routes |

---

## The patterns, and what each one actually buys

Dossier §13 lists five. Here is where each one is, and the concrete thing it
gives you. A pattern with no payoff is decoration.

**Strategy**: `domain/ratios/`, one module per ratio.
Adding R6 means adding a file and one line in `engine.py::_MODULES`. The
engine never changes, so the rules it enforces (BR-02, BR-03, BR-04, BR-15)
apply automatically to every ratio you will ever add.

**Adapter**: `infra/pdf/readers.py`, `infra/llm/`.
`document_processing` became usable by the rest of the system without one
line changed inside it, which is the test of a good adapter: the thing being
adapted does not know it has been adapted. The same holds for the two Claude
adapters, one that reads figures (`claude_structurer.py`) and one that only
comments on validated figures (`claude_analyst.py`).

**Repository**: `infra/db/repositories.py` and `infra/db/memory.py`.
Two implementations of the same ports. Every service test runs against the
in-memory one, in microseconds, leaving nothing behind; the SQL ones have
their own tests against a real SQLite database
(`tests/unit/infra/test_sql_*`), because two adapters can agree on method
names and still disagree on behaviour.

**Template method**: `ExtractionService.run_extraction`.
The sequence detect → extract → structure → validate → check → persist is
fixed and matches UC-03 step for step. Only the steps vary.

**Value object**: `Amount`, `ItemCode`.
`Amount` refuses a float. That single refusal is why the equilibrium check can
test equality to the franc: with floats, `0.1 + 0.2 != 0.3`, and on a balance
sheet of several billion that inexactness becomes visible.

---

## Adding things: the recipes

**A ratio.** Create `domain/ratios/r06_something.py` with a `calculate`
function and a `DEFINITION`; add the module to `_MODULES` in `engine.py`; add
a threshold in `interpretation/templates.py` *if you have a citable source*;
add its name in `frontend/src/i18n/en.js` and `fr.js`; write the test.

**A check.** Write the function in `domain/checks.py`, add it to `REGISTRY`,
choose its severity deliberately (BLOCKING stops a validation, so it must be
a rule that admits no judgement), add its label in both language files.

**An endpoint.** Add it to `api/routes.py` (or `api/admin.py` for the
administrator), with the right guard first, and keep it to three lines of
work: read the request, call a service, serialise. Add the matching function
to `frontend/src/api/client.js`. If an `if` about accounting appears in a
route, it belongs in the domain.

**An adapter** (another model provider, another OCR engine). Write a class
with the methods the port declares (no inheritance needed, `Protocol`
matches on shape) and wire it in `app/__init__.py::build_container`.

**A table.** Add the row class to `infra/db/models.py` and its repository.
`create_all` creates a *new* table on the next start; a new *column* on an
existing table needs a one-time script (see `add_users_schema.py`) or
Alembic.

**A screen text.** Add the key to both `en.js` and `fr.js`; use `t('key')`.

---

## What is deliberately not here

- **Background jobs.** Extraction and the AI commentary run inside the
  request. The interface covers the wait (`BusyOverlay.jsx`) with a time
  limit. The day OCR on a 40-page scan exceeds that, one route changes and
  nothing below it notices.
- **Migrations.** `create_all` is enough for a prototype. See the end of
  `DATA-MODEL-REVIEW.md` for when it stops being enough.
- **Deployment.** Explicitly out of scope (§3.3, §20.4): development servers,
  one CORS origin, no HTTPS. Say so at the defence rather than let a jury
  discover it.
- **Stored ratio results.** The `ratio_result`, `interpretation` and
  `check_result` tables exist, but ratios and checks are recomputed from the
  stored validated dataset at each request. Recomputation is exact and
  cheap; the cost is that a dashboard from last month is not frozen if a
  formula changes later.