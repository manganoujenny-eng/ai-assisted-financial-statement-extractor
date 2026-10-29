# Review of `financial_analysis_db.sql`

Read this before you conclude your schema was wrong. Most of it was right —
the seven tables, the direction of the relationships and the general shape all
match the data model of dossier §16. What follows are the differences between
your dump and `backend/app/infra/db/models.py`, each with its reason.

Three of them are real defects that would have cost you time later. The rest
are conventions, and conventions are worth adopting early only because they
stop costing attention once adopted.

---

## The three that matter

### 1. `ratio_result.dataset_id` pointed at the wrong table

```sql
-- your dump
ALTER TABLE ONLY public.ratio_result
    ADD CONSTRAINT fk_constraint_dataset_id
    FOREIGN KEY (dataset_id) REFERENCES public.extraction_run("extRun_id");
```

The column is called `dataset_id` but it references `extraction_run`. So a
ratio could be attached to raw, unreviewed extraction output — and **BR-01**
says no ratio is ever computed from data a human has not validated.

A foreign key is a far stronger guarantee of a business rule than a comment or
a careful service layer, because it holds even when someone writes to the
database by hand at eleven at night. Corrected to reference
`validated_dataset`.

This is the kind of mistake worth being pleased about finding: it is invisible
in the code and obvious in the schema, which is exactly why reviewing the
schema separately is worth doing.

### 2. `extracted_field` had nowhere to keep what the extractor proposed

Your `extracted_field` holds `amount`. Once an analyst corrects that amount,
what the model originally proposed is gone.

Dossier §12.1 singles this out: *"it is that field which makes it possible,
after the fact, to measure what the model proposed and what the human had to
correct — and therefore to produce the indicators of Part D."*

Without it, field-level accuracy cannot be measured after any correction has
been made, and Part D — the part that makes this a piece of research rather
than a development exercise — becomes impossible.

Added: `proposed_amount`, written once at extraction and never updated.
`repositories.py` has a comment on the exact line where updating it would be
tempting.

### 3. Every status column reused one enum that fits none of them

```sql
CREATE TYPE public.analysis_status AS ENUM
    ('pending', 'processing', 'completed', 'failed');
```

Used for `analysis_case.status`, `extracted_field.status`,
`extraction_run.status` and `ratio_result.status`. But these four columns
describe four different things:

| Column | What its values actually are |
|---|---|
| `analysis_case.status` | CREATED, EXTRACTING, EXTRACTED, EXTRACTION_FAILED, UNDER_REVIEW, VALIDATED, ANALYSED (dossier §15) |
| `extracted_field.status` | PROPOSED, CORRECTED, VALIDATED, KEYED (UC-04) |
| `extraction_run.status` | EXTRACTING, EXTRACTED, EXTRACTION_FAILED |
| `ratio_result.status` | COMPUTED, NOT_COMPUTABLE (BR-02) |

A shared enum forces a field status of `completed`, which answers none of the
questions UC-04 asks of it — was this value proposed by the machine, corrected
by a human, or keyed in by hand because the document never had it?

The models use plain short strings per column, with the permitted values
declared as constants in `domain/entities.py` and enforced by the state
machine there. An alternative, equally defensible, is one PostgreSQL enum per
column. What is not defensible is one enum for all four.

---

## The rest: conventions

### Quoted mixed-case identifiers

`"aCase_id"`, `"extField_id"`, `"extRun_id"` are created with capital letters,
so PostgreSQL requires double quotes **forever**, in every query anyone ever
writes:

```sql
SELECT "extField_id" FROM extracted_field;   -- works
SELECT extField_id FROM extracted_field;     -- error: column does not exist
```

The convention in PostgreSQL is `snake_case`, unquoted. Renamed to `id`, with
the table name giving the context (`extracted_field.id`, not
`extracted_field.extField_id`).

### `she256` → `sha256`

A typo, in a column name, in a schema. Harmless today; in six months it is in
forty queries and renaming it is a migration. Worth the ten seconds now.

### No uniqueness on the fingerprint

The whole point of the SHA-256 (dossier §16, NFR-08) is that the same bytes
are never extracted — or paid for — twice. Nothing in the dump enforced it.
Added `UNIQUE (sha256)`.

### Missing `NOT NULL`

`client`, `fiscal_year`, `file_name` and the status columns were all nullable.
A case with no client is not a case. Every column that must have a value now
says so, in the schema, where the rule cannot be forgotten.

### Missing timestamps

NFR-01: *"every displayed figure must be traceable to its source page, its
author and its timestamp."* `created_at`, `uploaded_at`, `started_at`,
`finished_at`, `corrected_at`, `computed_at` added.

### `audit_log.author` was a `uuid` with no table behind it

There is no user table, and access rights are explicitly out of scope (§3.3).
A `uuid` referencing nothing is a foreign key that is not one. Changed to a
plain string holding a name — honest about what it is, and trivially replaced
by a real FK the day a user table exists.

### `check_result` had no message

`passed`, `severity` and `gap` were there — good, and `gap` in particular is
exactly what §12.1 asks for. Added `message`, so a supervisor reading a
refusal sees *"BZ (11 246 000) ≠ DZ (11 246 235), gap of 235"* rather than
*"CHK001 failed"*.

### Nothing recorded a run's cost or its failure

`extraction_run` needs `cost_usd` (NFR-08, capped budget) and
`failure_reason` (UC-03 exception E1: *"state EXTRACTION_FAILED, reason
recorded"*). Added, along with `started_at` / `finished_at` for NFR-03.

### No `interpretation` table

BR-14 requires the sentence shown to a client to remain explainable: which
template produced it, which threshold was applied, what the reference was.
Storing only the text loses all three. Table added.

### Oversized column types

`year character varying(100)` holds `"N"` or `"N-1"`. `varchar(100)`
everywhere is a habit worth dropping: the length is free documentation about
what the column is for, and `item_code char(2)` states the SYSCOHADA rule in
the schema itself.

---

## What to do with this

You do not have to migrate the PostgreSQL database you already created. The
prototype runs on SQLite by default precisely so that nothing blocks on it
(`STORAGE=memory` needs no database at all).

When you do want PostgreSQL:

```bash
createdb financial_analysis_v2
export DATABASE_URL=postgresql+psycopg://postgres:password@localhost:5432/financial_analysis_v2
export STORAGE=sql
cd backend && python wsgi.py
```

SQLAlchemy creates the tables from `models.py` on start-up.

One thing worth knowing now even though you do not need it this week:
`create_all` only ever *creates* tables. It never alters an existing one. The
day you add a column to `models.py` and wonder why it is not in your database,
that is why — and the answer is a migration tool (Alembic). Not this week.


---

## Since this review (updated 22 October 2026)

The review above is kept as written: it is the record of how the schema got
its shape. The schema has grown since, with the features of October. All
tables live in `backend/app/infra/db/models.py`; there are now **16**.

| Table or column | Added for | What it holds |
|---|---|---|
| `analysis_case.analyst` | My cases (item 4) | The full name of the analyst who owns the case. Added to the existing table once by a one-time script, because `create_all` never alters a table. |
| `ai_analysis` | AI commentary (item 4) | One commentary per validated dataset: status (DRAFT, APPROVED, FAILED), the model's original sections and the approved ones, model, prompt version and language, cost, failure reason, who approved it and when. |
| `app_user` | Sign-in and roles (item 5) | Username and full name (both unique), role (ANALYST, SUPERVISOR, ADMIN, SUPERADMIN — exactly one, created by `create_superadmin.py`), password **hash** (never the password), active flag. Created by `add_users_schema.py`. |
| `evaluation_campaign` | Week 7, exercise 20 | One row per campaign: kind (CORPUS or SENSITIVITY), when, who, engine, corpus folder, note, the headline figures in their own columns, the full summary and the input fingerprints as JSON. |
| `evaluation_package` | Week 7, exercise 20 | One row per package of a corpus campaign, with its figures and full detail; deleted with its campaign (`ON DELETE CASCADE`). |
| `archive_entry` | The archive (27 Oct) | One row per deletion: kind (case, document, user, campaign, corpus file or package), label, who deleted it and when, a summary, and the whole object as JSON (`payload`, never shown in the data browser) so it can be restored with the same ids. Purging deletes the row. |
| `case_comment` | Supervisors' discussion (27 Oct) | One message: case id, author (the signed-in supervisor's name), text (at most 2000 characters), when. Deleted with its case, and archived and restored with it. |
| `case_discussion_read` | Supervisors' discussion (27 Oct) | When each supervisor last opened each case's thread, so the bell counts only unread messages. |

Two points of the review have moved on:

- **`audit_log.author`** is still a plain name, on purpose, even though a
  user table now exists. The name comes from the signed-in session, never
  from the request; it also records authors that are not accounts (a script
  such as `create_admin.py`, the application itself, a username typed at a
  refused sign-in), which a foreign key to `app_user` could not hold.
- **Default storage.** With no settings at all, the prototype keeps
  everything in memory (`STORAGE=memory`); with `STORAGE=sql` and no
  `DATABASE_URL` it uses SQLite (`data/prototype.db`); your `.env` points it
  at PostgreSQL.

Still true: no native ENUM types; `ratio_result`, `interpretation` and
`check_result` exist but are not written (results are recomputed from
`validated_dataset`); no migration tool. Each new column so far was added
with a one-time script; if columns keep being added, that is the moment for
Alembic.
