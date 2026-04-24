"""
AMZN 260/270 May 15 regression test — OTA-502 (Phase 6) + OTA-506 (Phase 5).

OTA-502 section verifies the full gate scaffolding:
  - Earnings gate triggers → verdict PASS
  - reason includes "2026-04-29" and "5 trading days"
  - effective_dte_override is None (hard-block, not modifier)

OTA-506 section verifies classifier + DTE payload in warning-band scenario:
  - Earnings 10 biz days from entry → warning band, not hard PASS
  - effective_dte_override = 9
  - TREND_RIDER disqualified (min=14); LOTTERY_TICKET is the only viable strategy
  - strategy_fit payload carries both nominal_dte and effective_dte
  - dte_source == "earnings_in_window"

Golden-path sanity check:
  - No earnings in window → effective_dte == nominal_dte → TR can still win
"""

import pytest
from datetime import date
from unittest.mock import AsyncMock

from app.analysis.hard_gates import (
    GateTradeContext,
    _clear_gates,
    evaluate_hard_gates,
    register_gate,
)
from app.analysis.hard_gates.earnings_gate import EarningsInWindowGate
from app.analysis.strategy_classifier import classify_best_strategy
from app.analysis.strategy_scorer import StrategyScore


# ─── Fixture parameters ───────────────────────────────────────────────────────

AMZN_SYMBOL      = "AMZN"
AMZN_ENTRY       = date(2026, 4, 22)   # Wednesday
AMZN_EXPIRY      = date(2026, 5, 15)   # Friday  — 260/270 May 15 expiry
AMZN_EARNINGS    = date(2026, 4, 29)   # Wednesday — 5 biz days from entry (hard PASS)
AMZN_DTE         = (AMZN_EXPIRY - AMZN_ENTRY).days   # 23 nominal DTE
AMZN_EV          = -5.86               # computed EV (context only; OTA-503 uses this)

# OTA-506: warning-band fixture — earnings 10 biz days from entry.
# Apr22 → May6: Apr23(1) Apr24(2) Apr27(3) Apr28(4) Apr29(5)
#               Apr30(6) May1(7)  May4(8)  May5(9)  May6(10)
AMZN_EARNINGS_WARNING = date(2026, 5, 6)   # 10 biz days → effective_dte_override = 9


@pytest.fixture(autouse=True)
def isolated_registry():
    """Each test gets a clean gate registry."""
    _clear_gates()
    yield
    _clear_gates()


def _amzn_ctx() -> GateTradeContext:
    return GateTradeContext(
        symbol=AMZN_SYMBOL,
        entry_date=AMZN_ENTRY,
        expiry_date=AMZN_EXPIRY,
        dte=AMZN_DTE,
        trade={
            "buy_strike": 260,
            "sell_strike": 270,
            "expiration": "2026-05-15",
            "total_ev": AMZN_EV,
        },
        db=None,
    )


def _gate_with_earnings(earnings_date) -> EarningsInWindowGate:
    """Build an EarningsInWindowGate whose DB lookup is patched to return a fixed date."""
    gate = EarningsInWindowGate(source=object())
    gate._fetch_earnings_date = AsyncMock(return_value=earnings_date)
    return gate


# ─── AMZN regression ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_amzn_regression_full_stack_verdict_is_pass():
    """
    AMZN 260/270 May 15 with earnings Apr 29 (5 biz days from entry):
    evaluate_hard_gates must return triggered=True, verdict=PASS.
    """
    register_gate(_gate_with_earnings(AMZN_EARNINGS))

    result = await evaluate_hard_gates(_amzn_ctx())

    assert result is not None, "Gate should have returned a result"
    assert result.triggered is True, f"Gate should have triggered; got triggered={result.triggered}"
    assert result.verdict == "PASS", f"Expected PASS, got {result.verdict!r}"
    assert result.gate_id == "earnings_in_window"


@pytest.mark.asyncio
async def test_amzn_regression_reason_contains_expected_substrings():
    """Reason string must include the earnings date and trading-day count."""
    register_gate(_gate_with_earnings(AMZN_EARNINGS))

    result = await evaluate_hard_gates(_amzn_ctx())

    assert result is not None
    assert "2026-04-29" in result.reason, f"Expected earnings date in reason: {result.reason!r}"
    assert "5 trading days" in result.reason, f"Expected '5 trading days' in reason: {result.reason!r}"


@pytest.mark.asyncio
async def test_amzn_regression_no_effective_dte_on_hard_block():
    """Hard-block gates must not set effective_dte_override — that is for warning-band only."""
    register_gate(_gate_with_earnings(AMZN_EARNINGS))

    result = await evaluate_hard_gates(_amzn_ctx())

    assert result is not None
    assert result.effective_dte_override is None, (
        f"Hard-block should not override DTE; got {result.effective_dte_override}"
    )


# ─── Golden path ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_golden_path_no_earnings_gate_does_not_trigger():
    """
    Symbol with null earnings data → gate does NOT fire.
    evaluate_hard_gates returns None → scoring pipeline is unaffected.
    """
    register_gate(_gate_with_earnings(None))

    result = await evaluate_hard_gates(_amzn_ctx())

    assert result is None, (
        f"Gate should return None when earnings are null; got {result}"
    )


@pytest.mark.asyncio
async def test_golden_path_earnings_after_expiry_gate_does_not_trigger():
    """
    Earnings after expiry → outside trade window → gate does NOT fire.
    Scoring pipeline must proceed normally.
    """
    earnings_after_expiry = date(2026, 5, 17)   # 2 days after May 15 expiry
    register_gate(_gate_with_earnings(earnings_after_expiry))

    result = await evaluate_hard_gates(_amzn_ctx())

    assert result is None, (
        f"Gate should not fire for out-of-window earnings; got {result}"
    )


@pytest.mark.asyncio
async def test_golden_path_no_gates_registered():
    """
    With zero registered gates, evaluate_hard_gates returns None.
    This confirms the pipeline doesn't break before OTA-502 ships.
    """
    result = await evaluate_hard_gates(_amzn_ctx())

    assert result is None


# ─── OTA-503: negative EV standalone regression ───────────────────────────────
# Earnings moved AFTER expiry so only the negative-EV gate can fire.
# Proves NegativeEVGate works independently, not just as defence-in-depth.


def _amzn_ctx_ev_only() -> GateTradeContext:
    """AMZN-style trade: earnings after expiry, EV still negative."""
    return GateTradeContext(
        symbol=AMZN_SYMBOL,
        entry_date=AMZN_ENTRY,
        expiry_date=AMZN_EXPIRY,
        dte=AMZN_DTE,
        trade={
            "buy_strike": 260,
            "sell_strike": 270,
            "expiration": "2026-05-15",
            "total_ev": AMZN_EV,
        },
        db=None,
        expected_value=AMZN_EV,    # -5.86
    )


@pytest.mark.asyncio
async def test_amzn_ev_only_negative_ev_gate_fires():
    """
    AMZN trade: earnings AFTER expiry (outside window) + EV = -5.86.
    EarningsInWindowGate must NOT fire; NegativeEVGate must fire.
    Verdict: PASS via negative_ev gate.
    """
    from app.analysis.hard_gates.earnings_gate import EarningsInWindowGate
    from app.analysis.hard_gates.negative_ev_gate import NegativeEVGate

    earnings_gate = EarningsInWindowGate(source=object())
    earnings_gate._fetch_earnings_date = AsyncMock(return_value=date(2026, 5, 17))  # after expiry
    register_gate(earnings_gate)
    register_gate(NegativeEVGate())

    result = await evaluate_hard_gates(_amzn_ctx_ev_only())

    assert result is not None
    assert result.triggered is True
    assert result.gate_id == "negative_ev", (
        f"Expected negative_ev gate; got {result.gate_id!r}"
    )
    assert result.verdict == "PASS"
    assert "Negative expected value" in result.reason


@pytest.mark.asyncio
async def test_amzn_ev_only_reason_contains_ev_value():
    """NegativeEVGate reason must surface the EV amount (-5.86)."""
    from app.analysis.hard_gates.earnings_gate import EarningsInWindowGate
    from app.analysis.hard_gates.negative_ev_gate import NegativeEVGate

    earnings_gate = EarningsInWindowGate(source=object())
    earnings_gate._fetch_earnings_date = AsyncMock(return_value=date(2026, 5, 17))
    register_gate(earnings_gate)
    register_gate(NegativeEVGate())

    result = await evaluate_hard_gates(_amzn_ctx_ev_only())

    assert result is not None
    assert "-5.86" in result.reason


@pytest.mark.asyncio
async def test_amzn_both_gates_earnings_reason_wins():
    """
    AMZN original case: earnings Apr 29 (in window) + EV = -5.86.
    Both gates would fire. Earnings gate (registered first) must win.
    Confirms Option A ordering holds for the canonical AMZN fixture.
    """
    from app.analysis.hard_gates.earnings_gate import EarningsInWindowGate
    from app.analysis.hard_gates.negative_ev_gate import NegativeEVGate

    # Use original AMZN ctx WITH expected_value populated
    ctx = GateTradeContext(
        symbol=AMZN_SYMBOL,
        entry_date=AMZN_ENTRY,
        expiry_date=AMZN_EXPIRY,
        dte=AMZN_DTE,
        trade={"buy_strike": 260, "sell_strike": 270, "expiration": "2026-05-15", "total_ev": AMZN_EV},
        db=None,
        expected_value=AMZN_EV,
    )

    earnings_gate = EarningsInWindowGate(source=object())
    earnings_gate._fetch_earnings_date = AsyncMock(return_value=AMZN_EARNINGS)  # Apr 29 — in window
    register_gate(earnings_gate)
    register_gate(NegativeEVGate())

    result = await evaluate_hard_gates(ctx)

    assert result is not None
    assert result.gate_id == "earnings_in_window", (
        f"Earnings gate should win on double-trigger; got {result.gate_id!r}"
    )
    assert "Earnings" in result.reason
    assert "Negative expected value" not in result.reason


# ─── OTA-506: Classifier regression — warning-band AMZN trade ────────────────
#
# Fixture: AMZN 260/270 May 15, earnings May 6 (10 biz days from entry).
# Earnings gate → warning band → effective_dte_override = 9.
# Classifier with effective_dte=9:
#   trend-rider min=14     → DISQUALIFIED
#   steady-paycheck min=14 → DISQUALIFIED
#   weekly-grind min=14    → DISQUALIFIED
#   lottery-ticket min=7   → VIABLE (9 ≥ 7 and 9 ≤ 60)
#
# Expected: best_fit="lottery-ticket", dte_source="earnings_in_window"


def _all_four_candidates(tr_score=71, sp_score=60, wg_score=55, lt_score=40):
    """Four StrategyScore proxies with configurable scores. Default: TR would win."""
    return [
        StrategyScore("trend-rider",     "Trend Rider",     tr_score, None, "", {}),
        StrategyScore("steady-paycheck", "Steady Paycheck", sp_score, None, "", {}),
        StrategyScore("weekly-grind",    "Weekly Grind",    wg_score, None, "", {}),
        StrategyScore("lottery-ticket",  "Lottery Ticket",  lt_score, None, "", {}),
    ]


@pytest.mark.asyncio
async def test_ota506_warning_band_gate_sets_effective_dte():
    """
    With earnings 10 biz days out, gate fires in warning-band mode.
    effective_dte_override must be 9 (= 10 - 1).
    """
    ctx = GateTradeContext(
        symbol=AMZN_SYMBOL,
        entry_date=AMZN_ENTRY,
        expiry_date=AMZN_EXPIRY,
        dte=AMZN_DTE,
        trade={"buy_strike": 260, "sell_strike": 270, "expiration": "2026-05-15"},
        db=None,
    )
    gate = EarningsInWindowGate(source=object())
    gate._fetch_earnings_date = AsyncMock(return_value=AMZN_EARNINGS_WARNING)
    register_gate(gate)

    result = await evaluate_hard_gates(ctx)

    assert result is not None
    assert result.triggered is False, "Warning band must NOT hard-block"
    assert result.effective_dte_override == 9, (
        f"Expected effective_dte_override=9; got {result.effective_dte_override}"
    )


@pytest.mark.asyncio
async def test_ota506_trend_rider_disqualified_at_effective_dte_9():
    """
    With effective_dte=9 (from warning-band gate), TREND_RIDER must be
    disqualified by the classifier (min=14).
    """
    result = classify_best_strategy(_all_four_candidates(), effective_dte=9)
    assert result.best_fit != "trend-rider", (
        f"TREND_RIDER must be disqualified at dte=9; got best_fit={result.best_fit!r}"
    )


@pytest.mark.asyncio
async def test_ota506_lottery_ticket_wins_at_effective_dte_9():
    """
    With effective_dte=9, only LOTTERY_TICKET qualifies. Even though TR has
    the highest score (71), LT must be selected.
    """
    result = classify_best_strategy(_all_four_candidates(tr_score=71, lt_score=40), effective_dte=9)
    assert result.best_fit == "lottery-ticket", (
        f"Expected lottery-ticket at dte=9; got {result.best_fit!r}"
    )


@pytest.mark.asyncio
async def test_ota506_strategy_fit_payload_warning_band():
    """
    Simulate what evaluate_structured() builds for strategy_fit when the
    earnings gate fires in warning-band mode.

    Asserts:
      - best_fit != "trend-rider"
      - effective_dte == 9
      - nominal_dte == AMZN_DTE (23)
      - dte_source == "earnings_in_window"
    """
    nominal_dte = AMZN_DTE       # 23
    effective_dte = 9            # gate override

    classification = classify_best_strategy(_all_four_candidates(), effective_dte=effective_dte)
    strategy_fit = {
        "best_fit":      classification.best_fit,
        "reason":        classification.reason,
        "nominal_dte":   nominal_dte,
        "effective_dte": effective_dte,
        "dte_source":    "earnings_in_window" if effective_dte != nominal_dte else "nominal",
    }

    assert strategy_fit["best_fit"] != "trend-rider"
    assert strategy_fit["effective_dte"] == 9
    assert strategy_fit["nominal_dte"] == 23
    assert strategy_fit["dte_source"] == "earnings_in_window"


# ─── OTA-506: Sanity check — no earnings in window ────────────────────────────
#
# When no earnings gate fires: effective_dte == nominal_dte.
# TREND_RIDER is viable at nominal DTE=23 and wins with highest score.


@pytest.mark.asyncio
async def test_ota506_no_earnings_trend_rider_can_win():
    """
    No earnings in window → effective_dte = nominal_dte = 23.
    TREND_RIDER (min=14, max=60) is viable and wins if it has the highest score.
    """
    nominal_dte = AMZN_DTE   # 23
    effective_dte = nominal_dte

    result = classify_best_strategy(_all_four_candidates(tr_score=71), effective_dte=effective_dte)

    assert result.best_fit == "trend-rider", (
        f"TR should win with highest score at dte={effective_dte}; got {result.best_fit!r}"
    )


@pytest.mark.asyncio
async def test_ota506_no_earnings_strategy_fit_dte_source_nominal():
    """
    No gate override → effective_dte == nominal_dte → dte_source must be "nominal".
    """
    nominal_dte = AMZN_DTE
    effective_dte = nominal_dte  # no override

    classification = classify_best_strategy(_all_four_candidates(), effective_dte=effective_dte)
    strategy_fit = {
        "best_fit":      classification.best_fit,
        "reason":        classification.reason,
        "nominal_dte":   nominal_dte,
        "effective_dte": effective_dte,
        "dte_source":    "earnings_in_window" if effective_dte != nominal_dte else "nominal",
    }

    assert strategy_fit["dte_source"] == "nominal"
    assert strategy_fit["effective_dte"] == strategy_fit["nominal_dte"]
