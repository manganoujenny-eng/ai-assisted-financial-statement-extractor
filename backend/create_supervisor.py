"""Supervisor accounts — managed here, directly in the database.

A supervisor cannot create, change, deactivate or delete another supervisor
from the screens (see services/user_service.py). Supervisor accounts are
therefore handled with this script, by whoever administers the server.
Run it from the backend/ directory, with the same venv Flask uses:

    python create_supervisor.py                    create a supervisor
    python create_supervisor.py --reset USERNAME   new temporary password
    python create_supervisor.py --deactivate USERNAME
    python create_supervisor.py --activate USERNAME
    python create_supervisor.py --list             who the supervisors are

A new account (or a reset) gets a TEMPORARY password: type one, or press
Enter and a random one is generated and printed ONCE. Give it to the
person; they sign in and change it — and their name if needed — on
My account. Passwords are stored hashed, never in clear.
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

AUTHOR = "create_supervisor.py"


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


def supervisor_named(service: UserService, username: str) -> E.User:
    user = service.users.get_by_username(username)
    if user is None or user.role != E.ROLE_SUPERVISOR:
        sys.exit(f"No supervisor with the username {username!r}.")
    return user


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage supervisor accounts in the database.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--reset", metavar="USERNAME", help="give a supervisor a new temporary password")
    group.add_argument("--deactivate", metavar="USERNAME", help="stop a supervisor from signing in")
    group.add_argument("--activate", metavar="USERNAME", help="let a deactivated supervisor sign in again")
    group.add_argument("--list", action="store_true", help="list the supervisor accounts")
    args = parser.parse_args()

    engine = make_engine(database_url())
    Base.metadata.create_all(engine)  # creates app_user if it does not exist yet
    session = make_session_factory(engine)()
    service = UserService(SqlUserRepository(session), SqlAuditLog(session), SqlCaseRepository(session))

    if args.list:
        for user in service.users.list():
            if user.role == E.ROLE_SUPERVISOR:
                state = "active" if user.active else "deactivated"
                print(f"  {user.username:<20} {user.full_name:<30} {state}")
        return

    if args.reset or args.deactivate or args.activate:
        user = supervisor_named(service, args.reset or args.deactivate or args.activate)
        if args.reset:
            user.password_hash = generate_password_hash(temporary_password())
            change, action = {"password": "reset"}, "USER_UPDATED"
        else:
            active = bool(args.activate)
            if not active and not any(
                u.id != user.id and u.active and u.role == E.ROLE_SUPERVISOR
                for u in service.users.list()
            ):
                sys.exit("This is the last active supervisor — create another one first.")
            user.active = active
            change, action = {"active": active}, "USER_UPDATED"
        service.users.save(user)
        service.audit.record(
            E.AuditEntry(entity="User", entity_id=user.id, action=action, author=AUTHOR, detail=change)
        )
        print(f"Done: {user.full_name} ({user.username}).")
        return

    print("New supervisor account.")
    username = input("  Username (to sign in, no spaces): ").strip()
    full_name = input("  Full name (shown on every record): ").strip()
    password = temporary_password()
    user = service.create(
        username, full_name, E.ROLE_SUPERVISOR, password, author=AUTHOR, allow_supervisor=True
    )
    print(
        f"Supervisor {user.full_name!r} created (username {user.username!r}).\n"
        "Ask them to sign in and change the temporary password on My account."
    )


if __name__ == "__main__":
    main()