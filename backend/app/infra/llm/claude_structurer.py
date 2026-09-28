"""The language-model structurer.  *** YOUR EXERCISE — week 4 ***

Everything around the model call is written: the cache, the strict schema at
the boundary, the one-and-only-one retry of UC-03 alternative A2, the cost
accounting. What is missing is the call itself and the prompt.

That split is deliberate. The interesting engineering here is not "how do I
call an API" — it is everything that makes an unreliable component safe to
depend on. Read this file before writing the call.

Rules that apply to this adapter and are not negotiable
-------------------------------------------------------
* **NFR-04** — no real, non-anonymised client document is sent to a third
  party without written approval. Test on the public or synthetic corpus.
* **NFR-08** — capped budget, results cached by document fingerprint. A
  re-run on a document already seen must cost zero.
* **§11.1** — the domain never receives free text. The model's answer passes
  the schema below or it is rejected; there is no "mostly valid" path.
* **UC-03 / A2** — one retry, then an explicit failure. Not three, not a
  loop. A model that answered nonsense twice will answer nonsense a third
  time, and the budget is finite.
* **BR-13** — the model structures figures. It never writes a conclusion.
"""

from __future__ import annotations

import json
import os
from decimal import Decimal

from ...domain.ports import RawDocument, StructuredItem, StructuringResult
from .cache import ResponseCache

PROMPT_VERSION = "v1"

#: The shape the model must answer in. Anything else is rejected outright.
#: Keep it small: every field you add is a field the model can get wrong.
OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["items"],
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["item_code", "amount", "year"],
                "properties": {
                    "item_code": {"type": "string", "pattern": "^[A-Z]{2}$"},
                    "amount": {"type": "string"},
                    "year": {"type": "string", "enum": ["N", "N-1"]},
                    "source_page": {"type": "integer"},
                    "confidence": {"type": "number"},
                },
            },
        }
    },
}


class ClaudeStructurer:
    engine = "LLM"

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-sonnet-5",
        cache: ResponseCache | None = None,
        max_cost_usd: Decimal = Decimal("5.00"),
    ) -> None:
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.model = model
        self.cache = cache or ResponseCache()
        self.max_cost_usd = max_cost_usd
        self.spent_usd = Decimal("0")

    # --- the part that is written for you -------------------------------
    def structure(self, document: RawDocument) -> StructuringResult:
        fingerprint = self.cache.fingerprint(document.full_text, PROMPT_VERSION, self.model)
        cached = self.cache.get(fingerprint)
        if cached is not None:
            return self._parse(cached, cost=Decimal("0"))

        if self.spent_usd >= self.max_cost_usd:
            raise RuntimeError(
                f"model budget exhausted ({self.spent_usd} / {self.max_cost_usd} USD). "
                f"Raise the cap deliberately or use the rule-based structurer."
            )

        last_error: Exception | None = None
        for attempt in (1, 2):  # UC-03 / A2: one retry, and only one
            try:
                raw_response, cost = self._call_model(document, attempt)
                result = self._parse(raw_response, cost=cost)
                self.cache.put(fingerprint, raw_response)
                self.spent_usd += cost
                return result
            except (ValueError, json.JSONDecodeError) as exc:
                last_error = exc

        raise ValueError(
            f"model output did not match the schema after one retry: {last_error}"
        )

    def _parse(self, raw_response: str, cost: Decimal) -> StructuringResult:
        """The hard boundary. Nothing gets past this without being the right shape.

        Note what is *not* done here: no repair, no best-effort salvage of a
        half-valid answer. A structurer that fixes up the model's output is a
        structurer nobody can evaluate — you would no longer know what the
        model actually proposed, and ``proposed_amount`` would stop meaning
        anything.
        """
        payload = json.loads(raw_response)
        if not isinstance(payload, dict) or "items" not in payload:
            raise ValueError("response has no 'items' key")

        items: list[StructuredItem] = []
        for entry in payload["items"]:
            code = str(entry.get("item_code", "")).strip().upper()
            if len(code) != 2 or not code.isalpha():
                raise ValueError(f"not a SYSCOHADA code: {entry.get('item_code')!r}")
            year = entry.get("year", "N")
            if year not in ("N", "N-1"):
                raise ValueError(f"unexpected year: {year!r}")
            items.append(
                StructuredItem(
                    item_code=code,
                    amount=str(entry["amount"]),
                    year=year,
                    source_page=entry.get("source_page"),
                    confidence=(
                        Decimal(str(entry["confidence"]))
                        if entry.get("confidence") is not None
                        else None
                    ),
                )
            )

        return StructuringResult(
            items=items,
            engine=self.engine,
            model=self.model,
            prompt_version=PROMPT_VERSION,
            cost_usd=cost,
            raw_response=raw_response,
        )

    # --- the part you write ---------------------------------------------
    def _call_model(self, document: RawDocument, attempt: int) -> tuple[str, Decimal]:
        """Send the document text, get JSON back. Return (response, cost).

        TO IMPLEMENT (week 4). Steps, in order:

        1. ``pip install anthropic``; read the key from ``ANTHROPIC_API_KEY``
           and never, under any circumstance, commit it. ``.env`` is already
           in ``.gitignore`` — check that it still is before your first call.
        2. Write the prompt in ``prompts/v1.md`` and load it from there, not
           from a string in this file. Versioned prompts are what make FR-23
           ("replay an extraction with a different prompt version") possible,
           and comparing two prompt versions on the same document is a
           measurement your thesis can use.
        3. Ask for JSON matching ``OUTPUT_SCHEMA``. Send the document *text*,
           not a screenshot: cheaper, and the model then cites page numbers
           you can verify.
        4. On the retry (``attempt == 2``), append the validation error to the
           prompt — telling the model what it got wrong is worth far more
           than asking it the same question twice.
        5. Compute the real cost from the token counts the API returns and
           return it. A cost you estimate is a cost you cannot cap.

        Sanity check before you start: run the rule-based structurer on the
        same document first. Every item it already gets right is an item you
        do not need a model for.
        """
        raise NotImplementedError("ClaudeStructurer._call_model — see the docstring")
