"""
ConfigSource — abstraction for reading engine_* table rows.

The engine package must not import any DB driver (insight_engine.md §2.5,
OTA-696 guard). The loader consumes an injected ConfigSource that yields
raw rows per table. The concrete Azure-SQL-backed ConfigSource is app-side
wiring (Wave 4); this module provides the interface and an in-memory
implementation for tests.

OTA-698
"""

from __future__ import annotations

from typing import Any, Protocol


# Each row is a plain dict mapping column name → value, matching the
# column names in insight_engine-schema-ddl.md §2.
RawRow = dict[str, Any]


class ConfigSource(Protocol):
    """Read-only source of engine_* table rows.

    Implementations return lists of dicts (one dict per row) with keys
    matching the DDL column names. The loader handles parsing, filtering,
    and scoping.
    """

    def fetch_apps(self) -> list[RawRow]:
        """Return all rows from engine_apps."""
        ...

    def fetch_rules(self) -> list[RawRow]:
        """Return all rows from engine_rules."""
        ...

    def fetch_strategies(self) -> list[RawRow]:
        """Return all rows from engine_strategies."""
        ...

    def fetch_junction(self) -> list[RawRow]:
        """Return all rows from engine_strategy_rule_junction."""
        ...

    def fetch_lookups(self) -> list[RawRow]:
        """Return all rows from engine_lookups."""
        ...


class InMemoryConfigSource:
    """Dict/list-backed ConfigSource for tests (OTA-707).

    Pass pre-built row lists at construction time.
    """

    def __init__(
        self,
        *,
        apps: list[RawRow] | None = None,
        rules: list[RawRow] | None = None,
        strategies: list[RawRow] | None = None,
        junction: list[RawRow] | None = None,
        lookups: list[RawRow] | None = None,
    ) -> None:
        self._apps = apps or []
        self._rules = rules or []
        self._strategies = strategies or []
        self._junction = junction or []
        self._lookups = lookups or []

    def fetch_apps(self) -> list[RawRow]:
        return list(self._apps)

    def fetch_rules(self) -> list[RawRow]:
        return list(self._rules)

    def fetch_strategies(self) -> list[RawRow]:
        return list(self._strategies)

    def fetch_junction(self) -> list[RawRow]:
        return list(self._junction)

    def fetch_lookups(self) -> list[RawRow]:
        return list(self._lookups)
