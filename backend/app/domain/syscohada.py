"""The SYSCOHADA codes this prototype actually depends on.

Scope (dossier §3.2): balance sheet aggregates + the income statement items
the five retained ratios require. Not the whole chart of accounts — only what
the ratios and the checks consume. Everything the extractor finds beyond this
list is kept in the database, but nothing downstream reads it.

Keeping this list in one module, rather than sprinkling ``"BK"`` literals
through the code, is what makes the dependency graph of dossier §18 (which
item feeds which ratio) computable instead of hand-drawn.
"""

from __future__ import annotations

from dataclasses import dataclass

from .value_objects import ItemCode


@dataclass(frozen=True)
class ItemDefinition:
    code: str
    label: str
    statement: str  # "BALANCE_SHEET" | "INCOME_STATEMENT"
    side: str  # "ASSETS" | "LIABILITIES" | "-"
    is_aggregate: bool = False


# --- Balance sheet, assets ------------------------------------------------
CATALOGUE: dict[str, ItemDefinition] = {
    d.code: d
    for d in [
        ItemDefinition("AZ", "TOTAL ACTIF IMMOBILISÉ", "BALANCE_SHEET", "ASSETS", True),
        ItemDefinition("BK", "TOTAL ACTIF CIRCULANT", "BALANCE_SHEET", "ASSETS", True),
        ItemDefinition("BT", "TOTAL TRÉSORERIE-ACTIF", "BALANCE_SHEET", "ASSETS", True),
        ItemDefinition("BU", "Écart de conversion-Actif", "BALANCE_SHEET", "ASSETS"),
        ItemDefinition("BZ", "TOTAL GÉNÉRAL ACTIF", "BALANCE_SHEET", "ASSETS", True),
        # --- Balance sheet, liabilities and equity ------------------------
        ItemDefinition("CJ", "Résultat net de l'exercice", "BALANCE_SHEET", "LIABILITIES"),
        ItemDefinition("CP", "TOTAL CAPITAUX PROPRES", "BALANCE_SHEET", "LIABILITIES", True),
        ItemDefinition("DD", "TOTAL DETTES FINANCIÈRES", "BALANCE_SHEET", "LIABILITIES", True),
        ItemDefinition("DF", "TOTAL RESSOURCES STABLES", "BALANCE_SHEET", "LIABILITIES", True),
        ItemDefinition("DP", "TOTAL PASSIF CIRCULANT", "BALANCE_SHEET", "LIABILITIES", True),
        ItemDefinition("DT", "TOTAL TRÉSORERIE-PASSIF", "BALANCE_SHEET", "LIABILITIES", True),
        ItemDefinition("DV", "Écart de conversion-Passif", "BALANCE_SHEET", "LIABILITIES"),
        ItemDefinition("DZ", "TOTAL GÉNÉRAL PASSIF", "BALANCE_SHEET", "LIABILITIES", True),
        # --- Income statement --------------------------------------------
        ItemDefinition("XB", "CHIFFRE D'AFFAIRES", "INCOME_STATEMENT", "-", True),
        ItemDefinition("XG", "RÉSULTAT D'EXPLOITATION", "INCOME_STATEMENT", "-", True),
        ItemDefinition("XI", "RÉSULTAT NET", "INCOME_STATEMENT", "-", True),
    ]
}

#: Codes the prototype must find in a package for the core set to be complete.
#: Used by check CHK004 (completeness) and by FR-16 (NOT_COMPUTABLE with a
#: reason rather than a silent zero).
REQUIRED_CODES: tuple[str, ...] = (
    "AZ", "BK", "BT", "BZ", "CP", "DD", "DP", "DT", "DZ", "XB", "XI",
)


def is_known(code: str | ItemCode) -> bool:
    return str(code).upper() in CATALOGUE


def label_of(code: str | ItemCode) -> str:
    definition = CATALOGUE.get(str(code).upper())
    return definition.label if definition else str(code).upper()
