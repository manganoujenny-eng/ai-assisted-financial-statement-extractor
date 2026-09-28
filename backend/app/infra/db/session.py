"""Engine and session factory.

Default: SQLite in a local file. Not because SQLite is the target — the
dossier's data model is PostgreSQL and you already have a schema running —
but because the prototype must install "in under thirty minutes" (NFR-05) on
a workstation, and a demonstration in front of a jury must not depend on a
database service having started that morning.

Point ``DATABASE_URL`` at PostgreSQL whenever you want it:

    DATABASE_URL=postgresql+psycopg://postgres:...@localhost:5432/financial_analysis
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base

DEFAULT_SQLITE_PATH = Path(__file__).resolve().parents[4] / "data" / "prototype.db"


def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    DEFAULT_SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{DEFAULT_SQLITE_PATH}"


def make_engine(url: str | None = None, echo: bool = False):
    return create_engine(url or database_url(), echo=echo, future=True)


def make_session_factory(engine=None) -> sessionmaker[Session]:
    return sessionmaker(bind=engine or make_engine(), expire_on_commit=False)


def create_schema(engine) -> None:
    """Create the tables if they are absent.

    Fine for a prototype. Not fine for anything that will carry real data:
    the moment a schema change has to be applied to a database someone else
    is using, you need migrations (Alembic), because ``create_all`` never
    alters an existing table and will leave you wondering why your new column
    is missing. Worth knowing now; not worth installing this week.
    """
    Base.metadata.create_all(engine)
