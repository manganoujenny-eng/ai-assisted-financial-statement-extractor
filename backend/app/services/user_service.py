"""UserService — accounts, passwords and roles .

Passwords are hashed with Werkzeug's ``generate_password_hash`` (salted,
slow by design; Werkzeug ships with Flask, so nothing new to install). The
plain password exists only for the duration of one call: it is never
stored, logged, put in the audit or returned by the API.

The rules that protect the system from locking itself out live here, not in
the routes: the last active supervisor cannot be demoted or deactivated,
and nobody can deactivate themselves.

Who manages whom:
* the SUPER ADMINISTRATOR (exactly one, created once with
  ``backend/create_superadmin.py``) adds, edits, resets, deactivates,
  reactivates and deletes ADMINISTRATORS, and does everything an
  administrator does; nobody manages the super administrator from the
  screens;
* the ADMINISTRATOR adds, edits, resets, deactivates, reactivates and
  deletes SUPERVISORS and ANALYSTS (Users page of the admin area);
* a supervisor does the same for ANALYSTS only — never for another
  supervisor, and never for an administrator;
* an administrator never manages another administrator; administrator
  accounts are created by the super administrator (or with
  ``backend/create_admin.py``), and each administrator manages their own
  name and password on My account (as every user does);
* nobody can change a role from the screens: a role is chosen when the
  account is created.
"""

from __future__ import annotations

from werkzeug.security import check_password_hash, generate_password_hash

from ..domain import entities as E
from ..domain.ports import AuditLog, CaseRepository, UserRepository

MIN_PASSWORD_LENGTH = 8


class AuthenticationFailed(Exception):
    """Wrong username or password, or an inactive account. One message for
    all three on purpose: the screen must not reveal which usernames exist."""


class UserService:
    def __init__(
        self, users: UserRepository, audit: AuditLog, cases: CaseRepository | None = None,
        archive=None,
    ) -> None:
        self.users = users
        self.audit = audit
        self.cases = cases
        #: ArchiveService: a deleted account is kept there, so the
        #: administrator can restore it (None: no archive, e.g. the scripts).
        self.archive = archive

    def _remove(self, user: E.User, author: E.User) -> None:
        """Delete the account — after keeping a copy in the archive."""
        if self.archive is not None:
            self.archive.keep_user(user, author.full_name)
        self.users.delete(user.id)

    # --- signing in -------------------------------------------------------
    def authenticate(self, username: str, password: str) -> E.User:
        user = self.users.get_by_username(username or "")
        if (
            user is None
            or not user.active
            or not check_password_hash(user.password_hash, password or "")
        ):
            self.audit.record(
                E.AuditEntry(
                    entity="User",
                    entity_id=user.id if user else "-",
                    action="LOGIN_FAILED",
                    author=(username or "")[:100] or "-",
                )
            )
            raise AuthenticationFailed("wrong username or password")
        self.audit.record(
            E.AuditEntry(entity="User", entity_id=user.id, action="LOGIN", author=user.full_name)
        )
        return user

    # --- administration (supervisor or administrator — checked by the caller)
    def create(
        self,
        username: str,
        full_name: str,
        role: str,
        password: str,
        author: str,
        allow_supervisor: bool = False,
        allow_admin: bool = False,
        allow_superadmin: bool = False,
    ) -> E.User:
        """Add an account.

        * ANALYST: a supervisor or an administrator;
        * SUPERVISOR: an administrator (``allow_supervisor``);
        * ADMIN: the super administrator, or ``create_admin.py``
          (``allow_admin``);
        * SUPERADMIN: only ``create_superadmin.py`` (``allow_superadmin``),
          and only while there is none.
        """
        role = (role or E.ROLE_ANALYST).upper()
        if role not in E.ROLES:
            raise ValueError(f"role must be one of {E.ROLES}")
        if role == E.ROLE_SUPERADMIN:
            if not allow_superadmin:
                raise E.DomainError(
                    "the super administrator cannot be created from the screens — "
                    "use backend/create_superadmin.py"
                )
            if any(u.is_superadmin for u in self.users.list()):
                raise E.DomainError("a super administrator already exists — there is only one")
        if role == E.ROLE_ADMIN and not allow_admin:
            raise E.DomainError(
                "only the super administrator can add an administrator"
            )
        if role == E.ROLE_SUPERVISOR and not allow_supervisor:
            raise E.DomainError(
                "only the administrator can add a supervisor — a supervisor adds analysts"
            )
        username = (username or "").strip()
        full_name = " ".join((full_name or "").split())
        if not username or not full_name:
            raise ValueError("username and full name are required")
        if any(ch.isspace() for ch in username):
            raise ValueError("the username cannot contain spaces")
        if self.users.get_by_username(username) is not None:
            raise E.DomainError(f"the username {username!r} is already taken")
        if any(u.full_name.casefold() == full_name.casefold() for u in self.users.list()):
            raise E.DomainError(
                f"a user called {full_name!r} already exists — full names identify "
                "people on every record, so they must be unique"
            )
        _check_password(password)

        user = E.User(
            username=username,
            full_name=full_name,
            role=role,
            password_hash=generate_password_hash(password),
        )
        self.users.add(user)
        self.audit.record(
            E.AuditEntry(
                entity="User",
                entity_id=user.id,
                action="USER_CREATED",
                author=author,
                detail={"username": user.username, "full_name": user.full_name, "role": user.role},
            )
        )
        return user

    def update(
        self,
        user: E.User,
        author: E.User,
        full_name: str | None = None,
        role: str | None = None,
        active: bool | None = None,
        password: str | None = None,
    ) -> E.User:
        # The super administrator's account belongs to them alone.
        if user.is_superadmin and user.id != author.id:
            raise E.DomainError(
                "the super administrator's account is managed by its owner (My account) "
                "or with backend/create_superadmin.py"
            )
        # An administrator's account: that administrator, or the super
        # administrator.
        if user.is_admin and user.id != author.id and not author.is_superadmin:
            raise E.DomainError(
                "an administrator account is managed by its owner (My account) "
                "or by the super administrator"
            )
        # A supervisor's account: that supervisor, or the administrator.
        if user.is_supervisor and user.id != author.id and not author.is_admin:
            raise E.DomainError(
                "a supervisor cannot change another supervisor's account — "
                "only the administrator can"
            )
        # Roles are fixed where the account was created (Users page: analyst;
        # database: supervisor). Sending the current role is not a change.
        if role is not None and role.upper() != user.role:
            raise E.DomainError("roles cannot be changed from the screens")
        role = None
        changes: dict = {}

        if full_name is not None:
            full_name = " ".join(full_name.split())
            if not full_name:
                raise ValueError("the full name cannot be empty")
            if any(
                u.id != user.id and u.full_name.casefold() == full_name.casefold()
                for u in self.users.list()
            ):
                raise E.DomainError(f"a user called {full_name!r} already exists")
            if full_name != user.full_name:
                changes["full_name"] = [user.full_name, full_name]
                self._rename_case_owner(user.full_name, full_name)
                user.full_name = full_name

        if role is not None:
            role = role.upper()
            if role not in E.ROLES:
                raise ValueError(f"role must be one of {E.ROLES}")
            if role != user.role:
                if user.role == E.ROLE_SUPERVISOR:
                    self._keep_one_supervisor(user)
                changes["role"] = [user.role, role]
                user.role = role

        if active is not None and active != user.active:
            if not active:
                if user.id == author.id:
                    raise E.DomainError("you cannot deactivate your own account")
                if user.role == E.ROLE_SUPERVISOR:
                    self._keep_one_supervisor(user)
            changes["active"] = [user.active, active]
            user.active = active

        if password:
            _check_password(password)
            user.password_hash = generate_password_hash(password)
            changes["password"] = "reset"

        self.users.save(user)
        if changes:
            self.audit.record(
                E.AuditEntry(
                    entity="User",
                    entity_id=user.id,
                    action="USER_UPDATED",
                    author=author.full_name,
                    detail=changes,
                )
            )
        return user

    def delete(self, user: E.User, author: E.User) -> None:
        """Remove an account for good.

        * Never yourself, never the super administrator.
        * An administrator: the super administrator only.
        * An analyst (supervisor or administrator), only while no case
          carries their name: a case must keep a real owner. An analyst who
          already has cases is deactivated instead (they can no longer sign
          in, and every record they signed stays readable).
        * A supervisor (administrator only), never the last active one.
          Their name stays on every validation they signed; the cases
          assigned to them, or validated by them, open up to the other
          supervisors, exactly as when a supervisor is deactivated.
        """
        if user.id == author.id:
            raise E.DomainError("you cannot delete your own account")
        if user.is_superadmin:
            raise E.DomainError("the super administrator's account cannot be deleted from the screens")
        if user.is_admin:
            if not author.is_superadmin:
                raise E.DomainError("only the super administrator can delete an administrator")
            self._remove(user, author)
            self.audit.record(
                E.AuditEntry(
                    entity="User",
                    entity_id=user.id,
                    action="USER_DELETED",
                    author=author.full_name,
                    detail={"username": user.username, "full_name": user.full_name,
                            "role": user.role},
                )
            )
            return
        if user.is_supervisor:
            if not author.is_admin:
                raise E.DomainError("only the administrator can delete a supervisor")
            if user.active:
                self._keep_one_supervisor(user)
            self._remove(user, author)
            self.audit.record(
                E.AuditEntry(
                    entity="User",
                    entity_id=user.id,
                    action="USER_DELETED",
                    author=author.full_name,
                    detail={"username": user.username, "full_name": user.full_name,
                            "role": user.role},
                )
            )
            return
        owned = [
            case for case in (self.cases.list() if self.cases else [])
            if case.analyst and case.analyst.strip().casefold() == user.full_name.casefold()
        ]
        if owned:
            raise E.DomainError(
                f"{user.full_name} owns {len(owned)} case(s) — deactivate the account "
                "instead, so the cases keep their analyst"
            )
        self._remove(user, author)
        self.audit.record(
            E.AuditEntry(
                entity="User",
                entity_id=user.id,
                action="USER_DELETED",
                author=author.full_name,
                detail={"username": user.username, "full_name": user.full_name,
                        "role": user.role},
            )
        )

    def update_own_profile(self, user: E.User, full_name: str) -> E.User:
        """My account: anyone may correct their own full name."""
        return self.update(user, author=user, full_name=full_name)

    def change_own_password(self, user: E.User, current: str, new: str) -> None:
        if not check_password_hash(user.password_hash, current or ""):
            raise AuthenticationFailed("the current password is wrong")
        _check_password(new)
        user.password_hash = generate_password_hash(new)
        self.users.save(user)
        self.audit.record(
            E.AuditEntry(
                entity="User", entity_id=user.id, action="PASSWORD_CHANGED", author=user.full_name
            )
        )

    def _rename_case_owner(self, old: str, new: str) -> None:
        """The cases a user owns follow a rename. Past records (validated_by,
        corrected_by, the audit) keep the name in force at the time."""
        if self.cases is None:
            return
        for case in self.cases.list():
            if case.analyst and case.analyst.strip().casefold() == old.casefold():
                case.analyst = new
                self.cases.save(case)

    def _keep_one_supervisor(self, leaving: E.User) -> None:
        others = [
            u for u in self.users.list()
            if u.id != leaving.id and u.active and u.role == E.ROLE_SUPERVISOR
        ]
        if not others:
            raise E.DomainError(
                "this is the last active supervisor — create or activate another "
                "supervisor first, or nobody could validate or manage users"
            )


def _check_password(password: str | None) -> None:
    if not password or len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"the password must have at least {MIN_PASSWORD_LENGTH} characters")