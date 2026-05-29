"""
Expression library — closed-set evaluator for the Insight Engine.

Supports only the operators listed in insight_engine.md §6.3:
    comparison:  >=  <=  >  <  ==  !=
    set:         IN  NOT IN
    null:        IS NULL  IS NOT NULL
    enum:        EQUALS_ENUM

``BETWEEN`` is decomposed at load (see ``decompose_between`` in the
loader); the runtime evaluator never sees it.

``formula:<name>`` is resolved and invoked via the FormulaRegistry
(see ``invoke_formula``).

No AND/OR/NOT operators exist anywhere in this module.

OTA-700
"""

from __future__ import annotations

from typing import Any

from app.insight_engine.registry import FormulaRegistry


# ── Operator sets ───────────────────────────────────────────────────────

_COMPARISON_OPS = frozenset({">=", "<=", ">", "<", "==", "!="})
_SET_OPS = frozenset({"IN", "NOT IN"})
_NULL_OPS = frozenset({"IS NULL", "IS NOT NULL"})
_ENUM_OPS = frozenset({"EQUALS_ENUM"})
_FORMULA_PREFIX = "formula:"

SUPPORTED_EXPRESSIONS = _COMPARISON_OPS | _SET_OPS | _NULL_OPS | _ENUM_OPS
"""All expression forms the runtime evaluator accepts (excluding BETWEEN,
which is decomposed at load, and formula:<name>, which is handled
separately via invoke_formula)."""


class UnsupportedExpressionError(Exception):
    """Raised at load when an expression form is not in the closed set."""


# ── Public API ──────────────────────────────────────────────────────────


def validate_expression(expression: str | None, formula_ref: str | None) -> None:
    """Reject unrecognized expression forms at load time.

    A rule must have either a supported ``condition_expression`` or a
    ``formula_ref`` (or both null for pure-formula scoring rules).
    ``BETWEEN`` is allowed at this stage — it is decomposed before
    reaching the runtime evaluator.

    Raises
    ------
    UnsupportedExpressionError
        If the expression is not in the closed set and no formula_ref
        is present.
    """
    if expression is None:
        return  # formula-only rules, or rules with no condition
    if expression == "BETWEEN":
        return  # valid at load; decomposed before runtime
    if expression in SUPPORTED_EXPRESSIONS:
        return
    raise UnsupportedExpressionError(
        f"Unrecognized expression '{expression}'. Supported: "
        f"{sorted(SUPPORTED_EXPRESSIONS | {'BETWEEN'})}."
    )


def evaluate_expression(
    expression: str,
    named_values: dict[str, Any],
    parameters: dict[str, Any],
    referenced_named_values: tuple[str, ...],
) -> bool:
    """Evaluate a closed-set expression against named values.

    Parameters
    ----------
    expression : str
        One of the supported operators (not BETWEEN, not formula:).
    named_values : dict
        The candidate's named-value map.
    parameters : dict
        The junction's bound parameter values.
    referenced_named_values : tuple[str, ...]
        Named values the rule references (from the rule definition).

    Returns
    -------
    bool
        True if the condition passes, False otherwise.

    Raises
    ------
    UnsupportedExpressionError
        If the expression is not in the closed set.
    """
    if expression in _COMPARISON_OPS:
        return _eval_comparison(expression, named_values, parameters, referenced_named_values)
    if expression in _SET_OPS:
        return _eval_set(expression, named_values, parameters, referenced_named_values)
    if expression in _NULL_OPS:
        return _eval_null(expression, named_values, referenced_named_values)
    if expression in _ENUM_OPS:
        return _eval_enum(expression, named_values, parameters, referenced_named_values)
    raise UnsupportedExpressionError(
        f"Runtime received unsupported expression '{expression}'."
    )


def invoke_formula(
    formula_ref: str,
    registry: FormulaRegistry,
    named_values: dict[str, Any],
    parameters: dict[str, Any],
) -> Any:
    """Resolve a formula:<name> reference and invoke the implementation.

    Parameters
    ----------
    formula_ref : str
        The full ref string, e.g. ``"formula:delta_quality"``.
    registry : FormulaRegistry
        The live formula registry.
    named_values : dict
        The candidate's named-value map.
    parameters : dict
        The junction's bound parameter values.

    Returns
    -------
    Any
        The formula's return value (bool for gates, numeric for scoring).
    """
    if not formula_ref.startswith(_FORMULA_PREFIX):
        raise ValueError(f"Invalid formula_ref '{formula_ref}': must start with '{_FORMULA_PREFIX}'")
    name = formula_ref[len(_FORMULA_PREFIX):]
    return registry.invoke(name, named_values, parameters)


def is_formula_ref(ref: str | None) -> bool:
    """Return True if *ref* is a formula:<name> reference."""
    return ref is not None and ref.startswith(_FORMULA_PREFIX)


def extract_formula_name(ref: str) -> str:
    """Extract the formula name from a formula:<name> reference."""
    return ref[len(_FORMULA_PREFIX):]


# ── Internal evaluators ─────────────────────────────────────────────────


def _get_lhs(
    named_values: dict[str, Any],
    referenced_named_values: tuple[str, ...],
) -> Any:
    """Get the left-hand side: value of the first referenced named value."""
    if not referenced_named_values:
        return None
    return named_values.get(referenced_named_values[0])


def _get_rhs(parameters: dict[str, Any]) -> Any:
    """Get the right-hand side: value of the first (sole) parameter."""
    if not parameters:
        return None
    return next(iter(parameters.values()))


def _eval_comparison(
    op: str,
    named_values: dict[str, Any],
    parameters: dict[str, Any],
    referenced_named_values: tuple[str, ...],
) -> bool:
    lhs = _get_lhs(named_values, referenced_named_values)
    rhs = _get_rhs(parameters)

    # Null on either side fails the comparison (except == None / != None)
    if lhs is None or rhs is None:
        if op == "==" and lhs is None and rhs is None:
            return True
        if op == "!=" and (lhs is None) != (rhs is None):
            return True
        return False

    if op == ">=":
        return lhs >= rhs
    if op == "<=":
        return lhs <= rhs
    if op == ">":
        return lhs > rhs
    if op == "<":
        return lhs < rhs
    if op == "==":
        return lhs == rhs
    if op == "!=":
        return lhs != rhs
    return False  # unreachable


def _eval_set(
    op: str,
    named_values: dict[str, Any],
    parameters: dict[str, Any],
    referenced_named_values: tuple[str, ...],
) -> bool:
    lhs = _get_lhs(named_values, referenced_named_values)
    rhs = _get_rhs(parameters)

    if lhs is None:
        return False
    if not isinstance(rhs, (list, set, tuple, frozenset)):
        return False

    if op == "IN":
        return lhs in rhs
    if op == "NOT IN":
        return lhs not in rhs
    return False


def _eval_null(
    op: str,
    named_values: dict[str, Any],
    referenced_named_values: tuple[str, ...],
) -> bool:
    lhs = _get_lhs(named_values, referenced_named_values)

    if op == "IS NULL":
        return lhs is None
    if op == "IS NOT NULL":
        return lhs is not None
    return False


def _eval_enum(
    op: str,
    named_values: dict[str, Any],
    parameters: dict[str, Any],
    referenced_named_values: tuple[str, ...],
) -> bool:
    lhs = _get_lhs(named_values, referenced_named_values)
    rhs = _get_rhs(parameters)

    if lhs is None or rhs is None:
        return False

    # String comparison for enum matching
    return str(lhs) == str(rhs)
