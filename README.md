# SYSCOHADA Financial Statement Extraction and Analysis

A prototype that reads SYSCOHADA financial statements (balance sheet and
income statement, as PDF or Excel), extracts the line items, lets an analyst
check and correct them beside the source document, has a supervisor validate
them, and only then computes five financial ratios with a rule-based,
auditable interpretation. A language model can add a written commentary,
which an analyst must approve before it counts.

Built for an internship and thesis project at **EB Partners / EB Audit &
Advisory, Douala**, following the supervisor's *Scoping and Design Dossier
v2.0* (cited in the code as "the dossier", with its section numbers).

> **Research question (dossier):** to what extent can AI-assisted
> extraction, deterministic ratio computation and human validation reliably
> turn a SYSCOHADA reporting package into usable financial indicators, and
> how does an extraction error propagate to those indicators?

---

## What the system does, from document to result

1. **Create a case**: a client and a fiscal year (analyst).
2. **Upload** the statement(s): PDF (native or scanned) or Excel. Each file
   is fingerprinted (SHA-256) so the same bytes are never processed twice.
3. **Extract**: the rule-based structurer (default, free, deterministic)
   reads the tables. Scanned pages go through OCR (Tesseract). A
   language-model structurer (Claude) can be switched on instead.
4. **Review and correct**: the source document on the left, the extracted
   items on the right. Every correction keeps the original proposal. An item
   the extractor missed can be keyed in by hand. The five consistency
   checks re-run after each change.
5. **Submit** the case to a chosen supervisor.
6. **Validate or send back**: the supervisor validates (refused while a
   blocking check fails, unless explicitly acknowledged) or sends the case
   back with a correction request.
7. **Analyse**: the five ratios are computed **from validated data only**,
   each with a template interpretation and, when the document has the
   column, a comparison with the previous year (N-1).
8. **AI commentary** (optional): right after validation, a model writes a
   commentary on the validated figures, in the screen's language. It stays
   a draft until an analyst approves it.
9. **Export** the analysis as an Excel workbook.

Every step is written to an append-only **audit log** (who, what, when, on
what).

---

## Who does what

| Role | What they do | Where |
|---|---|---|
| **Analyst** | Creates their cases, uploads, extracts, corrects, keys missing items, submits to a supervisor, approves the AI commentary, exports | Cases, My cases, Review, Dashboard |
| **Supervisor** | Validates the cases submitted to them, or sends them back; sees every analyst's work and statistics; manages analyst accounts; deletes finished (analysed) cases | Supervisor dashboard, My cases, Users |
| **Administrator** | Runs the system without preparing or validating any case: manages supervisor and analyst accounts, reads the audit log (filters, CSV), browses the database read-only, manages the evaluation corpus, runs and deletes evaluation campaigns | Administration: Overview, Users, Audit log, Campaigns, Data |

Administrator accounts are managed only with `backend/create_admin.py`,
never from the screens. Every user changes their own name and password on
**My account**.

The interface is in **English and French** (switch in the header). The
choice is remembered in the browser and also sets the language of the AI
commentary.

---

## Quick start (Windows, PowerShell)

**Requirements:** Python 3.11+, Node.js 18+. Optional: PostgreSQL (SQLite
is used otherwise), and Tesseract OCR for scanned PDFs.

```powershell
# 1. Python environment, from the project folder
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 2. Settings: copy the example, then edit .env
copy .env.example .env
#    For accounts to persist, set STORAGE=sql. Without DATABASE_URL the
#    data goes to data/prototype.db (SQLite); with it, to PostgreSQL.

# 3. The first administrator (one time)
cd backend
python create_admin.py          # prints a temporary password if you press Enter

# 4. The backend
python wsgi.py                  # http://127.0.0.1:5000/api/health
```

```powershell
# 5. The interface, in a second terminal
cd frontend
npm install
npm run dev                     # http://localhost:5173
```

Sign in as the administrator, change the temporary password on **My
account**, then create the supervisors and analysts on **Users**.

```powershell
# 6. The tests, from the project folder
pytest                          # 237 passed
```

> Start the backend from inside `backend/`: the `document_processing`
> package is imported from there.

---

## Configuration (`.env`)

`.env` is git-ignored and must never be committed (NFR-04). `.env.example`
lists every variable.

| Variable | Default | Meaning |
|---|---|---|
| `STORAGE` | `memory` | `memory` (nothing kept after a restart) or `sql` |
| `DATABASE_URL` | SQLite in `<project>/data/prototype.db` | e.g. `postgresql+psycopg://USER:PASSWORD@localhost:5433/DBNAME` |
| `AUTH_REQUIRED` | `true` | Sign-in and roles. `false` only for tests or a quick local demo |
| `SECRET_KEY` | random at each start | Signs the session cookie. Set it, or everyone is signed out on every restart |
| `STRUCTURER` | `rule_based` | `rule_based` or `llm` (Claude reads the figures) |
| `AI_ANALYSIS` | `llm` | `llm` (AI commentary) or `off` |
| `ANTHROPIC_API_KEY` | none | Needed for `STRUCTURER=llm` and the AI commentary |
| `MODEL` / `ANALYSIS_MODEL` | `claude-opus-5-5` | Model of the structurer / of the commentary |
| `INPUT_USD_PER_MTOK`, `OUTPUT_USD_PER_MTOK` | `4.00`, `20.00` | Prices used for the cost cap (and `ANALYSIS_…` variants) |
| `LLM_EFFORT` | `medium` | `low`, `medium`, `high`, `xhigh`, `max` |
| `MAX_COST_USD` | `5.00` | Hard cap on model spending since the backend started (NFR-08); restart to reset |
| `UPLOAD_DIR` | `<project>/data/uploads` | Where uploaded files are stored |
| `MAX_UPLOAD_MB` | `300` | Largest accepted upload |
| `CORPUS_DIR` | `<project>/data/corpus` | The evaluation corpus |
| `LLM_CACHE_DIR` | `<project>/data/llm_cache` | Cached model answers (never pay twice) |
| `OCR_WORKERS` | CPU count − 1, max 4 | Pages OCR'd in parallel |
| `CORS_ORIGIN` | `http://localhost:5173` | The development frontend |

---

## The accounting core

**Ratios** (`backend/app/domain/ratios/`):

| Code | Ratio | Formula | Reference threshold |
|---|---|---|---|
| R1 | Current ratio | (BK + BT) / (DP + DT) | 1.0 (documented) |
| R2 | Equity ratio | CP / (CP + DD) | none, deliberately (BR-14) |
| R3 | Stable funding coverage | (CP + DD) / AZ, AZ net | 1.0 (documented) |
| R4 | Net margin | XI / XB × 100 | none, deliberately |
| R5 | Return on equity | XI / CP × 100; not computable when equity is negative | none, deliberately |

**Consistency checks** (`backend/app/domain/checks.py`):

| Code | Check | Severity |
|---|---|---|
| CHK001 | Balance sheet equilibrium: BZ = DZ | blocking |
| CHK002 | Subtotals: AZ + BK + BT (+ BU) = BZ and CP + DD + DP + DT (+ DV) = DZ | blocking |
| CHK003 | Net income: XI = CJ | blocking |
| CHK004 | Completeness: the 11 required items are present | blocking |
| CHK005 | Plausible signs | warning |

The 11 required items: AZ, BK, BT, BZ, CP, DD, DP, DT, DZ, XB, XI.

Ratios are never computed from unvalidated data (BR-01). A missing item or a
zero denominator gives *not computable*, with its reason (BR-02, BR-03). No
ratio is called good or bad without a documented reference (BR-14).

---

## Evaluation (week 7)

The measurements of dossier §18–19, run over a corpus of hand-read packages:

```
data/corpus/
  RP001/
    ETAT_FINANCIER_TEST1.pdf      the statement(s)
    annotation_RP001.xlsx         your hand reading (sheet "Annotation",
                                  columns "code" and "Value")
  RP002/ ...
```

- **Corpus campaign**: the system extracts each package and is compared
  item by item with the hand reading. It reports field accuracy, ratio
  accuracy (within 1 %), the amplification coefficient, **silent false
  positives** (wrong values that pass every check) and the item criticality.
- **Sensitivity test**: a correct hand reading is damaged on purpose (+1 %,
  +5 %, +10 % on each item) to see which ratios move and whether the checks
  notice.

Run them from **Administration → Campaigns**, or from the command line:
`cd backend` then `python evaluate_corpus.py`. Every campaign is stored in
the database (`evaluation_campaign`, `evaluation_package`), with the
fingerprint of every file it read.

---

## Project layout

```
backend/
  app/                      the application (api, services, domain, infra)
  document_processing/      the original extractor (PDF, OCR, Excel, tables)
  wsgi.py                   starts the backend
  create_admin.py           manages administrator accounts
  evaluate_corpus.py        runs a corpus campaign from the command line
  add_users_schema.py       one-time migration (users table), already run
  reset_stranded_cases.py   one-time repair script
  test_loader.py            the original pipeline harness
frontend/                   React + Vite interface
tests/                      unit and integration tests (pytest)
data/                       uploads, corpus, model cache, test documents
docs/                       the documentation below
```

What **every file** does: [`docs/FILE-GUIDE.md`](docs/FILE-GUIDE.md).

---

## Documentation

| Document | What it answers |
|---|---|
| [`docs/PROJECT-STATE.md`](docs/PROJECT-STATE.md) | What is done, what is open, the history: **read it first** |
| [`docs/FILE-GUIDE.md`](docs/FILE-GUIDE.md) | What each file of the project does |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Why the code is arranged this way; where each rule lives |
| [`docs/EXTRACTION-PIPELINE.md`](docs/EXTRACTION-PIPELINE.md) | How `document_processing` reads a PDF or Excel statement |
| [`docs/DATA-MODEL-REVIEW.md`](docs/DATA-MODEL-REVIEW.md) | The database schema: the review of the original, and the tables added since |
| [`docs/LEARNING-PATH.md`](docs/LEARNING-PATH.md) | The supervisor's original week-by-week plan and exercises |

---

## Scope and known limitations

- **In scope:** balance sheet and income statement, PDF and Excel. Word
  files are refused by design.
- **Out of scope (dossier):** cash flow statement, notes, statement of
  changes in equity, sector benchmarking, scoring, IFRS, ERP integration,
  production deployment, real non-anonymised client data.
- **Scanned PDFs:** OCR recovers text, and a table is rebuilt from word
  positions, but a skewed or low-resolution scan can still yield nothing
  usable. The item can then be keyed in by hand.
- **No database migrations:** `create_all` creates missing tables but never
  alters an existing one (see `DATA-MODEL-REVIEW.md`).
- **Confidentiality (NFR-04):** public or anonymised documents only. A real
  client statement is never sent to a model API without written approval.