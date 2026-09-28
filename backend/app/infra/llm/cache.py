"""Response cache keyed by content fingerprint (NFR-08).

The same document, the same prompt version and the same model must never be
paid for twice. During week 7 you will replay the corpus many times while
tuning everything downstream; without this file that replay costs real money
every single run, and the budget of dossier §5.3 disappears into repetition.

Files on disk, not a database: the cache must survive a dropped database, a
reset schema and a laptop reboot, and it must be inspectable with a text
editor when an answer looks wrong.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

DEFAULT_CACHE_DIR = Path(
    os.environ.get("LLM_CACHE_DIR", Path(__file__).resolve().parents[4] / "data" / "llm_cache")
)


class ResponseCache:
    def __init__(self, directory: Path | str | None = None) -> None:
        self.directory = Path(directory) if directory else DEFAULT_CACHE_DIR
        self.directory.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def fingerprint(text: str, prompt_version: str, model: str) -> str:
        """The key includes the prompt version and the model, not just the text.

        Change the prompt and you are asking a different question; change the
        model and you are asking a different reader. Either way the old answer
        is not an answer to the new question — and FR-23 depends on both
        living side by side rather than overwriting each other.
        """
        digest = hashlib.sha256()
        digest.update(model.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(prompt_version.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(text.encode("utf-8"))
        return digest.hexdigest()

    def _path(self, fingerprint: str) -> Path:
        return self.directory / f"{fingerprint}.json"

    def get(self, fingerprint: str) -> str | None:
        path = self._path(fingerprint)
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def put(self, fingerprint: str, payload: str) -> None:
        self._path(fingerprint).write_text(payload, encoding="utf-8")
