# Learning path

**Read this first. It is the only document you need open to know what to do
next.**

The scaffold you have been given is deliberately incomplete. Everything
structural is built — the layers, the ports, the Flask app, the React app, the
tests, the sensitivity engine — and everything that is *the point of the
project* is left for you, with the specification, the guidance and, in most
cases, the tests already written.

That split is not laziness on the supervisor's part. The parts left to you are
the parts a jury will ask you about, and the only way to answer those questions
is to have made the decisions yourself.

---

## Before anything: get it running

```bash
# terminal 1 — the API
python -m venv .venv
.venv\Scripts\activate           # Windows
pip install -r requirements.txt
cd backend
python wsgi.py                   # http://127.0.0.1:5000/api/health
```

```bash
# terminal 2 — the interface
cd frontend
npm install
npm run dev                      # http://localhost:5173
```

```bash
# terminal 3 — the tests, all the time
pytest
```

You should see `52 passed, 18 skipped`. **The 18 skipped tests are your
exercises.** Each one is waiting behind a `@pytest.mark.skip` line that you
delete when you start that piece of work.

---

## How to work through it

One habit, and it is the only one that matters:

> **Delete a skip. Run the test. Watch it fail. Make it pass. Commit.**

In that order, every time. The test fails first *on purpose* — that is how you
know the test is actually exercising the code you are about to write. A test
that passes before you have written anything is testing nothing.

Commit after each one, with a message that says what changed and why:

```
CHK002: subtotal consistency, blocking, BU/DV absent treated as zero
```

not `fix` or `update`. In eight weeks you will want to find the commit where
you decided how to treat BU, and `git log --oneline` is how you will find it.

---

## The order, week by week

The schedule below follows dossier §5.2. The arbitration rule of §3.3 governs
everything: **if you fall behind, reduce the number of ratios first, then the
number of extracted items. Never reduce the evaluation protocol** — it is what
gives the work its academic value.

### Week 2 — the corpus (no code)

The one week with no programming, and the one that decides whether weeks 7 and
8 are possible at all. Milestone 1: corpus and ground truth frozen.

- 20 to 30 reporting packages, varied in layout and quality.
- For each: every item of `REQUIRED_CODES` read off the document **by hand**,
  and the five ratios computed **by hand** from those amounts.
- Store them as JSON next to the documents, in the same shape as
  `tests/conftest.py::BALANCED`. That shape is already what
  `FinancialStatement.from_dict` reads, so your corpus is directly usable by
  the evaluation service with no conversion.

Do the preliminary exercise of dossier §4.2 first: for each candidate ratio,
locate exactly where each required item sits in a real package. Two hours, and
it justifies your scope better than any argument.

> **Confidentiality (NFR-04).** Public or synthetic documents by default.
> Internal documents only anonymised and with prior approval. Never send a real
> client statement to a model API.

### Week 3 — the domain, in one sitting

This is where you learn the layer everything else rests on, and it is all
pure Python with no infrastructure in the way.

| # | Exercise | File | Test to un-skip |
|---|---|---|---|
| 1 | **R2** equity ratio | `domain/ratios/r02_equity_ratio.py` | `test_ratios.py::TestR2` |
| 2 | **R3** stable funding | `domain/ratios/r03_stable_funding.py` | `TestR3` |
| 3 | **R4** net margin | `domain/ratios/r04_net_margin.py` | `TestR4` |
| 4 | **R5** return on equity | `domain/ratios/r05_return_on_equity.py` | `TestR5` |
| 5 | **CHK004** completeness | `domain/checks.py` | `TestCHK004` |
| 6 | **CHK002** subtotal consistency | `domain/checks.py` | `TestCHK002` |
| 7 | **CHK003** net income consistency | `domain/checks.py` | `TestCHK003` |

Start with R2: it is the shortest, and `r01_current_ratio.py` next to it is a
complete worked example. Then R3, R4, R5 — each docstring names the trap
specific to it, and the traps are the interesting part.

**R5 carries your first real design decision**: what should the system do
with negative equity? Both options in the docstring are defensible. Choose,
implement, adjust the test, and write one paragraph in your thesis explaining
why. That paragraph is worth more than the code.

After exercise 4, run `pytest tests/unit/test_evaluation.py -v` again and look
at `test_criticality_ranks_items`. The ranking has changed, because more
ratios now depend on more items. That is error propagation, becoming visible.

**Then**, and only then, come back to the extractor: your README documents a
sign ambiguity on XI/XG because the income statement's `+`/`-` operator column
is not yet interpreted. CHK003 will fire on correctly extracted documents
until it is resolved. Resolving it is real work in
`document_processing/structure.py` — and it is the single most valuable fix
available to you, because XI feeds two of the five ratios.

### Week 4 — the language model

Milestone 2: first end-to-end extraction.

| # | Exercise | File |
|---|---|---|
| 8 | Write the prompt | `infra/llm/prompts/v1.md` |
| 9 | Implement the model call | `infra/llm/claude_structurer.py::_call_model` |
| 10 | Record what the schema rejected | `services/extraction_service.py::_to_fields` |

Order matters here more than anywhere. **Test the prompt by hand, in the
console, on one page of one document, before writing a single line of
`_call_model`.** Ten minutes there will save you an afternoon debugging an API
call that was never the problem.

Everything around the call is already written: the cache keyed by fingerprint,
the strict schema at the boundary, the single retry of UC-03/A2, the budget
cap. Read the file before you start — the interesting engineering there is not
the call, it is what makes an unreliable component safe to depend on.

Before you spend a franc: run the rule-based structurer over your corpus and
count what it already gets right. Every item the rules read correctly is an
item you do not need a model for — and that number is a result for the thesis,
not just a saving.

### Week 5 — the chain on the command line

**Milestone 3, and the point of no return** (§5.2). If the chain is not
running end to end by the end of this week, cut the interface back to its
simplest form to protect weeks 7 and 8. *A measured chain without an interface
supports a thesis; a handsome interface without measurement does not.*

| # | Exercise | File |
|---|---|---|
| 11 | Thresholds, or a documented absence | `domain/interpretation/templates.py` |
| 12 | Serve the source document | `api/routes.py` — `GET /api/documents/<id>/file` |
| 13 | What "invalidate" means on reopening | `services/validation_service.py::reopen` |

Exercise 11 is mostly not code. For each of R2..R5, either find a threshold
you can **cite** — a textbook, a professional body, the firm's own practice,
recorded in `Threshold.source` — or leave it at `None` and say why in the
thesis. Both answers are acceptable. Inventing a number is not: §20.2 says an
invented threshold is worse than no threshold at all.

### Week 6 — the interface

Milestone 4: internal demonstration.

| # | Exercise | File |
|---|---|---|
| 14 | Side-by-side document pane (FR-10) | `frontend/src/pages/ReviewPage.jsx` |
| 15 | Export (FR-19, a *should*) | `api/routes.py` + `DashboardPage.jsx` |

Exercise 14 is the one that matters: NFR-07 asks that a package be reviewable
in under ten minutes by someone untrained. An analyst who has to switch
windows to check an amount will not manage it. The placeholder in
`ReviewPage.jsx` tells you exactly how to start — an `<iframe>`, no library.

Exercise 15 only if 14 is done and the evaluation is on track.

### Week 7 — the measurements

Milestone 5: quantified results. This is the contribution.

| # | Exercise | File |
|---|---|---|
| 16 | **Silent false positives** | `services/evaluation_service.py` |
| 17 | Field-level accuracy | same |
| 18 | Ratio-level accuracy | same |
| 19 | Amplification coefficient | same |
| 20 | Persist campaigns — or argue you need not | `api/routes.py::get_evaluation` |

**Do 16 first**, even though it looks like the hardest. The dossier calls the
silent false positive *"the most important of all"*: an error that clears every
check and ends up in a ratio shown to a client is exactly the scenario the
system exists to prevent.

The sensitivity matrix (§19.2) is already built and already runs. Point it at
your corpus the first day of this week, before writing anything, and look at
the criticality ranking. It tells you where your extraction effort should have
gone — and comparing that against where it actually went is itself a finding.

### Week 8 — writing

Milestone 6. No new features. If something is not finished by the end of week
7, it becomes a stated limitation (§20), which is worth more to a jury than a
feature rushed in the final days.

---

## The exercises that are not code

These are worth as much as the rest, and they are the ones students forget.

1. **The R5 decision** (negative equity) — one paragraph, argued.
2. **The AZ column convention** (BRUT or NET) — one sentence, and the same
   sentence must hold for CHK001 and R3, or the system contradicts itself.
3. **The failure typology** (§19.3) — classify every failure by cause: unusual
   layout, scan quality, non-standard label, ambiguous amount, hallucination,
   item absent from the document. This tells the firm which documents can be
   automated with confidence and which will always need a human, and it
   survives the internship.
4. **Whether the model's stated confidence means anything** — you ask for it in
   the prompt; check whether low confidence actually predicts wrong answers.
   If it does not, say so. A negative result, honestly measured, is a result.
5. **The four acknowledged limitations** (§20) — stated by you, at the
   defence, before the jury finds them.

---

## When you are stuck

In this order:

1. **Read the test.** It says what the code is supposed to do, more precisely
   than any docstring.
2. **Read the worked example.** R1 for a ratio, CHK001 and CHK005 for a check,
   `CasesPage.jsx` for a React page, `SqlCaseRepository` for a repository.
3. **Run it and print.** The domain layer needs nothing to run:
   `python -c "from app.domain.ratios import compute_all; ..."` from `backend/`
   gives you a REPL on the whole business core in one line.
4. **Then ask.** With: what you expected, what happened, and the smallest
   piece of code that shows the difference. Preparing that question solves it
   about half the time — and the other half, it gets answered in two minutes
   instead of twenty.

Do not spend more than forty minutes stuck on the same thing without asking.
That is not a rule about pride; it is a rule about an eight-week schedule.

---

## What "done" looks like for each piece

Not "it runs". A piece of work is done when:

- its test passes, **and** the test failed before you wrote the code;
- `pytest` is green as a whole — you broke nothing else;
- the code says *why*, not *what*: a comment explaining the accounting
  convention is worth ten explaining the syntax;
- you could defend the decision behind it out loud, in one minute, without
  notes.

That last one is the real bar. Everything else is how you get there.
