"""The super administrator — created ONCE, here, directly in the database.

There is exactly one super administrator. It does everything an
administrator does, and it is the only account that manages the
administrators from the screens (Users page: add, rename, reset,
deactivate, reactivate, delete). Nobody can create, change or delete the
super administrator from the screens. Run this from the backend/ directory,
with the same venv Flask uses:

    python create_superadmin.py            create it (refused if one exists)
    python create_superadmin.py --reset    new temporary password (lost password)
    python create_superadmin.py --show     who it is

The account (or a reset) gets a TEMPORARY password: type one, or press
Enter and a random one is generated and printed ONCE. Sign in with it and
change it on My account. Passwords are stored hashed, never in clear.
Every change made here is written to the audit log, author
"create_superadmin.py".
"""

from __future__ import annotations

import argparse
import getpass
import secrets
import sys

from dotenv import load_dotenv

load_dotenv()

from werkzeug.security import generate_password_hash  # noqa: E402

from app.domain import entities as E  # noqa: E402
from app.infra.db.models import Base  # noqa: E402
from app.infra.db.repositories import (  # noqa: E402
    SqlAuditLog,
    SqlCaseRepository,
    SqlUserRepository,
)
from app.infra.db.session import database_url, make_engine, make_session_factory  # noqa: E402
from app.services.user_service import MIN_PASSWORD_LENGTH, UserService  # noqa: E402

AUTHOR = "create_superadmin.py"


def temporary_password() -> str:
    typed = getpass.getpass(
        f"  Temporary password ({MIN_PASSWORD_LENGTH}+ characters, Enter = generate one): "
    )
    if not typed:
        generated = secrets.token_urlsafe(9)
        print(f"  Generated temporary password (shown ONLY now): {generated}")
        return generated
    if typed != getpass.getpass("  Repeat it: "):
        sys.exit("  The two passwords differ — nothing was changed.")
    return typed


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the one super administrator.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--reset", action="store_true", help="give it a new temporary password")
    group.add_argument("--show", action="store_true", help="show who the super administrator is")
    args = parser.parse_args()

    engine = make_engine(database_url())
    Base.metadata.create_all(engine)  # creates the tables that do not exist yet
    session = make_session_factory(engine)()
    service = UserService(SqlUserRepository(session), SqlAuditLog(session), SqlCaseRepository(session))
    existing = next((u for u in service.users.list() if u.is_superadmin), None)

    if args.show:
        if existing is None:
            print("  No super administrator yet: run  python create_superadmin.py")
        else:
            state = "active" if existing.active else "deactivated"
            print(f"  {existing.username:<20} {existing.full_name:<30} {state}")
        return

    if args.reset:
        if existing is None:
            sys.exit("No super administrator yet: run  python create_superadmin.py")
        existing.password_hash = generate_password_hash(temporary_password())
        existing.active = True  # a reset also lets a locked-out account back in
        service.users.save(existing)
        service.audit.record(
            E.AuditEntry(entity="User", entity_id=existing.id, action="USER_UPDATED",
                         author=AUTHOR, detail={"password": "reset"})
        )
        print(f"Done: {existing.full_name} ({existing.username}).")
        return

    if existing is not None:
        sys.exit(
            f"A super administrator already exists: {existing.full_name} "
            f"({existing.username}). There is only one. Lost password? "
            "python create_superadmin.py --reset"
        )
    print("The super administrator account (created once).")
    username = input("  Username (to sign in, no spaces): ").strip()
    full_name = input("  Full name (shown on every record): ").strip()
    password = temporary_password()
    user = service.create(
        username, full_name, E.ROLE_SUPERADMIN, password, author=AUTHOR, allow_superadmin=True
    )
    print(
        f"Super administrator {user.full_name!r} created (username {user.username!r}).\n"
        "Sign in with the temporary password and change it on My account."
    )


if __name__ == "__main__":
    main()
