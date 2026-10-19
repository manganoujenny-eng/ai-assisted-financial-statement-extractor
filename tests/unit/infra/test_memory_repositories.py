"""The in-memory repositories implement the same ports as the SQL ones
(``app/infra/db/memory.py``'s own docstring: "Same ports as the SQLAlchemy
ones, no database"). That promise only holds if the two adapters actually
agree on behaviour, not just on method signatures — and they drifted once
already: SqlDatasetRepository.find_by_extraction was fixed to return the
most recently validated row when an extraction has more than one (reopen ->
correct -> re-validate keeps the earlier snapshot rather than deleting it),
but the in-memory twin was left returning whichever row happened to come
first. This file is the test that would have caught that drift.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.domain import entities as E
from app.infra.db.memory import InMemoryDatasetRepository


def test_find_by_extraction_returns_the_most_recently_validated_dataset():
    datasets = InMemoryDatasetRepository()

    older = E.ValidatedDataset(
        extraction_id="run-1",
        validated_by="franky",
        amounts={"BK": "100"},
        validated_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    newer = E.ValidatedDataset(
        extraction_id="run-1",
        validated_by="priscille",
        amounts={"BK": "200"},
        validated_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
    )

    # Added in the order a repository might plausibly return them in, i.e.
    # not already sorted — the point is that find_by_extraction must sort
    # them itself rather than trust insertion order.
    datasets.add(older)
    datasets.add(newer)

    found = datasets.find_by_extraction("run-1")

    assert found is not None
    assert found.id == newer.id, (
        "find_by_extraction must pick the dataset with the latest "
        "validated_at, not merely the first one added for this extraction"
    )
    assert found.validated_by == "priscille"