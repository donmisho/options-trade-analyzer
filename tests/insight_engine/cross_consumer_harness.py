"""Shared cross-consumer system-test harness (OTA-795).

Establishes the reusable building blocks the cross-consumer system suite runs on,
factored so OTA-798 (trace / bronze persistence assertions) imports them rather
than re-seeding:

  * :func:`build_seeded_config` — hydrate the COMPLETE seed (all three surfaces)
    from the workbook the live ``init_engine_runtime`` reads, via the same offline
    ``build_all_rows`` → ``InMemoryConfigSource`` → ``load_config`` path that
    ``test_full_seed_boot`` uses. No live DB, no live Schwab.
  * :func:`get_combined_registry` — the real screening ∪ directional ∪
    position-health formula registry (40 formulas).
  * Per-surface ``null_semantics`` maps built from each real adapter's §5.1 catalog.
  * Per-surface passing / halted candidate builders that drive the **real** adapter
    DERIVED helpers (``_compute_derived`` etc.), so the candidate inputs are produced
    by adapter code rather than fabricated from scratch.

Why candidates are built here rather than via ``adapter.produce_candidates``:
each adapter's ``produce_candidates`` fetches a live Schwab chain (screening,
directional) or reads the ``positions`` table + a live quote (position-health), so
it cannot run offline. The established offline convention (see
``tests/integration/test_options_chain_adapter.py`` and
``tests/options_rules/test_position_health_parity.py``) is to drive the adapter's
real DERIVED/COMPUTED helpers over hand-built RAW candidates. This keeps the
**evaluation path** — engine + rule libraries + seeded config — entirely real and
unmocked, which is what the suite proves.

Seed↔adapter reconciliation status (OTA-847 / OTA-850):
  * OTA-847 #2/#3/#4 fixed three of the four seed↔adapter gaps in the seed itself:
    the cushion_vs_atr gate now reads the adapter's ``cushion_vs_atr`` (was the
    phantom ``cushion_vs_atr_ratio``); ``cushion_of_price`` bounds are now percent
    (was fraction); and the ``earnings_days_past_expiry`` gate is disabled (no
    producer — tracked in OTA-849). The screening passing fixture no longer needs
    those workarounds.
  * Mismatch #1 is CLOSED by OTA-850: the delta-completeness gate is now
    structure-keyed — steady-paycheck (credit spread) gates on ``short_delta`` and
    trend-rider (debit spread) on ``long_delta``, both emitted by the adapter — so a
    faithful spread flows through data-completeness on its real leg deltas with no
    ``delta`` workaround. See ``test_delta_completeness_regression``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Callable

from app.insight_engine import (
    Candidate,
    EngineConfig,
    FormulaRegistry,
    InMemoryConfigSource,
    load_config,
)
from app.ota_adapters.engine_runtime import build_combined_registry

# Real adapter DERIVED/COMPUTED helpers + §5.1 catalogs (the "real adapters").
from app.ota_adapters.options_chain.adapter import (
    OptionsChainAdapter,
    _CATALOG as _SCREENING_CATALOG,
    _compute_derived as _screening_compute_derived,
    _compute_post_context_derived as _screening_post_context_derived,
)
from app.ota_adapters.directional.adapter import (
    DirectionalAdapter,
    _CATALOG as _DIRECTIONAL_CATALOG,
    _compute_derived as _directional_compute_derived,
)
from app.ota_adapters.position_health.adapter import (
    PositionHealthAdapter,
    _CATALOG as _POSITION_HEALTH_CATALOG,
    _compute_derived as _position_health_compute_derived,
    _direction_from_structure,
)

from scripts.seed_engine_config import DEFAULT_XLSX, build_all_rows

# Whether the build-time seed workbook is present. Tests skip when it is not,
# mirroring ``test_full_seed_boot`` (the engine_* tables are seeded from it).
SEED_WORKBOOK_AVAILABLE: bool = DEFAULT_XLSX.exists()

# Post-seed combined registry size (26 screening + 10 directional + 4
# position-health). See OTA-844 and ``test_full_seed_boot``.
EXPECTED_REGISTRY_COUNT = 40

SOURCE_APP_ID = "OTA"


# ── Seeded config (the live mixed-surface boot, offline) ─────────────────


def build_seeded_config() -> EngineConfig:
    """Hydrate the complete seed (all surfaces) the way ``init_engine_runtime`` does.

    Builds every seed row via ``build_all_rows`` (the same builder the live boot
    uses), assigns synthetic ids as DB IDENTITY stand-ins, and resolves them
    through ``InMemoryConfigSource`` → ``load_config``. Returns the combined
    ``EngineConfig`` whose ``rule_sets`` hold all nine strategies across the three
    consumer surfaces.
    """
    rules, strategies, junctions, lookups, _ = build_all_rows(DEFAULT_XLSX)

    rule_id = {r["rule_key"]: 1000 + i for i, r in enumerate(rules)}
    strat_id = {s["strategy_key"]: 100 + i for i, s in enumerate(strategies)}
    rules = [{**r, "rule_id": rule_id[r["rule_key"]]} for r in rules]
    strategies = [{**s, "strategy_id": strat_id[s["strategy_key"]]} for s in strategies]
    junctions = [
        {**j, "rule_id": rule_id[j["rule_key"]], "strategy_id": strat_id[j["strategy_key"]]}
        for j in junctions
    ]

    source = InMemoryConfigSource(
        apps=[
            {"app_id": "SHARED", "name": "Shared", "enabled": True},
            {"app_id": "OTA", "name": "OTA", "enabled": True},
        ],
        rules=rules,
        strategies=strategies,
        junction=junctions,
        lookups=lookups,
    )
    return load_config(source)


def get_combined_registry() -> FormulaRegistry:
    """The real screening ∪ directional ∪ position-health formula registry."""
    return build_combined_registry()


def _null_semantics(catalog: dict[str, Any]) -> dict[str, str | None]:
    """Build the engine's null-semantics map from an adapter's §5.1 catalog."""
    return {name: entry.null_semantics for name, entry in catalog.items()}


SCREENING_NULL_SEMANTICS = _null_semantics(_SCREENING_CATALOG)
DIRECTIONAL_NULL_SEMANTICS = _null_semantics(_DIRECTIONAL_CATALOG)
POSITION_HEALTH_NULL_SEMANTICS = _null_semantics(_POSITION_HEALTH_CATALOG)


def _future_exp(days: int = 30) -> str:
    """ISO expiration ``days`` ahead — keeps DTE-window gates deterministic."""
    return (date.today() + timedelta(days=days)).isoformat()


# ── SCREENING (options_chain adapter → steady-paycheck) ───────────────────

SCREENING_STRATEGY = "steady-paycheck"


def screening_passing_candidate() -> Candidate:
    """A credit spread that flows through every steady-paycheck gate to a verdict.

    Slightly-OTM bull_put so the seeded ``cushion_of_price`` gate (percent bounds
    after OTA-847 #3) and the ``cushion_vs_atr`` gate (OTA-847 #2) are both
    satisfied by the adapter-computed cushion, with tight per-leg bid/ask (≤ 0.15)
    and DTE inside the 21–45 window. RAW + DERIVED come from the real
    ``_compute_derived``; market-context values mirror what
    ``_fetch_market_context`` would stamp.
    """
    exp = _future_exp(30)
    nv: dict[str, Any] = {
        "underlying_price": 200.0,
        "spread_type": "bull_put",
        "option_type": "put",
        "expiration": exp,
        "long_strike": 170.0,
        "short_strike": 195.0,   # OTA-847: small OTM cushion clears the seeded percent floor
        "spread_width": 25.0,
        "long_bid": 0.20, "long_ask": 0.25,
        "short_bid": 1.00, "short_ask": 1.05,
        "long_delta": -0.05, "short_delta": -0.20,
        "long_theta": -0.02, "short_theta": 0.03,
        "long_gamma": 0.01, "short_gamma": 0.02,
        "long_vega": 0.10, "short_vega": 0.12,
        "long_volume": 800, "short_volume": 800,
        "long_oi": 4000, "short_oi": 4000,
        "long_iv": 0.28, "short_iv": 0.30,
        "next_earnings_date": None,
    }
    candidate = Candidate(
        candidate_id="screening-pass",
        candidate_type="options_trade",
        symbol="TEST",
        subject_type="TRADE_CANDIDATE",
        named_values=nv,
    )
    _screening_compute_derived(candidate)

    # Market-context values the adapter's _fetch_market_context would stamp.
    nv.update({
        "sma_8": 205.0, "sma_21": 203.0, "sma_50": 198.0,
        "sma_alignment": "BULLISH", "chart_state": "Bullish",
        "atr_14": 2.0, "atm_iv": 0.28, "iv_percentile": 55.0,
        "is_etf": False,
    })
    _screening_post_context_derived([candidate])

    # OTA-850 closed seed↔adapter mismatch #1: steady-paycheck's delta-completeness
    # gate now reads `short_delta` (the credit spread's assignment-risk leg, emitted
    # by the adapter above), so this credit spread flows through data-completeness on
    # its real leg delta — no `delta` workaround. OTA-847 #2/#3/#4 similarly fixed the
    # other three gaps in the seed itself:
    #   #2 cushion_vs_atr gate now reads the adapter's real `cushion_vs_atr`
    #      (computed above from cushion_pct/atr_14) — no `cushion_vs_atr_ratio`;
    #   #3 cushion_of_price bounds are now percent — the OTM cushion above clears them;
    #   #4 earnings_buffer_past_expiry is disabled — no `earnings_days_past_expiry`.
    return candidate


def screening_halted_candidate() -> Candidate:
    """A spread that halts at the first RAW gate (``underlying_price_floor__gte``).

    ``stock_price`` (== underlying_price) of 10 is below the seeded floor of 20,
    so the candidate halts at the very first gate — a clean, structure-stable halt.
    """
    exp = _future_exp(30)
    nv: dict[str, Any] = {
        "underlying_price": 10.0,   # below the seeded stock_price floor (20) → halt
        "spread_type": "bull_put",
        "option_type": "put",
        "expiration": exp,
        "long_strike": 5.0,
        "short_strike": 9.0,
        "spread_width": 4.0,
        "long_bid": 0.10, "long_ask": 0.15,
        "short_bid": 0.50, "short_ask": 0.55,
        "long_delta": -0.10, "short_delta": -0.20,
        "long_theta": -0.01, "short_theta": 0.02,
        "long_gamma": 0.01, "short_gamma": 0.02,
        "long_vega": 0.10, "short_vega": 0.12,
        "long_volume": 800, "short_volume": 800,
        "long_oi": 4000, "short_oi": 4000,
        "long_iv": 0.30, "short_iv": 0.30,
        "next_earnings_date": None,
    }
    candidate = Candidate(
        candidate_id="screening-halt",
        candidate_type="options_trade",
        symbol="TEST",
        subject_type="TRADE_CANDIDATE",
        named_values=nv,
    )
    _screening_compute_derived(candidate)
    return candidate


# ── DIRECTIONAL (directional adapter → directional_income) ────────────────

DIRECTIONAL_STRATEGY = "directional_income"

# The seeded non-stopping (stop_if_fail=False) gate the budget-overrun fixture
# trips — used by OTA-798 to exercise the §4.2 non-stopping-failure trace clause.
DIRECTIONAL_NONSTOPPING_GATE = "dir_budget_flag"


def _directional_thesis() -> dict[str, Any]:
    return {
        "thesis_direction": "bullish",
        "thesis_target_price": 220.0,
        "thesis_risk_budget": 5000.0,
        "thesis_timeframe_days": 30,
        "thesis_conviction": "high",
    }


def _directional_market_context(nv: dict[str, Any]) -> None:
    nv.update({
        "sma_8": 205.0, "sma_21": 203.0, "sma_50": 198.0,
        "sma_alignment": "BULLISH", "chart_state": "Bullish",
        "atr_14": 3.0, "atm_iv": 0.30, "iv_percentile": 50.0,
        "next_earnings_date": None, "earnings_unknown": True,
    })


def directional_passing_candidate() -> Candidate:
    """A bull_call debit spread that fits the thesis and reaches a verdict.

    Healthy debit (long/short mid spread > 0), liquidity above the OI/volume
    floors, no earnings in window. RAW + DERIVED via the real ``_compute_derived``.
    """
    exp = _future_exp(30)
    nv: dict[str, Any] = {
        **_directional_thesis(),
        "underlying_price": 200.0,
        "spread_type": "bull_call",
        "option_type": "call",
        "expiration": exp,
        "long_strike": 200.0,
        "short_strike": 210.0,
        "spread_width": 10.0,
        "long_bid": 3.00, "long_ask": 3.40,
        "short_bid": 1.20, "short_ask": 1.50,
        "long_delta": 0.55, "short_delta": 0.35,
        "long_theta": -0.03, "short_theta": 0.02,
        "long_iv": 0.30, "short_iv": 0.28,
        "open_interest": 500, "volume": 200,
    }
    candidate = Candidate(
        candidate_id="directional-pass",
        candidate_type="directional",
        symbol="TEST",
        subject_type="THESIS_COMPARISON",
        named_values=nv,
    )
    _directional_compute_derived(candidate)
    _directional_market_context(nv)
    return candidate


def directional_halted_candidate() -> Candidate:
    """A thesis-fit spread that halts at the OI floor (``dir_open_interest_floor``).

    Identical to the passing spread except ``open_interest`` (5) is below the
    seeded floor of 100 — a clean liquidity-gate halt after the data-completeness
    gates pass.
    """
    exp = _future_exp(30)
    nv: dict[str, Any] = {
        **_directional_thesis(),
        "underlying_price": 200.0,
        "spread_type": "bull_call",
        "option_type": "call",
        "expiration": exp,
        "long_strike": 200.0,
        "short_strike": 210.0,
        "spread_width": 10.0,
        "long_bid": 3.00, "long_ask": 3.40,
        "short_bid": 1.20, "short_ask": 1.50,
        "long_delta": 0.55, "short_delta": 0.35,
        "long_theta": -0.03, "short_theta": 0.02,
        "long_iv": 0.30, "short_iv": 0.28,
        "open_interest": 5,    # below the seeded OI floor (100) → halt
        "volume": 200,
    }
    candidate = Candidate(
        candidate_id="directional-halt",
        candidate_type="directional",
        symbol="TEST",
        subject_type="THESIS_COMPARISON",
        named_values=nv,
    )
    _directional_compute_derived(candidate)
    _directional_market_context(nv)
    return candidate


def directional_nonstopping_failure_candidate() -> Candidate:
    """A thesis-fit bull_call spread whose cost exceeds the risk budget.

    Identical to the passing spread except ``thesis_risk_budget`` (100) is below
    the trade cost (~185), so the DERIVED ``fits_budget`` is False and the
    non-stopping ``dir_budget_flag`` gate (stop_if_fail=False) **fails and is
    recorded** while the candidate continues to a verdict. This is the OTA-798
    fixture that exercises the §4.2 mandatory-trace clauses in one run: a
    non-stopping gate failure (recorded, not terminal) and a zero-penalty decision
    (``held_penalty`` is None → ``score_contribution`` None in bronze).
    """
    exp = _future_exp(30)
    nv: dict[str, Any] = {
        **_directional_thesis(),
        "thesis_risk_budget": 100.0,   # below the ~185 trade cost → fits_budget False
        "underlying_price": 200.0,
        "spread_type": "bull_call",
        "option_type": "call",
        "expiration": exp,
        "long_strike": 200.0,
        "short_strike": 210.0,
        "spread_width": 10.0,
        "long_bid": 3.00, "long_ask": 3.40,
        "short_bid": 1.20, "short_ask": 1.50,
        "long_delta": 0.55, "short_delta": 0.35,
        "long_theta": -0.03, "short_theta": 0.02,
        "long_iv": 0.30, "short_iv": 0.28,
        "open_interest": 500, "volume": 200,
    }
    candidate = Candidate(
        candidate_id="directional-nonstopping-fail",
        candidate_type="directional",
        symbol="TEST",
        subject_type="THESIS_COMPARISON",
        named_values=nv,
    )
    _directional_compute_derived(candidate)
    _directional_market_context(nv)
    return candidate


# ── POSITION_HEALTH (position_health adapter → position_health_full) ───────

POSITION_HEALTH_STRATEGY = "position_health_full"


def _position_candidate(
    *,
    candidate_id: str,
    entry_price: float | None,
    current_mark: float | None,
    current_underlying: float | None,
    structure: str | None,
    warning: float | None,
    stop: float | None,
) -> Candidate:
    """Build a position candidate with RAW values, then real DERIVED computation."""
    nv: dict[str, Any] = {
        "position_entry_price": entry_price,
        "position_structure": structure,
        "position_structure_direction": _direction_from_structure(structure),
        "position_exit_warning_underlying": warning,
        "position_exit_stop_underlying": stop,
        "position_exit_scale_out_underlying": None,
        "position_exit_levels_complete": warning is not None and stop is not None,
        "current_underlying_price": current_underlying,
        "current_position_mark": current_mark,
        "position_entry_date": "2026-01-15",
        "position_expiration": "2026-09-20",
        "position_entry_underlying_price": None,
    }
    candidate = Candidate(
        candidate_id=candidate_id,
        candidate_type="position",
        symbol="TEST",
        subject_type="POSITION",
        subject_id=candidate_id,
        named_values=nv,
    )
    _position_health_compute_derived(candidate)
    return candidate


def position_health_passing_candidate() -> Candidate:
    """An open bull_put_credit position well clear of its exit levels → verdict A.

    Positive P&L (mark 1.80 vs entry 1.50) and underlying (185) well above both
    warning (180) and stop (175): every gate passes, both scoring criteria
    contribute, neither adjustment fires.
    """
    return _position_candidate(
        candidate_id="position-health-pass",
        entry_price=1.50,
        current_mark=1.80,
        current_underlying=185.0,
        structure="bull_put_credit",
        warning=180.0,
        stop=175.0,
    )


def position_health_halted_candidate() -> Candidate:
    """A position with no entry price → halts at ``ph_entry_price_required``."""
    return _position_candidate(
        candidate_id="position-health-halt",
        entry_price=None,   # FAIL_CLOSED data-completeness gate → halt
        current_mark=1.80,
        current_underlying=185.0,
        structure="bull_put_credit",
        warning=180.0,
        stop=175.0,
    )


# ── Surface case registry (the parametrization the suite iterates) ─────────


@dataclass(frozen=True)
class SurfaceCase:
    """One consumer surface, fully specified for an end-to-end run."""
    surface: str
    strategy_key: str
    null_semantics: dict[str, str | None]
    passing_builder: Callable[[], Candidate]
    halted_builder: Callable[[], Candidate]
    expected_halt_gate: str
    adapter_factory: Callable[[], Any]

    def make_adapter(self) -> Any:
        return self.adapter_factory()


SURFACE_CASES: tuple[SurfaceCase, ...] = (
    SurfaceCase(
        surface="SCREENING",
        strategy_key=SCREENING_STRATEGY,
        null_semantics=SCREENING_NULL_SEMANTICS,
        passing_builder=screening_passing_candidate,
        halted_builder=screening_halted_candidate,
        expected_halt_gate="underlying_price_floor__gte",
        adapter_factory=OptionsChainAdapter,
    ),
    SurfaceCase(
        surface="DIRECTIONAL",
        strategy_key=DIRECTIONAL_STRATEGY,
        null_semantics=DIRECTIONAL_NULL_SEMANTICS,
        passing_builder=directional_passing_candidate,
        halted_builder=directional_halted_candidate,
        expected_halt_gate="dir_open_interest_floor",
        adapter_factory=DirectionalAdapter,
    ),
    SurfaceCase(
        surface="POSITION_HEALTH",
        strategy_key=POSITION_HEALTH_STRATEGY,
        null_semantics=POSITION_HEALTH_NULL_SEMANTICS,
        passing_builder=position_health_passing_candidate,
        halted_builder=position_health_halted_candidate,
        expected_halt_gate="ph_entry_price_required",
        adapter_factory=PositionHealthAdapter,
    ),
)
