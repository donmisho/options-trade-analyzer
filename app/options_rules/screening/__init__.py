"""
Screening rule library — formula registration mechanism for trade screening.

Provides a decorator-based registration API that populates a
DictFormulaRegistry. The consuming application calls ``get_registry()``
and injects the result into the engine's ``evaluate()`` and
``validate_config()`` calls.

Registered formulas must be pure: ``(named_values, params) -> float``
returning a value in ``[0, 100]``. The registry validates the return
value at invocation time and raises on violation.

OTA-726
"""

from __future__ import annotations

import functools
from typing import Any

from app.insight_engine.registry import DictFormulaRegistry, FormulaFn


class FormulaReturnValueError(ValueError):
    """Raised when a formula returns a value outside [0, 100]."""


# ── Module-level registry ──────────────────────────────────────────────

_REGISTRY = DictFormulaRegistry()


def screening_formula(name: str):
    """Register a screening formula implementation under *name*.

    The decorated function must accept ``(named_values, params)`` and
    return a ``float`` in ``[0, 100]``.  A runtime wrapper validates
    the return value on every invocation.

    Usage::

        @screening_formula("delta_quality")
        def delta_quality(named_values: dict, params: dict) -> float:
            ...
            return score
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
        return fn  # return the unwrapped fn so tests can call it directly

    return decorator


def adjustment_formula(name: str):
    """Register an adjustment formula implementation under *name*.

    Unlike ``screening_formula``, adjustment formulas may return:
    - ``bool``: True = no penalty, False = trigger junction's score_penalty
    - ``float``: added directly to score (can be negative, e.g. -25)

    No [0, 100] clamping is applied. The engine's ``_run_adjustments``
    handles clamping after applying the delta.

    OTA-728, OTA-729
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


def gate_formula(name: str):
    """Register a gate formula implementation under *name*.

    Gate formulas must return ``bool``:
    - ``True`` = gate passed (candidate continues)
    - ``False`` = gate failed (engine checks stop_if_fail / terminal_verdict)

    The engine's ``_evaluate_rule`` calls ``bool(result)`` on the return,
    but we enforce actual ``bool`` at the wrapper level for clarity.

    OTA-730, OTA-731
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


def get_registry() -> DictFormulaRegistry:
    """Return the live screening formula registry.

    This is the object OTA-699's ``_check_formula_in_live_registry``
    and ``_check_formula_registry_drift`` validate against, and
    OTA-700's ``invoke_formula`` resolves through.
    """
    return _REGISTRY


# ── Auto-register all formula modules ──────────────────────────────────
# Importing triggers @screening_formula / @adjustment_formula / @gate_formula decorators.
import app.options_rules.screening.scoring_formulas as _scoring  # noqa: E402, F401
import app.options_rules.screening.adjustment_formulas as _adj  # noqa: E402, F401
import app.options_rules.screening.gate_formulas as _gates  # noqa: E402, F401
