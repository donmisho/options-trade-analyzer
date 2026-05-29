"""
FormulaRegistry — protocol for formula membership, resolution, and invocation.

OTA-699: membership queries (has, registered_names).
OTA-700: resolution and invocation (invoke).
"""

from __future__ import annotations

from typing import Any, Callable, Protocol, runtime_checkable

# A formula function: (named_values, params) -> Any
FormulaFn = Callable[[dict[str, Any], dict[str, Any]], Any]


@runtime_checkable
class FormulaRegistry(Protocol):
    """Formula registry protocol.

    OTA-699 defines membership queries. OTA-700 adds resolution and
    invocation via ``invoke()``.
    """

    def has(self, name: str) -> bool:
        """Return True if a formula implementation exists for *name*."""
        ...

    def registered_names(self) -> frozenset[str]:
        """Return all registered formula names."""
        ...

    def invoke(
        self,
        name: str,
        named_values: dict[str, Any],
        params: dict[str, Any],
    ) -> Any:
        """Resolve *name* and call the implementation with (named_values, params)."""
        ...


class StubFormulaRegistry:
    """Empty registry — no formulas registered. Pre-Wave-3 default."""

    def has(self, name: str) -> bool:
        return False

    def registered_names(self) -> frozenset[str]:
        return frozenset()

    def invoke(
        self,
        name: str,
        named_values: dict[str, Any],
        params: dict[str, Any],
    ) -> Any:
        raise KeyError(f"StubFormulaRegistry has no formula '{name}'")


class DictFormulaRegistry:
    """Dict-backed registry for tests and early integration."""

    def __init__(self, formulas: dict[str, FormulaFn] | None = None) -> None:
        self._formulas: dict[str, FormulaFn] = dict(formulas or {})

    def register(self, name: str, fn: FormulaFn) -> None:
        self._formulas[name] = fn

    def has(self, name: str) -> bool:
        return name in self._formulas

    def registered_names(self) -> frozenset[str]:
        return frozenset(self._formulas)

    def invoke(
        self,
        name: str,
        named_values: dict[str, Any],
        params: dict[str, Any],
    ) -> Any:
        fn = self._formulas.get(name)
        if fn is None:
            raise KeyError(f"No formula registered for '{name}'")
        return fn(named_values, params)
