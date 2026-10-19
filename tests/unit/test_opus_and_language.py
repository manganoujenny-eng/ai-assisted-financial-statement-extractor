"""Opus 5.5 call shape and the commentary language.

No network: the Anthropic client is mocked. What is checked is what the
code sends (model, effort, no sampling parameters) and how it reads the
answer (text blocks by type, refusal and max_tokens stop reasons).
"""

import io
import json
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

from app import create_app
from app.config import Config
from app.domain.ports import AnalysisDraft, RawDocument
from app.infra.llm.cache import ResponseCache
from app.infra.llm.claude_analyst import ClaudeAnalyst
from app.infra.llm.claude_structurer import ClaudeStructurer

SECTIONS = {
    "overview": "Vue d'ensemble.",
    "ratios": [{"code": "R1", "commentary": "Commentaire."}],
    "checks": "Contrôles.",
    "comparison": "Aucune comparaison.",
    "attention": ["Point."],
}


def _response(text, stop_reason="end_turn"):
    response = Mock()
    thinking = Mock(type="thinking", thinking="")
    response.content = [thinking, Mock(type="text", text=text)]  # thinking comes first
    response.stop_reason = stop_reason
    response.usage.input_tokens = 1_000_000
    response.usage.output_tokens = 100_000
    return response


def test_adapters_default_to_opus_5_5():
    assert ClaudeStructurer(api_key="k").model == "claude-opus-5-5"
    assert ClaudeAnalyst(api_key="k", model="claude-opus-5-5").model == "claude-opus-5-5"


def test_analyst_writes_in_the_requested_language_and_sends_no_sampling_params():
    analyst = ClaudeAnalyst(api_key="k", model="claude-opus-5-5", effort="low")
    payload = {"items": [], "ratios": [{"code": "R1"}], "language": "fr"}
    with patch("anthropic.Anthropic") as client:
        client.return_value.messages.create.return_value = _response(json.dumps(SECTIONS))
        draft = analyst.write(payload)

    kwargs = client.return_value.messages.create.call_args.kwargs
    assert kwargs["model"] == "claude-opus-5-5"
    assert kwargs["output_config"] == {"effort": "low"}
    for forbidden in ("temperature", "top_p", "top_k", "thinking"):
        assert forbidden not in kwargs
    prompt = kwargs["messages"][0]["content"]
    assert "Write every text value in French" in prompt
    assert '"language"' not in prompt  # not a figure, not sent as one
    assert draft.prompt_version == "analysis-v2/fr"
    # $4 in + $20 out per million tokens: 1M in + 0.1M out = 6.00
    assert draft.cost_usd == Decimal("6.00")


def test_analyst_unknown_language_falls_back_to_english():
    analyst = ClaudeAnalyst(api_key="k", model="claude-opus-5-5")
    with patch("anthropic.Anthropic") as client:
        client.return_value.messages.create.return_value = _response(json.dumps(SECTIONS))
        draft = analyst.write({"ratios": [], "language": "xx"})
    assert "in English" in client.return_value.messages.create.call_args.kwargs["messages"][0]["content"]
    assert draft.prompt_version == "analysis-v2/en"


def test_analyst_refusal_is_an_explicit_failure():
    analyst = ClaudeAnalyst(api_key="k", model="claude-opus-5-5")
    with patch("anthropic.Anthropic") as client:
        client.return_value.messages.create.return_value = _response("", stop_reason="refusal")
        with pytest.raises(RuntimeError, match="declined"):
            analyst.write({"ratios": []})
    assert analyst.spent_usd > 0  # billed even though refused


def test_structurer_sends_effort_and_schema_and_handles_max_tokens(tmp_path):
    document = RawDocument(file_type="pdf", document_type="balance_sheet", pages_text=["BK 1"])
    good = json.dumps({"items": [{"item_code": "BK", "amount": "1", "year": "N",
                                  "source_page": 1, "confidence": 0.9}]})
    # A fresh cache: the default one on disk may already hold this document.
    structurer = ClaudeStructurer(api_key="k", effort="low", cache=ResponseCache(tmp_path))
    with patch("app.infra.llm.claude_structurer.anthropic.Anthropic") as client:
        client.return_value.messages.create.side_effect = [
            _response("", stop_reason="max_tokens"),  # cut off: retried once
            _response(good),
        ]
        result = structurer.structure(document)

    assert [i.item_code for i in result.items] == ["BK"]
    kwargs = client.return_value.messages.create.call_args.kwargs
    assert kwargs["output_config"]["effort"] == "low"
    assert kwargs["output_config"]["format"]["type"] == "json_schema"
    assert "temperature" not in kwargs
    # Both calls are counted: 2 x $6.00
    assert structurer.spent_usd == Decimal("12.00")


class _Writer:
    def __init__(self):
        self.payloads = []

    def write(self, payload):
        self.payloads.append(payload)
        return AnalysisDraft(
            sections={k: v for k, v in SECTIONS.items() if k != "ratios"} | {"ratios": []},
            model="m",
            prompt_version=f"analysis-v2/{payload.get('language')}",
            cost_usd=Decimal("0"),
        )


@pytest.fixture
def app_with_writer(tmp_path, balanced_amounts):
    from integration.test_api_end_to_end import FakeReader, FakeTwoYearStructurer

    app = create_app(Config(storage="memory", upload_dir=tmp_path))
    c = app.config["container"]
    c.extraction.readers = [FakeReader()]
    c.extraction.structurer = FakeTwoYearStructurer(balanced_amounts, balanced_amounts)
    writer = _Writer()
    c.insight.writer = writer
    return app, writer


def test_commentary_language_follows_the_screen(app_with_writer):
    app, writer = app_with_writer
    http = app.test_client()
    case_id = http.post("/api/cases", json={"client": "A", "fiscal_year": 2024}).get_json()["id"]
    http.post(
        f"/api/cases/{case_id}/documents",
        data={"file": (io.BytesIO(b"%PDF-1.7 x"), "s.pdf")},
        content_type="multipart/form-data",
    )
    run_id = http.post(f"/api/cases/{case_id}/extractions").get_json()["id"]
    http.post(f"/api/cases/{case_id}/submission")
    dataset = http.post(f"/api/extractions/{run_id}/validation", json={}).get_json()

    body = http.post(
        f"/api/datasets/{dataset['id']}/analysis", headers={"Accept-Language": "fr"}
    ).get_json()
    assert writer.payloads[-1]["language"] == "fr"
    assert body["ai_analysis"]["language"] == "fr"

    again = http.post(
        f"/api/cases/{case_id}/ai-analysis", json={}, headers={"Accept-Language": "en"}
    ).get_json()
    assert writer.payloads[-1]["language"] == "en"
    assert again["language"] == "en"