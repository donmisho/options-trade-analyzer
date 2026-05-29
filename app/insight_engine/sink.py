"""
PersistenceSink — abstraction for writing bronze record streams.

The engine depends on a sink **interface**, never on a database
(insight_engine.md §4.3, §8). The engine drives the sink after each run;
the sink owns connection, credentials, transactions, and retry.

The consuming application injects a concrete sink at startup. The concrete
Azure SQL sink is app-side wiring (Wave 4); this module provides the
interface and an in-memory implementation for tests.

OTA-705
"""

from __future__ import annotations

from typing import Protocol

from app.insight_engine.models import CandidateSnapshot, EvaluationDecision


class PersistenceSink(Protocol):
    """Write-side interface for bronze record persistence.

    Implementations own the write mechanics — connection, credentials,
    transactions, retry, physical store. The engine drives the calls;
    the sink does the rest.
    """

    def write_snapshots(self, records: list[CandidateSnapshot]) -> None:
        """Persist candidate snapshot records (one per candidate per run)."""
        ...

    def write_decisions(self, records: list[EvaluationDecision]) -> None:
        """Persist evaluation decision records (one per rule evaluation)."""
        ...


class InMemorySink:
    """In-memory sink that captures both streams for assertion in tests.

    Not thread-safe. Not for production use.
    """

    def __init__(self) -> None:
        self.snapshots: list[CandidateSnapshot] = []
        self.decisions: list[EvaluationDecision] = []

    def write_snapshots(self, records: list[CandidateSnapshot]) -> None:
        self.snapshots.extend(records)

    def write_decisions(self, records: list[EvaluationDecision]) -> None:
        self.decisions.extend(records)

    def clear(self) -> None:
        """Reset captured records."""
        self.snapshots.clear()
        self.decisions.clear()
