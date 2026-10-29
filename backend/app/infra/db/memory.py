"""In-memory repositories.

Same ports as the SQLAlchemy ones, no database. They exist for two reasons:

* every service test runs in microseconds and leaves nothing behind;
* the API can be started with ``STORAGE=memory`` to demonstrate the chain on
  a machine where nothing is installed.

If a test needs a database to prove a business rule, the business rule is in
the wrong layer. Use these repositories as the check: anything you cannot
test with them has leaked out of the domain.
"""

from __future__ import annotations

from ...domain import entities as E


class InMemoryCaseRepository:
    def __init__(self) -> None:
        self._cases: dict[str, E.AnalysisCase] = {}

    def add(self, case: E.AnalysisCase) -> None:
        self._cases[case.id] = case

    def get(self, case_id: str) -> E.AnalysisCase | None:
        return self._cases.get(case_id)

    def list(self) -> list[E.AnalysisCase]:
        return list(self._cases.values())

    def save(self, case: E.AnalysisCase) -> None:
        self._cases[case.id] = case

    # CaseService only calls this once every document attached to the case
    # has already gone through DocumentRepository.delete — same contract as
    # SqlCaseRepository.delete.
    def delete(self, case_id: str) -> None:
        self._cases.pop(case_id, None)


class InMemoryDocumentRepository:
    def __init__(self) -> None:
        self._documents: dict[str, E.SourceDocument] = {}

    def add(self, document: E.SourceDocument) -> None:
        self._documents[document.id] = document

    def get(self, document_id: str) -> E.SourceDocument | None:
        return self._documents.get(document_id)

    def find_by_sha256(self, sha256: str , case_id: str) -> E.SourceDocument | None:
        return next(
            (
                d
                for d in self._documents.values()
                if d.sha256 == sha256 and d.case_id == case_id
            ),
            None,
        )

    def save(self , document: E.SourceDocument) -> None:
        self._documents[document.id] = document

    # Same contract as SqlDocumentRepository.delete: CaseService has
    # already removed this document's id from every ExtractionRun that
    # named it, and cleared document_id on every ExtractedField that came
    # from it, before this is ever called.
    def delete(self, document_id: str) -> None:
        self._documents.pop(document_id, None)


class InMemoryExtractionRepository:
    def __init__(self) -> None:
        self._runs: dict[str, E.ExtractionRun] = {}

    def add(self, run: E.ExtractionRun) -> None:
        self._runs[run.id] = run

    def get(self, run_id: str) -> E.ExtractionRun | None:
        return self._runs.get(run_id)

    def save(self, run: E.ExtractionRun) -> None:
        self._runs[run.id] = run

    # A run now spans every document attached to the case at the time it
    # was started (see ExtractionRun's docstring), so this is keyed by
    # case_id rather than document_id.
    def list_for_case(self, case_id: str) -> list[E.ExtractionRun]:
        return [r for r in self._runs.values() if r.case_id == case_id]

    def find_by_field(self, field_id: str) -> E.ExtractionRun | None:
        return next(
            (r for r in self._runs.values() if any(f.id == field_id for f in r.fields)),
            None,
        )

    # The caller deletes every ValidatedDataset for this run first — this
    # only ever removes a run with nothing left pointing at it.
    def delete(self, run_id: str) -> None:
        self._runs.pop(run_id, None)


class InMemoryDatasetRepository:
    def __init__(self) -> None:
        self._datasets: dict[str, E.ValidatedDataset] = {}

    def add(self, dataset: E.ValidatedDataset) -> None:
        self._datasets[dataset.id] = dataset

    def get(self, dataset_id: str) -> E.ValidatedDataset | None:
        return self._datasets.get(dataset_id)

    def find_by_extraction(self, extraction_id: str) -> E.ValidatedDataset | None:
        # Mirrors SqlDatasetRepository.find_by_extraction: an extraction can
        # be validated more than once (reopen -> correct -> re-validate keeps
        # the earlier snapshot rather than deleting it), so "the" dataset for
        # an extraction is the most recently validated one, not whichever
        # this dict happens to yield first.
        matches = [d for d in self._datasets.values() if d.extraction_id == extraction_id]
        if not matches:
          return None
        return max(matches, key=lambda d: d.validated_at)

    def list_for_extraction(self, extraction_id: str) -> list[E.ValidatedDataset]:
        # Plural on purpose, unlike find_by_extraction: see
        # SqlDatasetRepository.list_for_extraction for why CaseService needs
        # every one of a run's datasets, not just the latest.
        return [d for d in self._datasets.values() if d.extraction_id == extraction_id]

    def list(self) -> list[E.ValidatedDataset]:
        return list(self._datasets.values())

    def delete(self, dataset_id: str) -> None:
        self._datasets.pop(dataset_id, None)


class InMemoryAuditLog:
    """Append-only, and it shows: there is no way to remove an entry."""

    def __init__(self) -> None:
        self._entries: list[E.AuditEntry] = []

    def record(self, entry: E.AuditEntry) -> None:
        self._entries.append(entry)

    def list_for(self, entity: str, entity_id: str) -> list[E.AuditEntry]:
        return [
            e for e in self._entries if e.entity == entity and e.entity_id == entity_id
        ]

    def all(self) -> list[E.AuditEntry]:
        return list(self._entries)

    def search(self, query) -> tuple[list[E.AuditEntry], int]:
        found = [e for e in self._entries if _audit_matches(e, query)]
        found.sort(key=lambda e: e.at, reverse=True)
        return found[query.offset : query.offset + query.limit], len(found)

    def facets(self) -> dict[str, list[str]]:
        return {
            "authors": sorted({e.author for e in self._entries}, key=str.casefold),
            "actions": sorted({e.action for e in self._entries}),
            "entities": sorted({e.entity for e in self._entries}),
        }


def _naive(moment):
    """Compare datetimes whether or not they carry a time zone."""
    return moment.replace(tzinfo=None) if getattr(moment, "tzinfo", None) else moment


def _audit_matches(entry: E.AuditEntry, query) -> bool:
    if query.author and entry.author != query.author:
        return False
    if query.action and entry.action != query.action:
        return False
    if query.entity and entry.entity != query.entity:
        return False
    if query.entity_id and entry.entity_id != query.entity_id:
        return False
    if query.since and _naive(entry.at) < _naive(query.since):
        return False
    if query.until and _naive(entry.at) >= _naive(query.until):
        return False
    if query.text:
        haystack = " ".join(
            [entry.action, entry.author, entry.entity, entry.entity_id, str(entry.detail or "")]
        ).casefold()
        if query.text.casefold() not in haystack:
            return False
    return True



class InMemoryAiAnalysisRepository:
    def __init__(self) -> None:
        self._analyses: dict[str, E.AiAnalysis] = {}

    def add(self, analysis: E.AiAnalysis) -> None:
        self._analyses[analysis.id] = analysis

    def get(self, analysis_id: str) -> E.AiAnalysis | None:
        return self._analyses.get(analysis_id)

    def save(self, analysis: E.AiAnalysis) -> None:
        self._analyses[analysis.id] = analysis

    def latest_for_dataset(self, dataset_id: str) -> E.AiAnalysis | None:
        matches = [a for a in self._analyses.values() if a.dataset_id == dataset_id]
        return max(matches, key=lambda a: a.generated_at) if matches else None

    def list_for_case(self, case_id: str) -> list[E.AiAnalysis]:
        return sorted(
            (a for a in self._analyses.values() if a.case_id == case_id),
            key=lambda a: a.generated_at,
        )

    def delete_for_case(self, case_id: str) -> None:
        for analysis_id in [a.id for a in self._analyses.values() if a.case_id == case_id]:
            del self._analyses[analysis_id]



class InMemoryUserRepository:
    def __init__(self) -> None:
        self._users: dict[str, E.User] = {}

    def add(self, user: E.User) -> None:
        self._users[user.id] = user

    def get(self, user_id: str) -> E.User | None:
        return self._users.get(user_id)

    def get_by_username(self, username: str) -> E.User | None:
        wanted = (username or "").strip().lower()
        return next((u for u in self._users.values() if u.username.lower() == wanted), None)

    def list(self) -> list[E.User]:
        return sorted(self._users.values(), key=lambda u: u.full_name.lower())

    def save(self, user: E.User) -> None:
        self._users[user.id] = user

    def delete(self, user_id: str) -> None:
        self._users.pop(user_id, None)



class InMemoryEvaluationRepository:
    def __init__(self) -> None:
        self._campaigns: dict[str, E.EvaluationCampaign] = {}

    def add(self, campaign: E.EvaluationCampaign) -> None:
        self._campaigns[campaign.id] = campaign

    def get(self, campaign_id: str) -> E.EvaluationCampaign | None:
        return self._campaigns.get(campaign_id)

    def list(self, kind: str | None = None) -> list[E.EvaluationCampaign]:
        found = [c for c in self._campaigns.values() if kind is None or c.kind == kind]
        return sorted(found, key=lambda c: c.run_at, reverse=True)

    def delete(self, campaign_id: str) -> bool:
        return self._campaigns.pop(campaign_id, None) is not None


class InMemoryArchiveRepository:
    def __init__(self) -> None:
        self._entries: dict[str, E.ArchiveEntry] = {}

    def add(self, entry: E.ArchiveEntry) -> None:
        self._entries[entry.id] = entry

    def get(self, entry_id: str) -> E.ArchiveEntry | None:
        return self._entries.get(entry_id)

    def list(self, kind: str | None = None) -> list[E.ArchiveEntry]:
        found = [e for e in self._entries.values() if kind is None or e.kind == kind]
        return sorted(found, key=lambda e: e.deleted_at, reverse=True)

    def delete(self, entry_id: str) -> None:
        self._entries.pop(entry_id, None)


class InMemoryCommentRepository:
    def __init__(self) -> None:
        self._comments: list[E.CaseComment] = []
        self._read: dict[tuple[str, str], object] = {}
        self._hidden: set[tuple[str, str, str]] = set()  # (user, case, comment)

    def add(self, comment: E.CaseComment) -> None:
        self._comments.append(comment)

    def get(self, comment_id: str) -> E.CaseComment | None:
        return next((c for c in self._comments if c.id == comment_id), None)

    def save(self, comment: E.CaseComment) -> None:
        self._comments = [comment if c.id == comment.id else c for c in self._comments]

    def list_for_case(self, case_id: str) -> list[E.CaseComment]:
        return [c for c in self._comments if c.case_id == case_id]

    def list(self) -> list[E.CaseComment]:
        return list(self._comments)

    def delete_for_case(self, case_id: str) -> None:
        self._comments = [c for c in self._comments if c.case_id != case_id]
        self._read = {k: v for k, v in self._read.items() if k[1] != case_id}
        self._hidden = {h for h in self._hidden if h[1] != case_id}

    def read_at(self, user_id: str, case_id: str):
        return self._read.get((user_id, case_id))

    def mark_read(self, user_id: str, case_id: str, at) -> None:
        self._read[(user_id, case_id)] = at

    def hide(self, user_id: str, case_id: str, comment_id: str) -> None:
        self._hidden.add((user_id, case_id, comment_id))

    def hidden(self, user_id: str, case_id: str) -> set[str]:
        return {h[2] for h in self._hidden if h[0] == user_id and h[1] == case_id}

