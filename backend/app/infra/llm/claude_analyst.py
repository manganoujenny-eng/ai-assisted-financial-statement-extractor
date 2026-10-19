"""The commentary writer (item 4) — an LLM writing ABOUT computed results.

Compare with ``claude_structurer.py``: that adapter would have let a model
propose the figures themselves. This one never sees a document and never
proposes a figure. It receives the validated amounts, the rule-based ratios,
the check results and the year comparison (``InsightService.build_payload``)
and writes commentary on them, which an analyst must approve (BR-13).

Same discipline as the structurer:

* **One retry, then an explicit failure** (UC-03 / A2). The failure is
  recorded on the AiAnalysis; the validated analysis is never blocked by it.
* **The answer is checked, not trusted.** JSON with the expected keys, or it
  is refused (``InsightService.clean_sections`` checks the shape again).
* **Capped budget** (NFR-08). ``max_cost_usd`` per process, like the
  structurer.

Plain JSON-in-the-prompt rather than an SDK structured-output parameter, so
this adapter does not depend on one SDK version's parameter names.
"""

from __future__ import annotations

import json
import os
from decimal import Decimal

from ...domain.ports import AnalysisDraft

PROMPT_VERSION = "analysis-v2"
PROMPT_FILE = "analysis_v2.md"
PLACEHOLDER = "<!-- The adapter inserts the payload JSON here. -->"
LANGUAGE_PLACEHOLDER = "{{LANGUAGE}}"

#: The languages the interface offers, and the name the prompt uses for
#: each. The commentary is written in the language the analyst's screen
#: is in; anything unknown falls back to English.
LANGUAGES = {"en": "English", "fr": "French"}


class ClaudeAnalyst:
    def __init__(
        self,
        api_key: str | None,
        model: str,
        max_cost_usd: Decimal = Decimal("5.00"),
        input_usd_per_mtok: Decimal = Decimal("4.00"),
        output_usd_per_mtok: Decimal = Decimal("20.00"),
        max_tokens: int = 8000,
        effort: str = "medium",
    ) -> None:
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.model = model
        self.max_cost_usd = max_cost_usd
        self.input_usd_per_mtok = input_usd_per_mtok
        self.output_usd_per_mtok = output_usd_per_mtok
        # Opus 5.5 thinks before answering and thinking counts toward
        # max_tokens: 2000 could be used up before the JSON was written.
        self.max_tokens = max_tokens
        self.effort = effort
        self.spent_usd = Decimal("0")

    def write(self, payload: dict) -> AnalysisDraft:
        if not self.api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        if self.spent_usd >= self.max_cost_usd:
            raise RuntimeError(
                f"AI budget exhausted ({self.spent_usd} / {self.max_cost_usd} USD) — "
                "raise MAX_COST_USD deliberately, or restart the backend"
            )

        language = payload.get("language") if payload.get("language") in LANGUAGES else "en"
        prompt = self._prompt(payload, language)
        cost = Decimal("0")
        last_error: Exception | None = None

        for attempt in (1, 2):  # one retry, and only one
            text, call_cost = self._call(
                prompt
                if attempt == 1
                else prompt
                + "\n\nYour previous answer was rejected: "
                + str(last_error)
                + "\nAnswer again with the JSON object only."
            )
            cost += call_cost
            self.spent_usd += call_cost
            try:
                sections = self._parse(text)
                return AnalysisDraft(
                    sections=sections,
                    model=self.model,
                    # e.g. "analysis-v2/fr": the screen shows which language
                    # a stored commentary was written in.
                    prompt_version=f"{PROMPT_VERSION}/{language}",
                    cost_usd=cost,
                )
            except ValueError as exc:
                last_error = exc

        raise ValueError(f"the model's answer was not valid after one retry: {last_error}")

    # --- helpers -------------------------------------------------------------
    def _prompt(self, payload: dict, language: str) -> str:
        path = os.path.join(os.path.dirname(__file__), "prompts", PROMPT_FILE)
        with open(path, encoding="utf-8") as handle:
            template = handle.read()
        figures = {key: value for key, value in payload.items() if key != "language"}
        return template.replace(LANGUAGE_PLACEHOLDER, LANGUAGES[language]).replace(
            PLACEHOLDER, json.dumps(figures, ensure_ascii=False, indent=2)
        )

    def _call(self, prompt: str) -> tuple[str, Decimal]:
        import anthropic  # noqa: PLC0415 — lazy: the app starts without the SDK

        client = anthropic.Anthropic(api_key=self.api_key)
        # Opus 5.5: no temperature/top_p/top_k and no prefill; thinking is
        # always on and "effort" is the only control.
        response = client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[{"role": "user", "content": prompt}],
            output_config={"effort": self.effort},
        )
        usage = response.usage
        cost = (
            Decimal(usage.input_tokens) * self.input_usd_per_mtok
            + Decimal(usage.output_tokens) * self.output_usd_per_mtok
        ) / Decimal(1_000_000)
        if response.stop_reason == "refusal":
            self.spent_usd += cost
            raise RuntimeError("the model declined to write this commentary")
        if response.stop_reason == "max_tokens":
            # Becomes a ValueError in write(), so it gets the one retry.
            return "", cost
        # Thinking blocks come first: select text blocks by type.
        text = "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        )
        return text, cost

    @staticmethod
    def _parse(text: str) -> dict:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:]
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end == -1:
            raise ValueError("no JSON object in the answer")
        try:
            data = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON: {exc}") from exc
        missing = [k for k in ("overview", "ratios", "checks", "comparison", "attention") if k not in data]
        if missing:
            raise ValueError(f"missing keys: {', '.join(missing)}")
        return data