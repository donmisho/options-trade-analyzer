"""
FormulaRegistry — minimal protocol for formula membership queries.

Pre-Wave-3 stub; OTA-700 extends with resolution/invocation.

OTA-699
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class FormulaRegistry(Protocol):
    """Minimal formula registry protocol.

    OTA-699 defines membership queries only. OTA-700 extends with
    expression evaluation and formula invocation.
    """

    def has(self, name: str) -> bool:
        """Return True if a formula implementation exists for *name*."""
        ...

    def registered_names(self) -> frozenset[str]:
        """Return all registered formula names."""
        ...


class StubFormulaRegistry:
    """Empty registry — no formulas registered. Pre-Wave-3 default."""

    def has(self, name: str) -> bool:
        return False

    def registered_names(self) -> frozenset[str]:
        return frozenset()
