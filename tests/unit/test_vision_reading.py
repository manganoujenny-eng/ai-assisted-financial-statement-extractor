"""Reading a scanned PDF with the language model, from images of its pages.

When OCR cannot read a scan (skewed, blurred, low resolution), the analyst
can ask the model to read the page images directly ("Read with AI"). Same
discipline as the text structurer: strict schema, one retry, cost counted,
budget capped, answer cached so the same pages are never paid twice.

No network: the Anthropic client is mocked.
"""

import json
from decimal import Decimal
from unittest.mock import Mock, patch

import fitz
import pytest

from app.infra.llm.cache import ResponseCache
from app.infra.llm.claude_vision import ClaudeVisionStructurer

ANSWER = {"items": [
    {"item_code": "BZ", "amount": "11246235", "year": "N", "source_page": 1, "confidence": 0.9},
    {"item_code": "XI", "amount": "1000000", "year": "N", "source_page": 2, "confidence": 0.8},
]}


def _response(text, stop_reason="end_turn"):
    response = Mock()
    response.content = [Mock(type="thinking", thinking=""), Mock(type="text", text=text)]
    response.stop_reason = stop_reason
    response.usage.input_tokens = 1_000_000
    response.usage.output_tokens = 100_000
    return response


def _scan(path, pages=2):
    """A small PDF whose pages carry no text layer — like a scan."""
    doc = fitz.open()
    for number in range(pages):
        page = doc.new_page(width=595, height=842)
        page.draw_rect(fitz.Rect(50, 50 + number * 10, 300, 120), color=(0, 0, 0), fill=(0.8, 0.8, 0.8))
    doc.save(path)
    return str(path)


def test_the_page_images_are_sent_and_the_answer_parsed(tmp_path):
    vision = ClaudeVisionStructurer(api_key="k", cache=ResponseCache(tmp_path / "cache"))
    with patch("anthropic.Anthropic") as client:
        client.return_value.messages.create.return_value = _response(json.dumps(ANSWER))
        result = vision.structure_file(_scan(tmp_path / "scan.pdf"))

    content = client.return_value.messages.create.call_args.kwargs["messages"][0]["content"]
    images = [block for block in content if block["type"] == "image"]
    assert len(images) == 2
    assert images[0]["source"]["type"] == "base64" and images[0]["source"]["media_type"] == "image/png"
    assert content[-1]["type"] == "text" and "page images" in content[-1]["text"]
    assert result.engine == "LLM_VISION" and result.prompt_version == "vision-v1"
    assert [(i.item_code, i.amount, i.source_page) for i in result.items] == [
        ("BZ", "11246235", 1), ("XI", "1000000", 2)]
    assert result.cost_usd == Decimal("6.00")  # $4 in, $20 out per million


def test_the_same_pages_are_never_paid_twice(tmp_path):
    vision = ClaudeVisionStructurer(api_key="k", cache=ResponseCache(tmp_path / "cache"))
    path = _scan(tmp_path / "scan.pdf")
    with patch("anthropic.Anthropic") as client:
        client.return_value.messages.create.return_value = _response(json.dumps(ANSWER))
        vision.structure_file(path)
        again = vision.structure_file(path)
    assert client.return_value.messages.create.call_count == 1
    assert again.cost_usd == Decimal("0")


def test_long_scans_are_cut_to_the_page_limit(tmp_path):
    vision = ClaudeVisionStructurer(api_key="k", cache=ResponseCache(tmp_path / "cache"), max_pages=3)
    with patch("anthropic.Anthropic") as client:
        client.return_value.messages.create.return_value = _response(json.dumps(ANSWER))
        vision.structure_file(_scan(tmp_path / "long.pdf", pages=5))
    content = client.return_value.messages.create.call_args.kwargs["messages"][0]["content"]
    assert len([b for b in content if b["type"] == "image"]) == 3


def test_a_bad_answer_is_retried_once_then_refused(tmp_path):
    vision = ClaudeVisionStructurer(api_key="k", cache=ResponseCache(tmp_path / "cache"))
    with patch("anthropic.Anthropic") as client:
        client.return_value.messages.create.return_value = _response('{"nope": 1}')
        with pytest.raises(ValueError, match="after one retry"):
            vision.structure_file(_scan(tmp_path / "scan.pdf"))
    assert client.return_value.messages.create.call_count == 2
