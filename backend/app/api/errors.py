"""One place where an exception becomes an HTTP response.

Without this file, every route grows its own try/except and they slowly stop
agreeing with each other. With it, a ``DomainError`` is a 409 everywhere, and
a route that forgets to handle something still answers something intelligible.

The status codes are chosen, not guessed:

* **409 Conflict** for a business rule refusal (a forbidden transition, a
  validation blocked by a failing check). The request was well formed; the
  system is simply not in a state where it can be granted. That is exactly
  what 409 means, and 400 would suggest the client made a mistake.
* **422 Unprocessable Entity** for a payload that is syntactically valid JSON
  but semantically wrong (an amount that is not a number).
* **404** for an unknown identifier, **400** for a malformed request.
"""

from __future__ import annotations

from flask import jsonify
from werkzeug.exceptions import HTTPException

from ..domain.entities import DomainError
from ..services.extraction_service import ExtractionFailed
from ..services.validation_service import ValidationRefused


def register_error_handlers(app) -> None:
    @app.errorhandler(DomainError)
    def _domain_error(exc: DomainError):
        return jsonify({"error": "business_rule_violated", "detail": str(exc)}), 409

    @app.errorhandler(ValidationRefused)
    def _validation_refused(exc: ValidationRefused):
        return (
            jsonify(
                {
                    "error": "validation_refused",
                    "detail": str(exc),
                    # The failing checks are returned, not only the refusal.
                    # UC-06 exception E1: "validation is refused and the
                    # discrepancies are listed". A refusal without the list
                    # tells the supervisor nothing they can act on.
                    "failing_checks": [
                        {
                            "code": outcome.code,
                            "label": outcome.label,
                            "gap": str(outcome.gap) if outcome.gap is not None else None,
                            "message": outcome.message,
                        }
                        for outcome in exc.failures
                    ],
                }
            ),
            409,
        )

    @app.errorhandler(ExtractionFailed)
    def _extraction_failed(exc: ExtractionFailed):
        return jsonify({"error": "extraction_failed", "detail": str(exc)}), 422

    @app.errorhandler(KeyError)
    def _not_found(exc: KeyError):
        return jsonify({"error": "not_found", "detail": str(exc)}), 404

    @app.errorhandler(ValueError)
    def _bad_value(exc: ValueError):
        return jsonify({"error": "invalid_value", "detail": str(exc)}), 422

    @app.errorhandler(HTTPException)
    def _http(exc: HTTPException):
        return jsonify({"error": exc.name, "detail": exc.description}), exc.code

    @app.errorhandler(Exception)
    def _unexpected(exc: Exception):
        # Deliberately terse to the client, complete in the log. A stack
        # trace in an HTTP response is a gift to whoever is probing the
        # service — and useless to the analyst reading it.
        app.logger.exception("unhandled error")
        return jsonify({"error": "internal_error"}), 500
