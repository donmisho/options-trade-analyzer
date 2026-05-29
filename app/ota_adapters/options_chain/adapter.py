"""
OptionsChainAdapter — §5 input adapter for the screening surface.

Three contract methods:
    produce_candidates  — fetch chain, build Candidate stream (stub: OTA-714/715)
    populate_computed   — COMPUTED callback matching engine ComputedAdapter (OTA-716)
    input_catalog       — §5.1 catalog of all named values (sparse until OTA-723)

This adapter does NOT run rules, assign scores, or reference strategies.

OTA-713
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.insight_engine import Candidate, NamedValue, Tier

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CatalogEntry:
    """One entry in the §5.1 input catalog.

    Attributes:
        name:             Named-value name as referenced by rules.
        tier:             RAW | DERIVED | COMPUTED.
        value_type:       "number", "enum", "date", "boolean".
        null_semantics:   FAIL_OPEN | FAIL_CLOSED | SKIP | None.
        producer_ref:     Dotted path to the adapter method that produces
                          this value (diagnostic only; not used by engine).
    """
    name: str
    tier: Tier
    value_type: str
    null_semantics: str | None
    producer_ref: str


class OptionsChainAdapter:
    """Input adapter for options-chain screening (§5 contract).

    Skeleton created by OTA-713. Producer logic lands in OTA-714–722;
    full catalog content in OTA-723.
    """

    # ── §5.1 — input catalog ────────────────────────────────────────

    def input_catalog(self) -> list[CatalogEntry]:
        """Return the catalog of every named value this adapter produces.

        Each entry carries name, tier, type, null semantics, and producer
        reference per §5.1. Sparse in OTA-713; populated by OTA-714–723.
        """
        return list(_CATALOG.values())

    # ── §5 — produce candidates ─────────────────────────────────────

    async def produce_candidates(
        self,
        scan_request: dict[str, Any],
    ) -> list[Candidate]:
        """Fetch chain data and build a stream of Candidate records.

        Parameters
        ----------
        scan_request : dict
            Consumer-supplied request parameters (symbol, DTE range,
            strike range, option type filters, etc.).

        Returns
        -------
        list[Candidate]
            One Candidate per trade structure found in the chain.

        Stub in OTA-713 — real construction lands in OTA-714/OTA-715.
        """
        logger.debug(
            "OptionsChainAdapter.produce_candidates called (stub) "
            "with scan_request=%s",
            scan_request,
        )
        return []

    # ── §5.2 — COMPUTED callback (engine ComputedAdapter protocol) ──

    def populate_computed(
        self,
        candidates: list[Candidate],
        needed: set[str],
    ) -> None:
        """Populate COMPUTED named values on surviving candidates.

        Matches the engine's ``ComputedAdapter`` protocol exactly
        (OTA-702, pipeline.py). Mutates candidates in-place.

        Stub in OTA-713 — real COMPUTED math lands in OTA-716.
        """
        logger.debug(
            "OptionsChainAdapter.populate_computed called (stub) "
            "needed=%s, candidates=%d",
            needed,
            len(candidates),
        )


# ── Sparse catalog (OTA-713) ──────────────────────────────────────────
# Entries added by OTA-714–722 as each producer lands; full publish OTA-723.

_CATALOG: dict[str, CatalogEntry] = {}
