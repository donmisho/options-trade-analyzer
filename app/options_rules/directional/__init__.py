"""
Directional comparison rule library — formula registration for thesis-fit scoring.

Mirrors the screening rule library pattern: decorator-based registration
populating a DictFormulaRegistry. The consuming application calls
``get_registry()`` and injects the result into the engine.

OTA-755
"""

from __future__ import annotations

import functools
from typing import Any

from app.insight_engine.registry import DictFormulaRegistry, FormulaFn


class FormulaReturnValueError(ValueError):
    """Raised when a formula returns a value outside [0, 100]."""


# ── Module-level registry ──────────────────────────────────────────────

_REGISTRY = DictFormulaRegistry()


def directional_formula(name: str):
    """Register a directional scoring formula under *name*.

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


def get_registry() -> DictFormulaRegistry:
    """Return the live directional formula registry."""
    return _REGISTRY


# ── Auto-register all formula modules ──────────────────────────────────
# Importing triggers @directional_formula decorators.
import app.options_rules.directional.scoring_formulas as _scoring  # noqa: E402, F401
