"""The five core ratios and the engine that runs them.

One module per ratio (the Strategy pattern of dossier §13). Adding R6 means
adding a file and one line in ``REGISTRY`` — the engine is never touched.

R1 is implemented as the worked example. R2 to R5 are your exercises: each
file states its formula, its items and the trap specific to it.
"""

from .definition import (
    COMPUTED,
    HIGHER_IS_BETTER,
    LOWER_IS_BETTER,
    NEUTRAL,
    NOT_COMPUTABLE,
    RatioDefinition,
    RatioResult,
)
from .engine import REGISTRY, compute_all, compute_one, definition_of

__all__ = [
    "COMPUTED",
    "NOT_COMPUTABLE",
    "HIGHER_IS_BETTER",
    "LOWER_IS_BETTER",
    "NEUTRAL",
    "RatioDefinition",
    "RatioResult",
    "REGISTRY",
    "compute_all",
    "compute_one",
    "definition_of",
]
