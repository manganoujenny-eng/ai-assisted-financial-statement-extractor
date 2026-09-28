"""The composition root: where the pieces are chosen and wired together.

This file is the only place in the backend that knows which concrete adapter
is being used. Change ``STRUCTURER=llm`` in the environment and the whole
chain switches from the rule-based structurer to the language model without a
single other file being touched — that is the property dossier §11.1 promises
("changing model provider or OCR engine must touch a single class"), and here
is where it is kept.

Read ``build_container`` slowly. It is short, and it is the map of the system.
"""

from __future__ import annotations

from dataclasses import dataclass

from flask import Flask

from .config import Config
from .domain.ports import (
    AuditLog,
    CaseRepository,
    DatasetRepository,
    DocumentRepository,
    ExtractionRepository,
    Structurer,
)
from .infra.db.memory import (
    InMemoryAuditLog,
    InMemoryCaseRepository,
    InMemoryDatasetRepository,
    InMemoryDocumentRepository,
    InMemoryExtractionRepository,
)
from .infra.llm.rule_based import RuleBasedStructurer
from .infra.pdf.readers import default_readers
from .services.analysis_service import AnalysisService
from .services.evaluation_service import EvaluationService
from .services.extraction_service import ExtractionService
from .services.validation_service import ValidationService


@dataclass
class Container:
    config: Config
    cases: CaseRepository
    documents: DocumentRepository
    extractions: ExtractionRepository
    datasets: DatasetRepository
    audit: AuditLog
    structurer: Structurer
    extraction: ExtractionService
    validation: ValidationService
    analysis: AnalysisService
    evaluation: EvaluationService


def build_container(config: Config | None = None) -> Container:
    config = config or Config()

    if config.storage == "sql":
        from .infra.db.repositories import (
            SqlAuditLog,
            SqlCaseRepository,
            SqlDatasetRepository,
            SqlDocumentRepository,
            SqlExtractionRepository,
        )
        from .infra.db.session import create_schema, make_engine, make_session_factory

        engine = make_engine(config.database_url)
        create_schema(engine)
        session = make_session_factory(engine)()
        cases = SqlCaseRepository(session)
        documents = SqlDocumentRepository(session)
        extractions = SqlExtractionRepository(session)
        datasets = SqlDatasetRepository(session)
        audit = SqlAuditLog(session)
    else:
        cases = InMemoryCaseRepository()
        documents = InMemoryDocumentRepository()
        extractions = InMemoryExtractionRepository()
        datasets = InMemoryDatasetRepository()
        audit = InMemoryAuditLog()

    if config.structurer == "llm":
        from .infra.llm.claude_structurer import ClaudeStructurer

        structurer: Structurer = ClaudeStructurer(
            api_key=config.anthropic_api_key,
            model=config.model,
            max_cost_usd=config.max_cost_usd,
        )
    else:
        structurer = RuleBasedStructurer()

    extraction = ExtractionService(
        readers=default_readers(),
        structurer=structurer,
        documents=documents,
        extractions=extractions,
        audit=audit,
    )
    return Container(
        config=config,
        cases=cases,
        documents=documents,
        extractions=extractions,
        datasets=datasets,
        audit=audit,
        structurer=structurer,
        extraction=extraction,
        validation=ValidationService(extractions, datasets, audit),
        analysis=AnalysisService(audit),
        evaluation=EvaluationService(),
    )


def create_app(config: Config | None = None) -> Flask:
    app = Flask(__name__)
    app.config["container"] = build_container(config)
    app.config["MAX_CONTENT_LENGTH"] = (
        app.config["container"].config.max_upload_mb * 1024 * 1024
    )

    from .api import register_blueprints
    from .api.errors import register_error_handlers

    register_blueprints(app)
    register_error_handlers(app)

    @app.after_request
    def allow_the_dev_frontend(response):
        # The Vite dev server runs on another port, so the browser treats it
        # as a different origin. This is the narrowest thing that works for
        # local development and nothing more: a single declared origin, not
        # "*", and it stays a development concern (§3.3 — production
        # deployment is out of scope).
        origin = app.config["container"].config.cors_origin
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET,POST,PATCH,OPTIONS"
        return response

    return app
