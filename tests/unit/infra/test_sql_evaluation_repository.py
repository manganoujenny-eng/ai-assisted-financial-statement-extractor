"""Exercise 20 — stored campaigns, against a real (SQLite) database.

A campaign is written once and read back exactly as it was measured: the
summary, the fingerprints of its input files, and one row per package with
the headline figures in their own columns (so they can be queried in SQL).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select

from app.domain import entities as E
from app.infra.db.memory import InMemoryEvaluationRepository
from app.infra.db.models import EvaluationCampaignRow, EvaluationPackageRow
from app.infra.db.repositories import SqlEvaluationRepository
from app.infra.db.session import create_schema, make_engine, make_session_factory
from app.services.corpus_campaign import CampaignResult, PackageResult, to_entity


def _session():
    engine = make_engine("sqlite:///:memory:")
    create_schema(engine)
    return make_session_factory(engine)()


def _campaign() -> E.EvaluationCampaign:
    package = PackageResult(
        package="RP001", documents=["ETAT_FINANCIER_TEST1.pdf"],
        annotation="annotation_RP001.xlsx", status="EVALUATED",
        judged_fields=14, wrong_fields=[{"code": "XB", "truth": "10", "extracted": "11"}],
        ratios=5, wrong_ratios=[{"code": "R4"}],
        field_accuracy=Decimal(13) / Decimal(14), ratio_accuracy=Decimal("0.8"),
        amplification=Decimal("2.80"), silent_false_positives=["XB"],
    )
    result = CampaignResult(corpus="data/corpus", engine="RULE_BASED", packages=[package],
                            inputs={"RP001/annotation_RP001.xlsx": "ab" * 32})
    return to_entity(result, author="Helena Ndongo", note="first run")


def test_a_campaign_is_read_back_as_it_was_stored():
    session = _session()
    repo = SqlEvaluationRepository(session)
    campaign = _campaign()
    repo.add(campaign)
    session.expire_all()

    back = repo.get(campaign.id)
    assert back.kind == E.CAMPAIGN_CORPUS
    assert back.author == "Helena Ndongo" and back.note == "first run"
    assert back.summary == campaign.summary
    assert back.inputs == {"RP001/annotation_RP001.xlsx": "ab" * 32}
    assert [p["package"] for p in back.packages] == ["RP001"]
    assert back.packages[0]["silent_false_positives"] == ["XB"]


def test_the_headline_figures_have_their_own_columns():
    session = _session()
    repo = SqlEvaluationRepository(session)
    campaign = _campaign()
    repo.add(campaign)

    row = session.get(EvaluationCampaignRow, campaign.id)
    assert row.packages_count == 1 and row.evaluated_count == 1
    assert Decimal(str(row.field_accuracy)) == Decimal("0.928571")
    assert Decimal(str(row.amplification)) == Decimal("2.80")
    assert row.silent_count == 1
    package = session.scalars(select(EvaluationPackageRow)).one()
    assert (package.package, package.wrong_fields, package.wrong_ratios) == ("RP001", 1, 1)


def test_campaigns_are_listed_newest_first_and_filtered_by_kind():
    # Explicit times: on Windows two campaigns created one after the other
    # can get the very same clock reading, and then "newest" is undecided.
    for repo in (SqlEvaluationRepository(_session()), InMemoryEvaluationRepository()):
        first = _campaign()
        first.run_at = datetime(2026, 10, 20, 9, 0)
        second = E.EvaluationCampaign(kind=E.CAMPAIGN_SENSITIVITY, summary={"cells": []},
                                      run_at=datetime(2026, 10, 21, 9, 0))
        repo.add(first)
        repo.add(second)
        assert [c.id for c in repo.list()] == [second.id, first.id]
        assert [c.id for c in repo.list(E.CAMPAIGN_CORPUS)] == [first.id]
        assert repo.get("unknown") is None


def test_a_campaign_is_deleted_with_its_packages():
    session = _session()
    for repo in (SqlEvaluationRepository(session), InMemoryEvaluationRepository()):
        kept, gone = _campaign(), _campaign()
        repo.add(kept)
        repo.add(gone)
        assert repo.delete(gone.id) is True
        assert repo.get(gone.id) is None
        assert [c.id for c in repo.list()] == [kept.id]
        assert repo.delete("unknown") is False
        if isinstance(repo, SqlEvaluationRepository):
            # its package rows went with it, the other campaign's stayed
            rows = session.scalars(select(EvaluationPackageRow)).all()
            assert [r.campaign_id for r in rows] == [kept.id]