import json
from decimal import Decimal
from unittest.mock import Mock, patch
from app.infra.llm.cache import ResponseCache

from app.domain.ports import RawDocument
from app.infra.llm.claude_structurer import ClaudeStructurer


def test_claude_structurer_parses_fake_response():
    document = RawDocument(
        file_type="pdf",
        document_type="balance_sheet",
        pages_text=[
            "TOTAL ACTIF CIRCULANT BK 6 746 235 223"
        ],
    )

    fake_response = Mock()
    fake_response.content = [
        Mock(
            type="text",
            text=json.dumps(
                {
                    "items": [
                        {
                            "item_code": "BK",
                            "amount": "6746235223",
                            "year": "N",
                            "source_page": 1,
                            "confidence": 0.95,
                        }
                    ]
                }
            ),
        )
    ]

    fake_response.usage.input_tokens = 1000
    fake_response.usage.output_tokens = 100

    structurer = ClaudeStructurer(
        api_key="fake-key"
    )

    with patch(
        "app.infra.llm.claude_structurer.anthropic.Anthropic"
    ) as mock_anthropic:

        mock_anthropic.return_value.messages.create.return_value = fake_response

        result = structurer.structure(document)

    assert len(result.items) == 1
    assert result.items[0].item_code == "BK"
    assert result.items[0].amount == "6746235223"
    assert result.items[0].year == "N"
    assert result.items[0].source_page == 1
    assert result.items[0].confidence == Decimal("0.95")

def test_claude_structurer_retries_after_invalid_response(tmp_path):
        document = RawDocument(
            file_type="pdf",
            document_type="balance_sheet",
            pages_text=[
                "TOTAL CAPITAUX PROPRES CP 3 500 000 000"
            ],
        )

        invalid_response = Mock()
        invalid_response.content = [
            Mock(
                type="text",
                text='{"items": [invalid json',
            )
        ]
        invalid_response.usage.input_tokens = 1000
        invalid_response.usage.output_tokens = 100

        valid_response = Mock()
        valid_response.content = [
            Mock(
                type="text",
                text=json.dumps(
                    {
                        "items": [
                            {
                                "item_code": "CP",
                                "amount": "3500000000",
                                "year": "N",
                                "source_page": 1,
                                "confidence": 0.95,
                            }
                        ]
                    }
                ),
            )
        ]
        valid_response.usage.input_tokens = 1000
        valid_response.usage.output_tokens = 100

        structurer = ClaudeStructurer(
            api_key="fake-key",
            cache=ResponseCache(tmp_path)
        )

        with patch(
                "app.infra.llm.claude_structurer.anthropic.Anthropic"
        ) as mock_anthropic:
            mock_client = mock_anthropic.return_value

            mock_client.messages.create.side_effect = [
                invalid_response,
                valid_response,
            ]

            result = structurer.structure(document)

        assert len(result.items) == 1
        assert result.items[0].item_code == "CP"
        assert result.items[0].amount == "3500000000"

        assert mock_client.messages.create.call_count == 2