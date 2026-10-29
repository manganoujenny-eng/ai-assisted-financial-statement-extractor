"""The supervisors' discussion of a case.

What it is for: only the supervisor a case is assigned to acts on it. A
supervisor who has an opinion on someone else's case opens that case and
writes in its discussion; the assigned supervisor is told (bell, My cases)
and replies. The discussion is about that case and nothing else.

The rules, in one place:

* The case must have a supervisor — the one it was submitted to, or the
  one who validated it. Before that there is nobody to talk to.
* The assigned supervisor does not write first: nobody writes to
  themselves. They may reply as soon as another supervisor has written.
* Only its author edits a message, or deletes it *for everyone*: it then
  stays in the thread as "deleted by ...", without its text.
* Anyone may delete a message *for themselves* — someone else's, or a
  "deleted by ..." notice: it disappears from their own view only.
* "Who is writing" lives in memory only, for a few seconds: it is a hint
  on the screen, not a record.
* Every message, edit and deletion is written to the audit log.

Who may *read* (supervisors only) is checked by the route, like every role.
"""

from __future__ import annotations

import time
from dataclasses import replace

from ..domain import entities as E

#: How long "X is writing…" stays after the last keystroke signal.
TYPING_SECONDS = 6

WAIT_FOR_MESSAGE = "WAIT_FOR_MESSAGE"
NO_SUPERVISOR = "NO_SUPERVISOR"


def _same(a: str | None, b: str | None) -> bool:
    return " ".join((a or "").split()).casefold() == " ".join((b or "").split()).casefold()


class NotYourMessage(PermissionError):
    """Editing or deleting someone else's message (HTTP 403)."""


class DiscussionService:
    def __init__(self, comments, audit, clock=time.monotonic) -> None:
        self.comments = comments
        self.audit = audit
        #: Replaceable in tests; ``now()`` always reads the real clock.
        self.clock = clock
        self.now = clock
        self._typing: dict[str, dict[str, float]] = {}

    # --- reading ----------------------------------------------------------------
    def why_not(self, case_id: str, me: str, supervisor: str | None) -> str | None:
        """None when ``me`` may write now, otherwise the reason."""
        if not supervisor:
            return NO_SUPERVISOR
        if _same(me, supervisor) and not any(
            not _same(m.author, me) for m in self.comments.list_for_case(case_id)
        ):
            return WAIT_FOR_MESSAGE
        return None

    def view(self, case_id: str, me: str, supervisor: str | None,
             viewer: str | None = None) -> dict:
        """The thread as ``me`` sees it; ``viewer`` (the account id) leaves
        out what they deleted for themselves."""
        why = self.why_not(case_id, me, supervisor)
        return {
            "assigned_to": supervisor,
            "can_write": why is None,
            "why_not": why,
            "messages": [self.as_json(m, me) for m in self.visible(case_id, viewer)],
            "typing": self.typing(case_id, me),
        }

    def visible(self, case_id: str, viewer: str | None) -> list[E.CaseComment]:
        messages = self.comments.list_for_case(case_id)
        if viewer is None:
            return messages
        hidden = self.comments.hidden(viewer, case_id)
        return [m for m in messages if m.id not in hidden]

    @staticmethod
    def as_json(comment: E.CaseComment, me: str | None = None) -> dict:
        return {
            "id": comment.id,
            "author": comment.author,
            # The text of a deleted message never leaves the server.
            "message": None if comment.deleted else comment.message,
            "at": comment.created_at.isoformat(),
            "edited_at": comment.edited_at.isoformat() if comment.edited_at else None,
            "deleted": comment.deleted,
            "mine": _same(comment.author, me) if me is not None else False,
        }

    # --- writing ----------------------------------------------------------------
    def post(self, case_id: str, author: str, supervisor: str | None, message: str) -> E.CaseComment:
        message = self._clean(message)
        why = self.why_not(case_id, author, supervisor)
        if why == NO_SUPERVISOR:
            raise E.DomainError(
                "this case has no supervisor yet: the discussion opens once it is submitted"
            )
        if why == WAIT_FOR_MESSAGE:
            raise E.DomainError(
                "this is your case: you reply once another supervisor has written about it"
            )
        comment = E.CaseComment(case_id=case_id, author=author, message=message)
        self.comments.add(comment)
        self._stopped_typing(case_id, author)
        self._audit(case_id, "DISCUSSION_MESSAGE", author, {"message_id": comment.id,
                                                            "message": message[:300]})
        return comment

    def edit(self, case_id: str, comment_id: str, author: str, message: str) -> E.CaseComment:
        comment = self._own(case_id, comment_id, author, "edit")
        message = self._clean(message)
        edited = replace(comment, message=message, edited_at=E._now())
        self.comments.save(edited)
        self._stopped_typing(case_id, author)
        self._audit(case_id, "DISCUSSION_EDITED", author, {
            "message_id": comment.id, "before": comment.message[:300], "after": message[:300]})
        return edited

    def delete(self, case_id: str, comment_id: str, author: str) -> None:
        comment = self._own(case_id, comment_id, author, "delete")
        self.comments.save(replace(comment, deleted_at=E._now()))
        self._audit(case_id, "DISCUSSION_DELETED", author, {
            "message_id": comment.id, "message": comment.message[:300]})

    def delete_for_me(self, case_id: str, comment_id: str, viewer: str) -> None:
        """Hides a message — anyone's, deleted or not — from ``viewer`` only."""
        comment = self.comments.get(comment_id)
        if comment is None or comment.case_id != case_id:
            raise KeyError(f"message {comment_id}")
        self.comments.hide(viewer, case_id, comment_id)

    # --- who is writing ---------------------------------------------------------
    def is_typing(self, case_id: str, name: str) -> None:
        self._typing.setdefault(case_id, {})[name] = self.clock()

    def typing(self, case_id: str, me: str) -> list[str]:
        now = self.clock()
        return sorted(
            name for name, at in self._typing.get(case_id, {}).items()
            if now - at <= TYPING_SECONDS and not _same(name, me)
        )

    def _stopped_typing(self, case_id: str, name: str) -> None:
        self._typing.get(case_id, {}).pop(name, None)

    # --- helpers -----------------------------------------------------------------
    @staticmethod
    def _clean(message) -> str:
        message = str(message or "").strip()
        if not message:
            raise ValueError("the message is empty")
        if len(message) > E.MAX_COMMENT_LENGTH:
            raise ValueError(f"a message has at most {E.MAX_COMMENT_LENGTH} characters")
        return message

    def _own(self, case_id: str, comment_id: str, author: str, verb: str) -> E.CaseComment:
        comment = self.comments.get(comment_id)
        if comment is None or comment.case_id != case_id:
            raise KeyError(f"message {comment_id}")
        if not _same(comment.author, author):
            raise NotYourMessage(f"only {comment.author} can {verb} this message")
        if comment.deleted:
            raise E.DomainError("this message was deleted")
        return comment

    def _audit(self, case_id: str, action: str, author: str, detail: dict) -> None:
        self.audit.record(E.AuditEntry(entity="AnalysisCase", entity_id=case_id,
                                       action=action, author=author, detail=detail))