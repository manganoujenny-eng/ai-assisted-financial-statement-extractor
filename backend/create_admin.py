"""Administrator accounts — managed here, directly in the database.

The administrator runs the system from the screens (Administration area:
users, audit log, campaigns, data), but nobody can create, change or delete
an administrator from the screens. This script does it. Run it from the
backend/ directory, with the same venv Flask uses:

    python create_admin.py                    create an administrator
    python create_admin.py --reset USERNAME   new temporary password
    python create_admin.py --deactivate USERNAME
    python create_admin.py --activate USERNAME
    python create_admin.py --list             who the administrators are

A new account (or a reset) gets a TEMPORARY password: type one, or press
Enter and a random one is generated and printed ONCE. Sign in with it and
change it on My account. Passwords are stored hashed, never in clear.
Every change made here is written to the audit log, author "create_admin.py".
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

AUTHOR = "create_admin.py"


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


def admin_named(service: UserService, username: str) -> E.User:
    user = service.users.get_by_username(username)
    if user is None or user.role != E.ROLE_ADMIN:
        sys.exit(f"No administrator with the username {username!r}.")
    return user


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage administrator accounts in the database.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--reset", metavar="USERNAME", help="give an administrator a new temporary password")
    group.add_argument("--deactivate", metavar="USERNAME", help="stop an administrator from signing in")
    group.add_argument("--activate", metavar="USERNAME", help="let a deactivated administrator sign in again")
    group.add_argument("--list", action="store_true", help="list the administrator accounts")
    args = parser.parse_args()

    engine = make_engine(database_url())
    Base.metadata.create_all(engine)  # creates the tables that do not exist yet
    session = make_session_factory(engine)()
    service = UserService(SqlUserRepository(session), SqlAuditLog(session), SqlCaseRepository(session))

    if args.list:
        admins = [u for u in service.users.list() if u.role == E.ROLE_ADMIN]
        if not admins:
            print("  No administrator yet: run  python create_admin.py")
        for user in admins:
            state = "active" if user.active else "deactivated"
            print(f"  {user.username:<20} {user.full_name:<30} {state}")
        return

    if args.reset or args.deactivate or args.activate:
        user = admin_named(service, args.reset or args.deactivate or args.activate)
        if args.reset:
            user.password_hash = generate_password_hash(temporary_password())
            change = {"password": "reset"}
        else:
            user.active = bool(args.activate)
            change = {"active": user.active}
        service.users.save(user)
        service.audit.record(
            E.AuditEntry(entity="User", entity_id=user.id, action="USER_UPDATED",
                         author=AUTHOR, detail=change)
        )
        print(f"Done: {user.full_name} ({user.username}).")
        return

    print("New administrator account.")
    username = input("  Username (to sign in, no spaces): ").strip()
    full_name = input("  Full name (shown on every record): ").strip()
    password = temporary_password()
    user = service.create(
        username, full_name, E.ROLE_ADMIN, password, author=AUTHOR, allow_admin=True
    )
    print(
        f"Administrator {user.full_name!r} created (username {user.username!r}).\n"
        "Sign in with the temporary password and change it on My account."
    )


if __name__ == "__main__":
    main()