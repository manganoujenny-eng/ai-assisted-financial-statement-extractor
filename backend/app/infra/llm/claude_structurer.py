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
import anthropic

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
                "required": [
                    "item_code",
                    "amount",
                    "year",
                    "source_page",
                    "confidence",
                ],
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
                raw_response, cost = self._call_model(
                    document,
                    attempt,
                    str(last_error) if last_error else None,
                )
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


    def _call_model(
        self,
        document: RawDocument,
        attempt: int,
        validation_error: str | None = None,
    ) -> tuple[str, Decimal]:

     prompt_path = os.path.join(
            os.path.dirname(__file__),
            "prompts",
            f"{PROMPT_VERSION}.md",
        )

     with open(prompt_path ,"r" , encoding="utf-8") as file:
           prompt_template = file.read()

     prompt = prompt_template.replace(
           "<!-- The adapter inserts RawDocument.full_text here. -->",
           document.full_text,
       )

     if attempt == 2:
           if validation_error is None:
               raise ValueError("retry attempt requires a validation error")

           prompt += (
               "\n\nYour previous response failed validation for this reason:\n"
               f"{validation_error}\n"
               "Return corrected JSON only."
         )


     client = anthropic.Anthropic(api_key=self.api_key)

     response = client.messages.create(
           model=self.model,
           max_tokens=4096,
           messages=[
               {
                   "role": "user",
                   "content": prompt,
               }
           ],
           output_config={
               "format": {
                   "type": "json_schema",
                   "schema": OUTPUT_SCHEMA,
               }
           },
       )

     #EXTRACT THE JSON TEXT
     raw_response = next(
           block.text
           for block in response.content
           if block.type == "text"
       )

     #GET THE ACTUAL TOKEN COUNT
     input_tokens = response.usage.input_tokens
     output_tokens = response.usage.output_tokens

     #CALCULATE THE COST
     input_cost = (
               Decimal(input_tokens) * Decimal("2.00") / Decimal("1000000")
       )

     output_cost = (
               Decimal(output_tokens) * Decimal("10.00") / Decimal("1000000")
       )

     cost = input_cost + output_cost

     return raw_response, cost