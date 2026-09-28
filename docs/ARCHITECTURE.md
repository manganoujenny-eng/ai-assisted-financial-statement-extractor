# Architecture

The layout follows dossier §17.2. This document explains *why* each boundary
is where it is — because a structure you can justify is a structure you can
defend at the viva, and a structure you only inherited is one you will break
the first time you are in a hurry.

```
backend/
  document_processing/     ← your existing extractor. Untouched.
  app/
    api/                   Flask controllers, serialisation, error handling
    services/              orchestration: extraction, validation, analysis, evaluation
    domain/                the accounting rules. Depends on nothing.
      value_objects.py       Amount, ItemCode
      entities.py            AnalysisCase, ExtractedField, ... + the lifecycle
      statement.py           code -> Amount, the only shape the rules see
      syscohada.py           the catalogue of codes in scope
      checks.py              CHK001..CHK005
      ratios/                one module per ratio + the engine
      interpretation/        templates and thresholds
      ports.py               the interfaces the domain requires
    infra/
      pdf/                   adapters over document_processing
      llm/                   rule-based structurer, Claude adapter, cache, prompts
      db/                    SQLAlchemy models, repositories, in-memory repositories
  wsgi.py                  python wsgi.py -> http://127.0.0.1:5000
tests/
  unit/domain/             no network, no database, no PDF
  integration/             the whole chain over HTTP
frontend/                  React + Vite
docs/
```

---

## The one rule

**Dependencies point inward.** `api` may import `services`; `services` may
import `domain`; `domain` imports nothing but the Python standard library.

That is not taste. It is requirement NFR-06, and
`tests/unit/domain/test_entities_and_purity.py` fails the build if it is ever
broken — it parses every module under `domain/` and looks at the imports.

### Why it is worth the discipline

Three things become possible that would otherwise not be:

1. **The sensitivity analysis of Part D.** Section 19.2 asks you to perturb
   every item by three percentages and recompute every ratio. That is several
   hundred complete computations. Because the domain needs no database and no
   network, the whole campaign finishes in under a second — run
   `pytest tests/unit/test_evaluation.py` and watch the timer.

2. **Swapping the model for another.** `STRUCTURER=llm` in the environment and
   nothing else in the codebase changes. The composition root
   (`backend/app/__init__.py`) is the only file that names a concrete adapter.

3. **The baseline comparison your thesis needs.** `RuleBasedStructurer` and
   `ClaudeStructurer` implement the same port, so they can be run over the
   same corpus and measured against each other without a single `if`.

### Where each business rule lives

Keep this table beside you when you are unsure where to put something. The
question is never "where would this be convenient?" but "what kind of thing is
it?".

| Rule | Where it is enforced |
|---|---|
| BR-01 no ratio from unvalidated data | `AnalysisService.analyse` takes a `ValidatedDataset` and nothing else |
| BR-02 missing item → NOT_COMPUTABLE | `ratios/engine.py`, before the calculator is called |
| BR-03 zero denominator → NOT_COMPUTABLE | `ratios/engine.py`, catching `ZeroDivisionError` |
| BR-04 keep the items used | `RatioResult.items_used`, serialised and stored |
| BR-05..09 the checks | `domain/checks.py` |
| BR-10 a correction keeps the proposal | `ExtractedField.correct`, and the repository never updates `proposed_amount` |
| BR-11 rerun every check | `ValidationService.correct_field` |
| BR-12 no validation while blocking | `ValidationService.validate`, rechecked at the moment of validation |
| BR-13 no free text as a conclusion | `interpretation/templates.py` — three templates, no fourth path |
| BR-14 no judgement without a reference | `THRESHOLDS`; an absent threshold produces a factual sentence |
| BR-15 rounding | `value_objects.py`, applied once in the engine |

---

## The patterns, and what each one actually buys

Dossier §13 lists five. Here is where each one is, and the concrete thing it
gives you — a pattern with no payoff is decoration.

**Strategy** — `domain/ratios/`, one module per ratio.
Adding R6 means adding a file and one line in `engine.py::_MODULES`. The
engine never changes, so the rules it enforces (BR-02, BR-03, BR-04, BR-15)
apply automatically to every ratio you will ever add.

**Adapter** — `infra/pdf/readers.py`, `infra/llm/`.
Your `document_processing` package became usable by the rest of the system
without one line changed inside it. That is the test of a good adapter: the
thing being adapted does not know it has been adapted.

**Repository** — `infra/db/repositories.py` and `infra/db/memory.py`.
Two implementations of the same ports. Every service test runs against the
in-memory one, in microseconds, leaving nothing behind.

**Template method** — `ExtractionService.run_extraction`.
The sequence detect → extract → structure → validate → check → persist is
fixed and matches UC-03 step for step. Only the steps vary.

**Value object** — `Amount`, `ItemCode`.
`Amount` refuses a float. That single refusal is why the equilibrium check can
test equality to the franc: with floats, `0.1 + 0.2 != 0.3`, and on a balance
sheet of several billion that inexactness becomes visible.

---

## Adding things: the four recipes

**A ratio.** Create `domain/ratios/r06_something.py` with a `calculate`
function and a `DEFINITION`; add the module to `_MODULES` in `engine.py`; add
a threshold in `interpretation/templates.py` *if you have a citable source*;
write the test. Nothing else.

**A check.** Write the function in `domain/checks.py`, add it to `REGISTRY`,
choose its severity deliberately — BLOCKING stops a validation, so it must be
a rule that admits no judgement.

**An endpoint.** Add it to `api/routes.py`, keep it to three lines of work:
read the request, call a service, serialise. If an `if` about accounting
appears in a route, it belongs in the domain.

**An adapter** (another model provider, another OCR engine). Write a class
with the methods the port declares — no inheritance needed, `Protocol` matches
on shape — and wire it in `app/__init__.py::build_container`.

---

## What is deliberately not here

- **Authentication and access rights.** Out of scope (§3.3). The *shape* of
  the separation is in place — `ValidationService` distinguishes the analyst
  who corrects from the supervisor who validates, per §6.2 — but the author is
  a string passed by the caller. Wiring real roles later touches one file.
- **Background jobs.** Extraction is synchronous. NFR-03 allows 90 seconds,
  which a browser will wait for. The day OCR on a 40-page scan exceeds that,
  one route changes and nothing below it notices.
- **Migrations.** `create_all` is enough for a prototype. See the end of
  `DATA-MODEL-REVIEW.md` for when it stops being enough.
- **Deployment.** Explicitly out of scope, and §20.4 asks you to say so at the
  defence rather than let a jury discover it.
