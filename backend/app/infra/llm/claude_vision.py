"""Reading a scanned PDF with the model, from images of its pages.

The rule-based structurer reads the tables that pdfplumber or the OCR
rebuilt. On a bad scan (skewed, blurred, low resolution) the OCR words land
in the wrong places and no table survives — the case fails with "no usable
item found". This adapter is the analyst's way out: "Read with AI" renders
each page as an image and asks Claude to read the line items off the
images, the way a person would.

It is the text structurer (``claude_structurer.py``) with one difference:
what is sent. Everything else is inherited unchanged — the strict schema at
the boundary, ONE retry, the cost counted before parsing, the budget cap,
and the cache: the key is the fingerprint of the page images, so the same
scan read twice costs nothing the second time.

* **NFR-04** — the page images leave the machine for Anthropic: only an
  anonymised document, or one whose owner agreed, may be read this way.
  The screen asks the analyst to confirm that before every reading.
* Pages are rendered so their long side is ``LONG_EDGE`` pixels (what the
  model reads well, without paying for useless detail), and a long scan
  is cut at ``max_pages`` (``VISION_MAX_PAGES``): a SYSCOHADA balance sheet
  and income statement fit in a few pages.
"""

from __future__ import annotations

import base64
import hashlib
import os
from decimal import Decimal

import anthropic
import fitz  # PyMuPDF

from .claude_structurer import OUTPUT_SCHEMA, ClaudeStructurer

PROMPT_VERSION = "vision-v1"
#: The long side of a page image, in pixels.
LONG_EDGE = 1568


class ClaudeVisionStructurer(ClaudeStructurer):
    engine = "LLM_VISION"

    def __init__(self, *args, max_pages: int = 12, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.max_pages = max_pages

    # --- the entry point: a PDF file ------------------------------------------
    def structure_file(self, path: str):
        images = self._page_images(path)
        if not images:
            raise ValueError("the PDF has no page to read")
        digest = hashlib.sha256()
        for image in images:
            digest.update(hashlib.sha256(image).digest())
        fingerprint = self.cache.fingerprint(digest.hexdigest(), PROMPT_VERSION, self.model)
        cached = self.cache.get(fingerprint)
        if cached is not None:
            return self._result(cached, Decimal("0"))

        if self.spent_usd >= self.max_cost_usd:
            raise RuntimeError(
                f"model budget exhausted ({self.spent_usd} / {self.max_cost_usd} USD). "
                "Raise the cap deliberately (MAX_COST_USD) or key the items in by hand."
            )

        last_error: Exception | None = None
        for attempt in (1, 2):  # UC-03 / A2: one retry, and only one
            try:
                raw_response, cost = self._call_with_images(
                    images, attempt, str(last_error) if last_error else None
                )
                self.spent_usd += cost  # a rejected answer was billed too
                result = self._result(raw_response, cost)
                self.cache.put(fingerprint, raw_response)
                return result
            except (ValueError,) as exc:
                last_error = exc
        raise ValueError(f"model output did not match the schema after one retry: {last_error}")

    def _result(self, raw_response: str, cost: Decimal):
        result = self._parse(raw_response, cost=cost)  # the same hard boundary
        result.engine = self.engine
        result.prompt_version = PROMPT_VERSION
        return result

    # --- the pages, as PNG images ----------------------------------------------
    def _page_images(self, path: str) -> list[bytes]:
        images = []
        with fitz.open(path) as document:
            for page in list(document)[: self.max_pages]:
                zoom = LONG_EDGE / max(page.rect.width, page.rect.height)
                pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
                images.append(pixmap.tobytes("png"))
        return images

    # --- the call ---------------------------------------------------------------
    def _call_with_images(self, images: list[bytes], attempt: int,
                          validation_error: str | None) -> tuple[str, Decimal]:
        # The file is prompts/vision_v1.md (like analysis_v3.md).
        prompt_path = os.path.join(os.path.dirname(__file__), "prompts",
                                   f"{PROMPT_VERSION.replace('-', '_')}.md")
        with open(prompt_path, encoding="utf-8") as file:
            prompt = file.read()
        if attempt == 2:
            if validation_error is None:
                raise ValueError("retry attempt requires a validation error")
            prompt += (
                "\n\nYour previous response failed validation for this reason:\n"
                f"{validation_error}\nReturn corrected JSON only."
            )
        content = [
            {"type": "image",
             "source": {"type": "base64", "media_type": "image/png",
                        "data": base64.b64encode(image).decode("ascii")}}
            for image in images
        ]
        content.append({"type": "text", "text": prompt})

        client = anthropic.Anthropic(api_key=self.api_key)
        # Same call shape as the text structurer (Opus 5.5: no sampling
        # parameters, effort as the only knob, JSON enforced by the schema).
        response = client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[{"role": "user", "content": content}],
            output_config={"effort": self.effort,
                           "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
        )
        cost = (
            Decimal(response.usage.input_tokens) * self.input_usd_per_mtok
            + Decimal(response.usage.output_tokens) * self.output_usd_per_mtok
        ) / Decimal(1_000_000)
        if response.stop_reason == "refusal":
            self.spent_usd += cost
            raise RuntimeError("the model declined to read this document")
        if response.stop_reason == "max_tokens":
            self.spent_usd += cost
            raise ValueError("the answer was cut off at max_tokens")
        raw = "".join(block.text for block in response.content if block.type == "text")
        return raw, cost
