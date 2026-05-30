"""
Position-health rule library — formula registration for position grading.

Mirrors the screening rule library pattern: decorator-based registration
populating a DictFormulaRegistry. The consuming application calls
``get_registry()`` and injects the result into the engine.

Three decorator types:
    @health_formula   — scoring criteria, returns float in [0, 100]
    @health_gate      — gates, returns bool (True = pass)
    @health_adjustment — post-scoring adjustments, returns float or bool

OTA-743 (registration mechanism), OTA-744–747 (formula implementations)
"""

from __future__ import annotations

import functools
from typing import Any

from app.insight_engine.registry import DictFormulaRegistry, FormulaFn


class FormulaReturnValueError(ValueError):
    """Raised when a formula returns a value outside its expected range."""


# ── Module-level registry ──────────────────────────────────────────────

_REGISTRY = DictFormulaRegistry()


def health_formula(name: str):
    """Register a position-health scoring formula under *name*.

    The decorated function must accept ``(named_values, params)`` and
    return a ``float`` in ``[0, 100]``.
    """

    def decorator(fn: FormulaFn) -> FormulaFn:
        @functools.wraps(fn)
        def wrapper(
            named_values: dict[str, Any], params: dict[str, Any]
        ) -> float:
            result = fn(named_values, params)
            if not isinstance(result, (int, float)):
                raise FormulaReturnValueError(
                    f"Formula '{name}' returned {type(result).__name__}, "
                    f"expected a number in [0, 100]."
                )
            val = float(result)
            if val < 0.0 or val > 100.0:
                raise FormulaReturnValueError(
                    f"Formula '{name}' returned {val}, "
                    f"expected a value in [0, 100]."
                )
            return val

        _REGISTRY.register(name, wrapper)
        return fn  # return unwrapped fn so tests can call directly

    return decorator


def health_gate(name: str):
    """Register a position-health gate formula under *name*.

    Gate formulas must return ``bool``:
    - ``True`` = gate passed (candidate continues)
    - ``False`` = gate failed (engine checks stop_if_fail / terminal_verdict)
    """

    def decorator(fn: FormulaFn) -> FormulaFn:
        @functools.wraps(fn)
        def wrapper(
            named_values: dict[str, Any], params: dict[str, Any]
        ) -> bool:
            result = fn(named_values, params)
            if not isinstance(result, bool):
                raise FormulaReturnValueError(
                    f"Gate formula '{name}' returned "
                    f"{type(result).__name__}, expected bool."
                )
            return result

        _REGISTRY.register(name, wrapper)
        return fn

    return decorator


def health_adjustment(name: str):
    """Register a position-health adjustment formula under *name*.

    Adjustment formulas may return:
    - ``float``: a replacement score (the engine uses it as the new score)
    - ``bool``: True = no penalty, False = trigger junction's score_penalty

    For position-health adjustments (floor/cap), the formulas return
    a float that the engine uses directly as the adjusted score.
    """

    def decorator(fn: FormulaFn) -> FormulaFn:
        @functools.wraps(fn)
        def wrapper(
            named_values: dict[str, Any], params: dict[str, Any]
        ) -> Any:
            result = fn(named_values, params)
            if not isinstance(result, (bool, int, float)):
                raise FormulaReturnValueError(
                    f"Adjustment formula '{name}' returned "
                    f"{type(result).__name__}, expected bool or number."
                )
            return result

        _REGISTRY.register(name, wrapper)
        return fn

    return decorator


def get_registry() -> DictFormulaRegistry:
    """Return the live position-health formula registry.

    The consuming application injects this into the engine's
    ``evaluate()`` and ``validate_config()`` calls.
    """
    return _REGISTRY


# ── Auto-register all formula modules ──────────────────────────────────
# Importing triggers @health_formula / @health_gate / @health_adjustment
# decorators. Modules are added as formula implementations ship.
import app.options_rules.position_health.scoring_formulas as _scoring  # noqa: E402, F401
import app.options_rules.position_health.adjustment_formulas as _adj  # noqa: E402, F401
