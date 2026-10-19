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
    AiAnalysisRepository,
    UserRepository,
    AuditLog,
    CaseRepository,
    DatasetRepository,
    DocumentRepository,
    ExtractionRepository,
    Structurer,
)
from .infra.db.memory import (
    InMemoryAiAnalysisRepository,
    InMemoryAuditLog,
    InMemoryCaseRepository,
    InMemoryDatasetRepository,
    InMemoryDocumentRepository,
    InMemoryExtractionRepository,
    InMemoryUserRepository,
)
from .infra.llm.rule_based import RuleBasedStructurer
from .infra.pdf.readers import default_readers
from .services.analysis_service import AnalysisService
from .services.case_service import CaseService
from .services.evaluation_service import EvaluationService
from .services.extraction_service import ExtractionService
from .services.insight_service import InsightService
from .services.user_service import UserService
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
    case_management: CaseService
    ai_analyses: AiAnalysisRepository
    insight: InsightService
    users: UserRepository
    user_service: UserService


def build_container(config: Config | None = None) -> Container:
    config = config or Config()

    if config.storage == "sql":
        from .infra.db.repositories import (
            SqlAiAnalysisRepository,
            SqlAuditLog,
            SqlCaseRepository,
            SqlDatasetRepository,
            SqlDocumentRepository,
            SqlExtractionRepository,
            SqlUserRepository,
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
        ai_analyses = SqlAiAnalysisRepository(session)
        users = SqlUserRepository(session)
    else:
        cases = InMemoryCaseRepository()
        documents = InMemoryDocumentRepository()
        extractions = InMemoryExtractionRepository()
        datasets = InMemoryDatasetRepository()
        audit = InMemoryAuditLog()
        ai_analyses = InMemoryAiAnalysisRepository()
        users = InMemoryUserRepository()

    # Item 4 — rule-based for figures, checks and ratios (above and in the
    # services); the LLM only writes commentary on them, as a draft an
    # analyst must approve. "off", or no API key, leaves the analysis fully
    # working and records why there is no AI commentary.
    analyst_writer = None
    unavailable_reason = "AI analysis is switched off (AI_ANALYSIS=off)"
    if config.ai_analysis == "llm":
        if config.anthropic_api_key:
            from .infra.llm.claude_analyst import ClaudeAnalyst

            analyst_writer = ClaudeAnalyst(
                api_key=config.anthropic_api_key,
                model=config.analysis_model,
                max_cost_usd=config.max_cost_usd,
                input_usd_per_mtok=config.analysis_input_usd_per_mtok,
                output_usd_per_mtok=config.analysis_output_usd_per_mtok,
                effort=config.llm_effort,
            )
        else:
            unavailable_reason = "AI analysis needs ANTHROPIC_API_KEY in the backend .env"

    if config.structurer == "llm":
        from .infra.llm.claude_structurer import ClaudeStructurer

        structurer: Structurer = ClaudeStructurer(
            api_key=config.anthropic_api_key,
            model=config.model,
            max_cost_usd=config.max_cost_usd,
            input_usd_per_mtok=config.input_usd_per_mtok,
            output_usd_per_mtok=config.output_usd_per_mtok,
            effort=config.llm_effort,
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
        case_management=CaseService(
            cases, documents, extractions, datasets, audit, ai_analyses
        ),
        ai_analyses=ai_analyses,
        insight=InsightService(analyst_writer, ai_analyses, audit, unavailable_reason),
        users=users,
        user_service=UserService(users, audit, cases),
    )


def create_app(config: Config | None = None) -> Flask:
    app = Flask(__name__)
    app.config["container"] = build_container(config)
    # The signed session cookie that carries who is signed in.
    from .api.auth import SESSION_LIFETIME

    app.secret_key = app.config["container"].config.secret_key
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["PERMANENT_SESSION_LIFETIME"] = SESSION_LIFETIME
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
        response.headers["Access-Control-Allow-Methods"] = "GET,POST,PATCH,DELETE,OPTIONS"
        return response

    return app