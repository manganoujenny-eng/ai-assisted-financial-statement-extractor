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
        model: str = "claude-opus-5-5",
        cache: ResponseCache | None = None,
        max_cost_usd: Decimal = Decimal("5.00"),
        input_usd_per_mtok: Decimal = Decimal("4.00"),
        output_usd_per_mtok: Decimal = Decimal("20.00"),
        effort: str = "medium",
        max_tokens: int = 16000,
    ) -> None:
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.model = model
        self.cache = cache or ResponseCache()
        self.max_cost_usd = max_cost_usd
        # Opus 5.5 prices by default ($4 / $20 per million tokens). Thinking
        # tokens are billed as output, so they are in output_tokens below.
        self.input_usd_per_mtok = input_usd_per_mtok
        self.output_usd_per_mtok = output_usd_per_mtok
        self.effort = effort
        # Opus 5.5 always thinks first, and thinking counts toward
        # max_tokens. 4096 left too little room for the JSON on a long
        # package; the budget cap (max_cost_usd) is what limits spending.
        self.max_tokens = max_tokens
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
                # Counted before parsing: a rejected answer was billed too.
                self.spent_usd += cost
                result = self._parse(raw_response, cost=cost)
                self.cache.put(fingerprint, raw_response)
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
        with open(prompt_path, "r", encoding="utf-8") as file:
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

        # Opus 5.5 rules (migration guide): no temperature/top_p/top_k, no
        # thinking budget, no assistant prefill. Thinking is adaptive and
        # always on; "effort" is the only knob. The JSON shape is enforced
        # by structured outputs (output_config.format).
        response = client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[{"role": "user", "content": prompt}],
            output_config={
                "effort": self.effort,
                "format": {
                    "type": "json_schema",
                    "schema": OUTPUT_SCHEMA,
                },
            },
        )

        # The cost is due whatever the answer is, so count it first.
        cost = (
            Decimal(response.usage.input_tokens) * self.input_usd_per_mtok
            + Decimal(response.usage.output_tokens) * self.output_usd_per_mtok
        ) / Decimal(1_000_000)

        if response.stop_reason == "refusal":
            # Not retried: the same document would be refused again.
            self.spent_usd += cost
            raise RuntimeError("the model declined to process this document")
        if response.stop_reason == "max_tokens":
            self.spent_usd += cost
            raise ValueError(
                "the answer was cut off at max_tokens; the document may be too long"
            )

        # Thinking blocks come first on Opus 5.5: pick the text blocks by
        # type, never content[0].
        raw_response = "".join(
            block.text for block in response.content if block.type == "text"
        )
        return raw_response, cost