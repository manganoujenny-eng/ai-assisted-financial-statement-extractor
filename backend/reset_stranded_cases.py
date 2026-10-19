"""One-time companion to drop_old_extraction_tables.py.

Dropping the extraction tables deleted every run, but cases that had already
reached EXTRACTED / UNDER_REVIEW / VALIDATED / ANALYSED still carry that
status, with nothing behind it. This puts every case that has NO extraction
run back to CREATED, so "Extract documents" works on it again.

Cases and documents are not touched or deleted, only their status.

Run once from backend/, after drop_old_extraction_tables.py and after the
backend has been restarted at least once (so the new tables exist):

    python reset_stranded_cases.py
"""

from app.infra.db.session import database_url, make_engine
from sqlalchemy import text

engine = make_engine(database_url())

with engine.begin() as conn:
    result = conn.execute(
        text(
            "UPDATE analysis_case SET status = 'CREATED' "
            "WHERE status <> 'CREATED' "
            "AND id NOT IN (SELECT case_id FROM extraction_run)"
        )
    )

print(f"Reset {result.rowcount} case(s) to CREATED.")