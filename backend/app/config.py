"""Configuration, read from the environment.

Nothing secret is written in this file, and nothing secret is ever committed.
``.env.example`` at the repository root lists the variables; copy it to
``.env`` and fill your own values there — ``.env`` is in ``.gitignore``.

NFR-04 is the reason this matters more here than in a normal student
project: the system handles client financial statements. An API key pushed to
a public GitHub repository is found by scanners within minutes.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Config:
    #: "memory" (default, nothing to install) or "sql"
    storage: str = os.environ.get("STORAGE", "memory")
    database_url: str | None = os.environ.get("DATABASE_URL")

    #: "rule_based" (default, free and deterministic) or "llm"
    structurer: str = os.environ.get("STRUCTURER", "rule_based")
    anthropic_api_key: str | None = os.environ.get("ANTHROPIC_API_KEY")
    model: str = os.environ.get("MODEL", "claude-sonnet-5")
    max_cost_usd: Decimal = Decimal(os.environ.get("MAX_COST_USD", "5.00"))

    upload_dir: Path = Path(os.environ.get("UPLOAD_DIR", ROOT / "data" / "uploads"))
    max_upload_mb: int = int(os.environ.get("MAX_UPLOAD_MB", "50"))

    cors_origin: str = os.environ.get("CORS_ORIGIN", "http://localhost:5173")

    def __post_init__(self) -> None:
        self.upload_dir.mkdir(parents=True, exist_ok=True)
