"""The sensitivity analysis of dossier §19.2.

Run this file and watch how long it takes. A few hundred complete ratio
computations finish in a fraction of a second — because the domain layer needs
no database, no network and no PDF. That speed is not a nicety; it is what
makes Part D feasible inside an eight-week internship.
"""

from decimal import Decimal

from app.services.evaluation_service import EvaluationService


def test_perturbing_an_item_moves_the_ratios_that_depend_on_it(balanced):
    service = EvaluationService()
    matrix = service.sensitivity_matrix(
        balanced, items=("BK",), perturbations=(Decimal("0.10"),)
    )

    r1 = next(c for c in matrix.cells if c.ratio_code == "R1")
    assert r1.relative_deviation is not None
    assert r1.relative_deviation > 0


def test_an_item_no_ratio_uses_moves_nothing(balanced):
    # XG (operating income) feeds none of the five core ratios. Perturbing it
    # must leave every one of them untouched — a sanity check on the whole
    # protocol: if this fails, the dependency graph is not what you think.
    service = EvaluationService()
    matrix = service.sensitivity_matrix(
        balanced, items=("XG",), perturbations=(Decimal("0.10"),)
    )
    deviations = [c.relative_deviation for c in matrix.cells if c.is_measurable]
    assert all(d == 0 for d in deviations)


def test_the_ground_truth_is_never_modified(balanced):
    # The statement is frozen and perturbation returns a copy. A campaign
    # that corrupted its own reference would produce numbers nobody could
    # trust, and the corruption would be invisible.
    before = balanced.to_dict()
    EvaluationService().sensitivity_matrix(balanced, items=("CP",))
    assert balanced.to_dict() == before


def test_the_matrix_says_which_perturbations_the_checks_would_catch(balanced):
    # Step 5 of the protocol. Perturbing BZ alone breaks the equilibrium, so
    # CHK001 fires: that error would never reach a ratio unnoticed.
    service = EvaluationService()
    matrix = service.sensitivity_matrix(
        balanced, items=("BZ",), perturbations=(Decimal("0.05"),)
    )
    assert all(cell.intercepted_by_checks for cell in matrix.cells)


def test_an_error_the_checks_miss_is_visible_as_such(balanced):
    # XB (revenue) appears in no balance-sheet identity, so a wrong revenue
    # passes every check and lands straight in the net margin. That is the
    # silent false positive of §18.1 — the indicator the dossier calls the
    # most important of all — and here it is, reproducible, in one test.
    service = EvaluationService()
    matrix = service.sensitivity_matrix(
        balanced, items=("XB",), perturbations=(Decimal("0.10"),)
    )
    assert not any(cell.intercepted_by_checks for cell in matrix.cells)


def test_criticality_ranks_items_by_how_far_their_errors_travel(balanced):
    """The answer to sub-question 4 of the dossier, in one assertion.

    Note: while R2..R5 are unimplemented this measures R1 only, so the
    ranking is partial. Run it again after each ratio you implement — the
    table changes, and watching it change is the most direct way to feel what
    "error propagation" actually means.
    """
    service = EvaluationService()
    matrix = service.sensitivity_matrix(balanced, items=("BK", "XG"))
    assert matrix.criticality("BK") > matrix.criticality("XG")
