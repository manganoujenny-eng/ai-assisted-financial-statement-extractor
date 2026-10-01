from types import SimpleNamespace

from app.services.extraction_service import ExtractionService

def test_to_fields_records_rejected_items():
    structured = SimpleNamespace(
        items=[
            SimpleNamespace(
                item_code="BK",
                amount="6746235223",
                year="N",
                source_page=1,
                confidence=0.95,
            ),
            SimpleNamespace(
                item_code="BKK",
                amount="123456",
                year="N",
                source_page=1,
                confidence=0.50,
            ),
            SimpleNamespace(
                item_code="CP",
                amount="not-a-number",
                year="N",
                source_page=1,
                confidence=0.40,
            ),
        ]
    )

    service = object.__new__(ExtractionService)

    fields , rejections = service._to_fields("run-001", structured)

    assert len(fields) == 1
    assert fields[0].item_code == "BK"
    assert fields[0].amount.value == 6746235223

    assert len(rejections) == 2

    assert rejections[0].reason == "invalid item code"
    assert rejections[0].raw_item.item_code == "BKK"

    assert rejections[1].reason.startswith("invalid amount")
    assert rejections[1].raw_item.item_code == "CP"