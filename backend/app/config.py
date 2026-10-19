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
import secrets
from dotenv import load_dotenv
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path



ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Config:
    load_dotenv()
    #: "memory" (default, nothing to install) or "sql"
    storage: str = os.environ.get("STORAGE", "memory")
    database_url: str | None = os.environ.get("DATABASE_URL")

    #: "rule_based" (default, free and deterministic) or "llm"
    structurer: str = os.environ.get("STRUCTURER", "rule_based")
    anthropic_api_key: str | None = os.environ.get("ANTHROPIC_API_KEY")
    #: Claude Opus 5.5 (supervisor's choice). Exact ID from
    #: https://platform.claude.com/docs/en/models/overview — no date suffix.
    model: str = os.environ.get("MODEL", "claude-opus-5-5")
    max_cost_usd: Decimal = Decimal(os.environ.get("MAX_COST_USD", "5.00"))
    #: Prices in USD per million tokens, used for the NFR-08 budget cap.
    #: Opus 5.5: $4 input / $20 output (thinking tokens are billed as
    #: output). Update them if you change MODEL.
    input_usd_per_mtok: Decimal = Decimal(os.environ.get("INPUT_USD_PER_MTOK", "4.00"))
    output_usd_per_mtok: Decimal = Decimal(os.environ.get("OUTPUT_USD_PER_MTOK", "20.00"))
    #: Opus 5.5 always thinks before answering; effort decides how much
    #: (low | medium | high | xhigh | max). medium is the model's default;
    #: low is cheaper and is enough for reading figures off a table.
    llm_effort: str = os.environ.get("LLM_EFFORT", "medium")

    #: AI commentary on validated analyses (item 4): "llm" or "off".
    #: "llm" needs ANTHROPIC_API_KEY. Model and prices are separate from the
    #: structurer's so the two can differ; by default both use MODEL.
    ai_analysis: str = os.environ.get("AI_ANALYSIS", "llm")
    analysis_model: str = os.environ.get("ANALYSIS_MODEL", os.environ.get("MODEL", "claude-opus-5-5"))
    analysis_input_usd_per_mtok: Decimal = Decimal(
        os.environ.get("ANALYSIS_INPUT_USD_PER_MTOK", os.environ.get("INPUT_USD_PER_MTOK", "4.00"))
    )
    analysis_output_usd_per_mtok: Decimal = Decimal(
        os.environ.get("ANALYSIS_OUTPUT_USD_PER_MTOK", os.environ.get("OUTPUT_USD_PER_MTOK", "20.00"))
    )

    upload_dir: Path = Path(os.environ.get("UPLOAD_DIR", ROOT / "data" / "uploads"))
    #: A full SYSCOHADA package scanned at a readable resolution is easily
    #: 50-150 MB. The file is streamed to disk and hashed in chunks, so the
    #: limit is about disk space and patience, not memory.
    max_upload_mb: int = int(os.environ.get("MAX_UPLOAD_MB", "300"))

    #: Item 5 — sign-in. "false" only for the test suite or a quick local
    #: demo: names then come from the request and roles are not enforced.
    auth_required: bool = os.environ.get("AUTH_REQUIRED", "true").strip().lower() != "false"
    #: Signs the session cookie. Set SECRET_KEY in .env (any long random
    #: string, e.g. python -c "import secrets; print(secrets.token_hex(32))").
    #: Without it a random key is made at each start, which signs everyone
    #: out whenever the backend restarts.
    secret_key: str = os.environ.get("SECRET_KEY") or secrets.token_hex(32)

    cors_origin: str = os.environ.get("CORS_ORIGIN", "http://localhost:5173")

    def __post_init__(self) -> None:
        self.upload_dir.mkdir(parents=True, exist_ok=True)