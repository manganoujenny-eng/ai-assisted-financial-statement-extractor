"""One-time setup for item 5 (users, roles, sign-in). Safe to run again.

Run it ONCE, from the backend/ directory, with the same venv Flask uses,
BEFORE restarting the backend with the item-5 code (once sign-in is on,
nobody can use the app until a user exists):

    python add_users_schema.py

What it does:
1. creates the ``app_user`` table;
2. if there is no supervisor yet, asks for the first one (username, full
   name, password — typed here, never shown or stored in clear);
3. creates an ANALYST account for every analyst name already recorded on a
   case (from item 4), with a temporary password printed ONCE below. Give
   each person theirs; they change it after signing in (or a supervisor
   resets it on the Users page).

Nothing is deleted. Each case keeps its analyst name, which is now that
user's full name; only differences of spacing or capitals between cases
("helena " / "Helena") are aligned to one spelling.
"""

from __future__ import annotations

import getpass
import re
import secrets

from dotenv import load_dotenv
from sqlalchemy import select

load_dotenv()

from app.domain import entities as E  # noqa: E402
from app.infra.db.models import AnalysisCaseRow, Base  # noqa: E402
from app.infra.db.repositories import (  # noqa: E402
    SqlAuditLog,
    SqlCaseRepository,
    SqlUserRepository,
)
from app.infra.db.session import database_url, make_engine, make_session_factory  # noqa: E402
from app.services.user_service import UserService  # noqa: E402


def username_for(full_name: str, taken: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", ".", full_name.lower()).strip(".") or "analyst"
    candidate, n = base, 2
    while candidate in taken:
        candidate, n = f"{base}{n}", n + 1
    taken.add(candidate)
    return candidate


def create_users_for_case_analysts(session, service: UserService) -> list[tuple[str, str, str]]:
    """Returns [(full_name, username, temporary_password)] for accounts created."""
    users = service.users.list()
    existing = {u.full_name.casefold() for u in users}
    taken = {u.username.lower() for u in users}
    names = sorted(
        {
            " ".join(name.split())
            for name in session.scalars(select(AnalysisCaseRow.analyst)).all()
            if name and name.strip()
        },
        key=str.casefold,
    )
    created = []
    for name in names:
        if name.casefold() in existing:
            continue
        username = username_for(name, taken)
        password = secrets.token_urlsafe(9)
        service.create(username, name, E.ROLE_ANALYST, password, author="setup script")
        existing.add(name.casefold())
        created.append((name, username, password))
    return created


def align_case_analyst_names(session, service: UserService) -> int:
    """'helena ' / 'Helena' typed on different cases -> the user's exact
    full name, so every screen groups them as one person. Only spacing and
    capitalisation differ; a name matching no user is left as it is."""
    by_key = {u.full_name.casefold(): u.full_name for u in service.users.list()}
    changed = 0
    for row in session.scalars(select(AnalysisCaseRow)).all():
        if not row.analyst:
            continue
        target = by_key.get(" ".join(row.analyst.split()).casefold())
        if target and row.analyst != target:
            row.analyst = target
            changed += 1
    session.commit()
    return changed


def main() -> None:
    engine = make_engine(database_url())
    Base.metadata.create_all(engine)
    session = make_session_factory(engine)()
    service = UserService(
        SqlUserRepository(session), SqlAuditLog(session), SqlCaseRepository(session)
    )

    if not any(u.role == E.ROLE_SUPERVISOR and u.active for u in service.users.list()):
        print("No supervisor yet — create the first one.")
        username = input("  Username (to sign in, no spaces): ").strip()
        full_name = input("  Full name (shown on every record): ").strip()
        while True:
            password = getpass.getpass("  Password (8+ characters): ")
            if password == getpass.getpass("  Repeat the password: "):
                break
            print("  The two passwords differ — try again.")
        service.create(username, full_name, E.ROLE_SUPERVISOR, password, author="setup script")
        print(f"Supervisor {full_name!r} created.")
    else:
        print("A supervisor already exists.")

    created = create_users_for_case_analysts(session, service)
    if created:
        print("\nAnalyst accounts created from the names already on cases.")
        print("Temporary passwords — shown ONLY now, give each person theirs:\n")
        for full_name, username, password in created:
            print(f"  {full_name:<30} username: {username:<20} password: {password}")
    else:
        print("No new analyst account needed.")
    aligned = align_case_analyst_names(session, service)
    if aligned:
        print(f"Aligned the analyst name on {aligned} case(s) with the user's full name.")
    print("\nDone. Set SECRET_KEY in .env if not done yet, then restart the backend.")


if __name__ == "__main__":
    main()