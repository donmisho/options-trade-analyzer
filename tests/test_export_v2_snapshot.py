"""
Snapshot tests for Export MD v2 envelope (OTA-638, OTA-641).

Tests the v2 header block (Schema version, Strategy profile, DTE, spread_type ENUM,
Current P&L, Last monitored), Technicals, Earnings, and footer against committed
expected output.

Uses lightweight stub objects instead of real DB models to keep the test
independent of the database layer.
"""

import json
import re
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from app.api.export_routes import (
    _build_trade_markdown,
    _build_position_markdown,
    format_spread_type_enum,
    _fmt_signed_pnl,
    _compute_dte,
    _V2_FOOTER,
    _compute_sma,
    _compute_atr,
    sma_alignment_narrative,
    distance_from_50d_narrative,
    _build_technicals_section,
    _build_earnings_section,
    _build_legs_table,
    _build_net_metrics_v2,
    _build_greeks_iv_section,
    _enrich_legs_from_chain,
    _fmt_iv_1d,
    _fmt_thousands,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────

def _make_trade_candidate():
    """Fixed trade candidate stub matching v2 QQQ example shape."""
    return SimpleNamespace(
        trade_key="abc-123-def",
        user_id="user-1",
        symbol="QQQ",
        structure="bear_put_debit",
        leg_count=2,
        legs=json.dumps([
            {
                "side": "BUY",
                "option_type": "PUT",
                "strike": 480.0,
                "expiration": "2026-06-01",
                "qty": 1,
                "bid": 5.20,
                "ask": 5.40,
                "delta": -0.42,
                "iv": 0.28,
            },
            {
                "side": "SELL",
                "option_type": "PUT",
                "strike": 470.0,
                "expiration": "2026-06-01",
                "qty": 1,
                "bid": 2.80,
                "ask": 3.00,
                "delta": -0.25,
                "iv": 0.30,
            },
        ]),
        net_metrics=json.dumps({
            "entry_price": 2.40,
            "max_profit": 7.60,
            "max_loss": 2.40,
            "breakeven": 477.60,
            "net_bid_ask": 0.40,
            "iv_rank": 45.0,
            "scenario_weighted_ev": 1.20,
            "prob_of_profit": 0.38,
        }),
        underlying_spot=485.50,
        pipeline_score=72.0,
        pipeline_components=json.dumps({"momentum": 0.8, "iv_rank": 0.6}),
        scan_source="verticals_scanner",
        scan_strategy_key="trend-rider",
        scanned_at=datetime(2026, 5, 11, 18, 0, 0, tzinfo=timezone.utc),
        claude_evaluation=json.dumps({
            "verdict": "FAVORABLE",
            "score": 72.0,
            "claude_read": "Bearish momentum with solid risk/reward.",
            "key_risks": ["Reversal above 490"],
            "thesis_invalidators": ["QQQ closes above 490 for two consecutive days"],
        }),
    )


def _make_position(last_monitored_at=None, current_pnl=0.0):
    """Fixed position stub matching v2 QQQ example shape."""
    return SimpleNamespace(
        position_id="pos-999-xyz",
        user_id="user-1",
        symbol="QQQ",
        strategy_key="steady-paycheck",
        trade_structure=json.dumps({
            "trade_type": "bull_put_credit",
            "short_strike": 470,
            "long_strike": 460,
            "expiration": "2026-06-01",
            "max_profit": 1.80,
            "max_loss": 8.20,
            "breakeven": 468.20,
            "legs": [
                {
                    "side": "SELL",
                    "option_type": "PUT",
                    "strike": 470.0,
                    "expiration": "2026-06-01",
                    "qty": 1,
                    "bid": 3.00,
                    "ask": 3.20,
                    "delta": -0.25,
                    "iv": 0.30,
                },
                {
                    "side": "BUY",
                    "option_type": "PUT",
                    "strike": 460.0,
                    "expiration": "2026-06-01",
                    "qty": 1,
                    "bid": 1.10,
                    "ask": 1.30,
                    "delta": -0.15,
                    "iv": 0.32,
                },
            ],
        }),
        source="PAPER",
        status="FOLLOWING",
        entry_price=1.80,
        entry_date=datetime(2026, 5, 11, tzinfo=timezone.utc),
        entry_greeks=None,
        entry_iv_rank=45.0,
        entry_sma_alignment=None,
        entry_underlying_price=485.50,
        claude_probability_matrix=None,
        claude_exit_levels=None,
        claude_verdict=json.dumps({
            "verdict": "FAVORABLE",
            "score": 68.0,
            "claude_read": "Credit collected with room to run.",
        }),
        claude_score=68,
        health_grade="A",
        current_price=1.50,
        current_pnl=current_pnl,
        last_monitored_at=last_monitored_at or datetime(2026, 5, 11, 18, 22, 0, tzinfo=timezone.utc),
        exit_price=None,
        exit_date=None,
        exit_reason=None,
        outcome_pnl=None,
        created_at=datetime(2026, 5, 11, tzinfo=timezone.utc),
        updated_at=datetime(2026, 5, 11, tzinfo=timezone.utc),
    )


def _mock_db():
    """Create a mock AsyncSession that returns no symbol_reference rows by default."""
    db = AsyncMock()
    result = MagicMock()
    result.fetchone.return_value = None
    db.execute.return_value = result
    return db


# ─── Helper unit tests ──────────────────────────────────────────────────────

class TestFormatSpreadTypeEnum:
    def test_canonical_values(self):
        assert format_spread_type_enum("BULL_PUT_CREDIT") == "BULL_PUT_CREDIT"
        assert format_spread_type_enum("BEAR_CALL_CREDIT") == "BEAR_CALL_CREDIT"
        assert format_spread_type_enum("BEAR_PUT_DEBIT") == "BEAR_PUT_DEBIT"
        assert format_spread_type_enum("BULL_CALL_DEBIT") == "BULL_CALL_DEBIT"

    def test_lowercase_input(self):
        assert format_spread_type_enum("bull_put_credit") == "BULL_PUT_CREDIT"
        assert format_spread_type_enum("bear_put_debit") == "BEAR_PUT_DEBIT"

    def test_space_separated(self):
        assert format_spread_type_enum("Bull Put Credit") == "BULL_PUT_CREDIT"

    def test_none_returns_unknown(self):
        assert format_spread_type_enum(None) == "UNKNOWN"
        assert format_spread_type_enum("") == "UNKNOWN"

    def test_unrecognized_returns_unknown(self):
        assert format_spread_type_enum("iron_condor") == "UNKNOWN"


class TestFmtSignedPnl:
    def test_positive(self):
        assert _fmt_signed_pnl(1.5) == "+1.50"

    def test_negative(self):
        assert _fmt_signed_pnl(-2.3) == "-2.30"

    def test_zero(self):
        assert _fmt_signed_pnl(0) == "+0.00"

    def test_none(self):
        assert _fmt_signed_pnl(None) == "N/A"


class TestComputeDte:
    def test_normal(self):
        ref = datetime(2026, 5, 11, tzinfo=timezone.utc)
        assert _compute_dte("2026-06-01", ref) == 21

    def test_same_day(self):
        ref = datetime(2026, 6, 1, tzinfo=timezone.utc)
        assert _compute_dte("2026-06-01", ref) == 0

    def test_past_returns_zero(self):
        ref = datetime(2026, 6, 5, tzinfo=timezone.utc)
        assert _compute_dte("2026-06-01", ref) == 0

    def test_missing_raises_422(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _compute_dte(None)
        assert exc_info.value.status_code == 422


# ─── SMA / ATR computation tests ──────────────────────────────────────────

class TestComputeSma:
    def test_basic(self):
        prices = [10.0, 20.0, 30.0, 40.0, 50.0]
        assert _compute_sma(prices, 3) == pytest.approx(40.0)  # (30+40+50)/3

    def test_insufficient_data(self):
        assert _compute_sma([10.0, 20.0], 5) is None

    def test_exact_period(self):
        prices = [1.0, 2.0, 3.0]
        assert _compute_sma(prices, 3) == pytest.approx(2.0)


class TestComputeAtr:
    def test_basic(self):
        # 16 bars → 15 true ranges, period=14 → enough for ATR
        bars = [{"high": 100 + i, "low": 99 + i, "close": 99.5 + i} for i in range(16)]
        result = _compute_atr(bars, 14)
        assert result is not None
        assert result > 0

    def test_insufficient_data(self):
        bars = [{"high": 10, "low": 9, "close": 9.5} for _ in range(5)]
        assert _compute_atr(bars, 14) is None


# ─── SMA alignment unit tests (OTA-641) ─────────────────────────────────────

class TestSmaAlignmentNarrative:
    def test_bullish_stack(self):
        result = sma_alignment_narrative(
            spot=730.0, sma8=725.0, sma21=720.0, sma50=715.0
        )
        assert result == "bullish stack — price above 8 > 21 > 50 SMA."

    def test_bearish_stack(self):
        result = sma_alignment_narrative(
            spot=700.0, sma8=705.0, sma21=710.0, sma50=715.0
        )
        assert result == "bearish stack — price below 8 < 21 < 50 SMA."

    def test_clustered(self):
        # All SMAs within 0.5% of spot
        result = sma_alignment_narrative(
            spot=500.0, sma8=500.5, sma21=500.3, sma50=499.8
        )
        assert "clustered" in result
        assert "Trend undefined" in result

    def test_mixed_matches_qqq_sample(self):
        """The mixed case must match the QQQ sample's exact rendering format."""
        # Price below 8 and 50, above 21 (QQQ sample scenario)
        result = sma_alignment_narrative(
            spot=715.0, sma8=717.32, sma21=713.85, sma50=720.71
        )
        assert result == "mixed — price below 8 and 50, above 21. Not a clean bullish or bearish stack."


class TestDistanceFrom50dNarrative:
    def test_within_range(self):
        result = distance_from_50d_narrative(spot=720.0, sma_50=720.71)
        assert "within range, not extended" in result

    def test_somewhat_extended(self):
        result = distance_from_50d_narrative(spot=740.0, sma_50=720.0)
        assert "somewhat extended" in result

    def test_extended(self):
        result = distance_from_50d_narrative(spot=760.0, sma_50=720.0)
        assert "extended" in result
        assert "somewhat" not in result

    def test_negative_distance(self):
        result = distance_from_50d_narrative(spot=700.0, sma_50=720.71)
        assert "\u2212" in result  # Unicode minus sign
        assert "within range" not in result


# ─── Trade snapshot (OTA-638) ───────────────────────────────────────────────

class TestTradeV2Envelope:
    @pytest.mark.asyncio
    async def test_header_contains_schema_version(self):
        with patch("app.api.export_routes._build_technicals_section", new_callable=AsyncMock, return_value=""), \
             patch("app.api.export_routes._build_earnings_section", new_callable=AsyncMock, return_value=""):
            body, _ = await _build_trade_markdown(_make_trade_candidate(), _mock_db())
        assert "**Schema version:** 2.0" in body

    @pytest.mark.asyncio
    async def test_header_contains_strategy_profile(self):
        with patch("app.api.export_routes._build_technicals_section", new_callable=AsyncMock, return_value=""), \
             patch("app.api.export_routes._build_earnings_section", new_callable=AsyncMock, return_value=""):
            body, _ = await _build_trade_markdown(_make_trade_candidate(), _mock_db())
        assert "**Strategy profile:** Trend Rider" in body

    @pytest.mark.asyncio
    async def test_header_contains_current_pnl_na(self):
        with patch("app.api.export_routes._build_technicals_section", new_callable=AsyncMock, return_value=""), \
             patch("app.api.export_routes._build_earnings_section", new_callable=AsyncMock, return_value=""):
            body, _ = await _build_trade_markdown(_make_trade_candidate(), _mock_db())
        assert "**Current P&L:** N/A" in body

    @pytest.mark.asyncio
    async def test_spread_type_is_enum(self):
        with patch("app.api.export_routes._build_technicals_section", new_callable=AsyncMock, return_value=""), \
             patch("app.api.export_routes._build_earnings_section", new_callable=AsyncMock, return_value=""):
            body, _ = await _build_trade_markdown(_make_trade_candidate(), _mock_db())
        assert "**Spread type:** BEAR_PUT_DEBIT" in body
        assert "Bear Put Debit" not in body

    @pytest.mark.asyncio
    async def test_dte_is_integer(self):
        with patch("app.api.export_routes._build_technicals_section", new_callable=AsyncMock, return_value=""), \
             patch("app.api.export_routes._build_earnings_section", new_callable=AsyncMock, return_value=""):
            body, _ = await _build_trade_markdown(_make_trade_candidate(), _mock_db())
        match = re.search(r"\*\*DTE:\*\* (\d+)", body)
        assert match is not None
        assert int(match.group(1)) >= 0

    @pytest.mark.asyncio
    async def test_no_last_monitored_on_trade(self):
        with patch("app.api.export_routes._build_technicals_section", new_callable=AsyncMock, return_value=""), \
             patch("app.api.export_routes._build_earnings_section", new_callable=AsyncMock, return_value=""):
            body, _ = await _build_trade_markdown(_make_trade_candidate(), _mock_db())
        assert "**Last monitored:**" not in body

    @pytest.mark.asyncio
    async def test_footer_v2(self):
        with patch("app.api.export_routes._build_technicals_section", new_callable=AsyncMock, return_value=""), \
             patch("app.api.export_routes._build_earnings_section", new_callable=AsyncMock, return_value=""):
            body, _ = await _build_trade_markdown(_make_trade_candidate(), _mock_db())
        assert _V2_FOOTER in body
        assert "Step 0 parse contract" not in body

    @pytest.mark.asyncio
    async def test_legacy_strategy_key_none(self):
        """Trade with no scan_strategy_key → 'unassigned'."""
        c = _make_trade_candidate()
        c.scan_strategy_key = None
        with patch("app.api.export_routes._build_technicals_section", new_callable=AsyncMock, return_value=""), \
             patch("app.api.export_routes._build_earnings_section", new_callable=AsyncMock, return_value=""):
            body, _ = await _build_trade_markdown(c, _mock_db())
        assert "**Strategy profile:** unassigned" in body


# ─── Position snapshot (OTA-638) ────────────────────────────────────────────

class TestPositionV2Envelope:
    @pytest.mark.asyncio
    async def test_header_contains_schema_version(self):
        with patch("app.api.export_routes._build_technicals_section", new_callable=AsyncMock, return_value=""), \
             patch("app.api.export_routes._build_earnings_section", new_callable=AsyncMock, return_value=""):
            body, _ = await _build_position_markdown(_make_position(), None, _mock_db())
        assert "**Schema version:** 2.0" in body

    @pytest.mark.asyncio
    async def test_header_contains_strategy_profile(self):
        with patch("app.api.export_routes._build_technicals_section", new_callable=AsyncMock, return_value=""), \
             patch("app.api.export_routes._build_earnings_section", new_callable=AsyncMock, return_value=""):
            body, _ = await _build_position_markdown(_make_position(), None, _mock_db())
        assert "**Strategy profile:** Steady Paycheck" in body

    @pytest.mark.asyncio
    async def test_header_contains_last_monitored(self):
        with patch("app.api.export_routes._build_technicals_section", new_callable=AsyncMock, return_value=""), \
             patch("app.api.export_routes._build_earnings_section", new_callable=AsyncMock, return_value=""):
            body, _ = await _build_position_markdown(_make_position(), None, _mock_db())
        assert "**Last monitored:** 05-11-2026 18:22 UTC" in body

    @pytest.mark.asyncio
    async def test_spread_type_is_enum(self):
        with patch("app.api.export_routes._build_technicals_section", new_callable=AsyncMock, return_value=""), \
             patch("app.api.export_routes._build_earnings_section", new_callable=AsyncMock, return_value=""):
            body, _ = await _build_position_markdown(_make_position(), None, _mock_db())
        assert "**Spread type:** BULL_PUT_CREDIT" in body
        assert "Bull Put Credit" not in body

    @pytest.mark.asyncio
    async def test_dte_is_integer(self):
        with patch("app.api.export_routes._build_technicals_section", new_callable=AsyncMock, return_value=""), \
             patch("app.api.export_routes._build_earnings_section", new_callable=AsyncMock, return_value=""):
            body, _ = await _build_position_markdown(_make_position(), None, _mock_db())
        match = re.search(r"\*\*DTE:\*\* (\d+)", body)
        assert match is not None
        assert int(match.group(1)) >= 0

    @pytest.mark.asyncio
    async def test_current_pnl_zero(self):
        with patch("app.api.export_routes._build_technicals_section", new_callable=AsyncMock, return_value=""), \
             patch("app.api.export_routes._build_earnings_section", new_callable=AsyncMock, return_value=""):
            body, _ = await _build_position_markdown(_make_position(current_pnl=0.0), None, _mock_db())
        assert "**Current P&L:** +0.00" in body

    @pytest.mark.asyncio
    async def test_current_pnl_positive(self):
        with patch("app.api.export_routes._build_technicals_section", new_callable=AsyncMock, return_value=""), \
             patch("app.api.export_routes._build_earnings_section", new_callable=AsyncMock, return_value=""):
            body, _ = await _build_position_markdown(_make_position(current_pnl=2.50), None, _mock_db())
        assert "**Current P&L:** +2.50" in body

    @pytest.mark.asyncio
    async def test_current_pnl_negative(self):
        with patch("app.api.export_routes._build_technicals_section", new_callable=AsyncMock, return_value=""), \
             patch("app.api.export_routes._build_earnings_section", new_callable=AsyncMock, return_value=""):
            body, _ = await _build_position_markdown(_make_position(current_pnl=-1.30), None, _mock_db())
        assert "**Current P&L:** -1.30" in body

    @pytest.mark.asyncio
    async def test_footer_v2(self):
        with patch("app.api.export_routes._build_technicals_section", new_callable=AsyncMock, return_value=""), \
             patch("app.api.export_routes._build_earnings_section", new_callable=AsyncMock, return_value=""):
            body, _ = await _build_position_markdown(_make_position(), None, _mock_db())
        assert _V2_FOOTER in body
        assert "Step 0 parse contract" not in body

    @pytest.mark.asyncio
    async def test_full_envelope_shape(self):
        """Assert the header block lines appear in the correct order."""
        with patch("app.api.export_routes._build_technicals_section", new_callable=AsyncMock, return_value=""), \
             patch("app.api.export_routes._build_earnings_section", new_callable=AsyncMock, return_value=""):
            body, _ = await _build_position_markdown(_make_position(), None, _mock_db())
        lines = body.split("\n")
        header_labels = []
        for line in lines:
            if line.startswith("**") and ":**" in line:
                label = line.split(":**")[0].replace("**", "").strip()
                header_labels.append(label)
            if line.startswith("## Trade structure"):
                break

        assert header_labels == [
            "Exported",
            "Schema version",
            "Strategy profile",
            "Status",
            "Followed at",
            "Last monitored",
            "Current price",
            "Current P&L",
        ]


# ─── Technicals + Earnings snapshot tests (OTA-641) ─────────────────────────

def _make_mock_candles():
    """Generate 60 daily OHLC bars for technicals computation."""
    bars = []
    for i in range(60):
        base = 710.0 + i * 0.2
        bars.append({
            "open": base,
            "high": base + 2.0,
            "low": base - 1.5,
            "close": base + 0.5,
        })
    return bars


def _mock_db_with_asset_type(asset_type: str):
    """Create a mock AsyncSession returning a specific asset_type."""
    db = AsyncMock()
    result = MagicMock()
    row = MagicMock()
    row.__getitem__ = lambda self, idx: asset_type
    result.fetchone.return_value = row
    db.execute.return_value = result
    return db


def _mock_db_no_symbol():
    """Create a mock AsyncSession returning no symbol_reference row."""
    db = AsyncMock()
    result = MagicMock()
    result.fetchone.return_value = None
    db.execute.return_value = result
    return db


class TestTechnicalsSection:
    @pytest.mark.asyncio
    async def test_renders_all_fields(self):
        mock_provider = AsyncMock()
        mock_provider.get_candles.return_value = _make_mock_candles()
        with patch("app.api.export_routes._get_provider", return_value=mock_provider):
            section = await _build_technicals_section("QQQ")
        assert "## Technicals (underlying)" in section
        assert "**SMA 8:**" in section
        assert "**SMA 21:**" in section
        assert "**SMA 50:**" in section
        assert "**ATR 14:**" in section
        assert "**SMA alignment:**" in section
        assert "**Distance from 50d:**" in section
        # $ prefix retained on SMA/ATR values in Technicals block
        assert "$" in section

    @pytest.mark.asyncio
    async def test_empty_on_insufficient_data(self):
        mock_provider = AsyncMock()
        mock_provider.get_candles.return_value = [{"open": 1, "high": 2, "low": 0.5, "close": 1.5}] * 10
        with patch("app.api.export_routes._get_provider", return_value=mock_provider):
            section = await _build_technicals_section("QQQ")
        assert section == ""


class TestEarningsSectionETF:
    """Fixture B: ETF (e.g., SPY) — earnings short-circuit."""

    @pytest.mark.asyncio
    async def test_etf_short_circuit(self):
        db = _mock_db_with_asset_type("ETF")
        section = await _build_earnings_section("SPY", "2026-06-01", db)
        assert "## Earnings" in section
        assert "N/A (SPY is an ETF)" in section
        assert "**Days to earnings:** N/A" in section
        assert "**Earnings in expiration window:** No" in section

    @pytest.mark.asyncio
    async def test_etf_no_provider_call(self):
        """ETFs must never call the earnings provider."""
        db = _mock_db_with_asset_type("ETF")
        with patch("app.api.export_routes.CONTEXT_SOURCE_REGISTRY", {"finnhub_earnings": MagicMock()}) as reg:
            section = await _build_earnings_section("SPY", "2026-06-01", db)
            # The FinnhubEarningsSource.fetch should NOT have been called
            reg["finnhub_earnings"].fetch.assert_not_called()
        assert "N/A (SPY is an ETF)" in section


class TestEarningsSectionProviderInactive:
    """Fixture C: non-ETF stock with provider inactive."""

    @pytest.mark.asyncio
    async def test_unavailable_rendering(self):
        db = _mock_db_with_asset_type("Equity")
        with patch("app.api.export_routes.CONTEXT_SOURCE_REGISTRY", {}):
            section = await _build_earnings_section("AAPL", "2026-06-01", db)
        assert "## Earnings" in section
        assert "unavailable (provider in flight under OTA-508)" in section
        assert "**Days to earnings:** unavailable" in section
        assert "**Earnings in expiration window:** unknown" in section
        # Must NOT contain bare N/A — N/A is reserved for "not applicable"
        assert "N/A" not in section


class TestEarningsSectionActiveProvider:
    """Fixture A: non-ETF stock with active earnings provider."""

    @pytest.mark.asyncio
    async def test_active_provider_renders_date(self):
        db = _mock_db_with_asset_type("Equity")
        mock_source = MagicMock()
        mock_source.fetch = AsyncMock(return_value={
            "earningsCalendar": [{"date": "2026-05-20", "hour": "bmo", "epsEstimate": 1.5, "quarter": 2}]
        })
        mock_source.normalize.return_value = {
            "next_earnings_date": "2026-05-20",
            "time_of_day": "bmo",
            "eps_estimate": 1.5,
            "quarter": 2,
            "fetched_at": "2026-05-11T00:00:00Z",
            "meta": {"notes": None},
        }
        with patch("app.api.export_routes.CONTEXT_SOURCE_REGISTRY", {"finnhub_earnings": mock_source}):
            section = await _build_earnings_section("AAPL", "2026-06-01", db)
        assert "## Earnings" in section
        assert "05-20-2026" in section
        assert "**Earnings in expiration window:** Yes" in section

    @pytest.mark.asyncio
    async def test_earnings_outside_window(self):
        db = _mock_db_with_asset_type("Equity")
        mock_source = MagicMock()
        mock_source.fetch = AsyncMock(return_value={})
        mock_source.normalize.return_value = {
            "next_earnings_date": "2026-07-15",
            "time_of_day": "amc",
            "eps_estimate": None,
            "quarter": 3,
            "fetched_at": "2026-05-11T00:00:00Z",
            "meta": {"notes": None},
        }
        with patch("app.api.export_routes.CONTEXT_SOURCE_REGISTRY", {"finnhub_earnings": mock_source}):
            section = await _build_earnings_section("AAPL", "2026-06-01", db)
        assert "**Earnings in expiration window:** No" in section


# ─── Full trade export with Technicals + Earnings (OTA-641) ──────────────────

class TestTradeWithTechnicalsAndEarnings:
    @pytest.mark.asyncio
    async def test_section_ordering(self):
        """Technicals sits after Net metrics, Earnings after Technicals, both before App verdict."""
        mock_provider = AsyncMock()
        mock_provider.get_candles.return_value = _make_mock_candles()
        db = _mock_db_with_asset_type("ETF")

        with patch("app.api.export_routes._get_provider", return_value=mock_provider):
            body, _ = await _build_trade_markdown(_make_trade_candidate(), db)

        # Verify section ordering (Greeks & IV is between Net metrics and Technicals)
        net_idx = body.index("## Net metrics")
        greeks_idx = body.index("## Greeks & IV (position-level)")
        tech_idx = body.index("## Technicals (underlying)")
        earn_idx = body.index("## Earnings")
        verdict_idx = body.index("## App verdict")

        assert net_idx < greeks_idx < tech_idx < earn_idx < verdict_idx


# ─── OTA-639 Snapshot tests: legs columns, net metrics, Greeks ─────────────


# Chain contract data matching the BEAR_PUT_DEBIT trade candidate legs
_DEBIT_CHAIN_CONTRACTS = [
    {
        "symbol": "QQQ260601P00480000",
        "option_type": "PUT",
        "strike": 480.0,
        "expiration": "2026-06-01",
        "bid": 5.20,
        "ask": 5.40,
        "delta": -0.42,
        "gamma": 0.018,
        "theta": -0.12,
        "vega": 0.35,
        "iv": 0.28,
        "volume": 6113,
        "open_interest": 9408,
    },
    {
        "symbol": "QQQ260601P00470000",
        "option_type": "PUT",
        "strike": 470.0,
        "expiration": "2026-06-01",
        "bid": 2.80,
        "ask": 3.00,
        "delta": -0.25,
        "gamma": 0.014,
        "theta": -0.08,
        "vega": 0.28,
        "iv": 0.30,
        "volume": 4250,
        "open_interest": 12300,
    },
]

# Chain contract data matching the BULL_PUT_CREDIT position legs
_CREDIT_CHAIN_CONTRACTS = [
    {
        "symbol": "QQQ260601P00470000",
        "option_type": "PUT",
        "strike": 470.0,
        "expiration": "2026-06-01",
        "bid": 3.00,
        "ask": 3.20,
        "delta": -0.25,
        "gamma": 0.014,
        "theta": -0.08,
        "vega": 0.28,
        "iv": 0.30,
        "volume": 4250,
        "open_interest": 12300,
    },
    {
        "symbol": "QQQ260601P00460000",
        "option_type": "PUT",
        "strike": 460.0,
        "expiration": "2026-06-01",
        "bid": 1.10,
        "ask": 1.30,
        "delta": -0.15,
        "gamma": 0.009,
        "theta": -0.05,
        "vega": 0.18,
        "iv": 0.32,
        "volume": 2890,
        "open_interest": 7450,
    },
]


class TestDebitSpreadSnapshot:
    """Snapshot test: BEAR_PUT_DEBIT trade candidate with chain data (OTA-639)."""

    @pytest.mark.asyncio
    async def test_legs_table_columns(self):
        """Legs table has all 12 v2 columns: Side, Type, Strike, Exp, Qty, Bid, Ask, Mid, Delta, IV, Volume, OI."""
        with patch("app.api.export_routes._build_technicals_section", new_callable=AsyncMock, return_value=""), \
             patch("app.api.export_routes._build_earnings_section", new_callable=AsyncMock, return_value=""):
            body, _ = await _build_trade_markdown(
                _make_trade_candidate(), _mock_db(), chain_contracts=_DEBIT_CHAIN_CONTRACTS,
            )
        # Header row
        assert "| Side | Type | Strike | Expiration | Qty | Bid | Ask | Mid | Delta | IV | Volume | OI |" in body
        # Mid computed as (bid + ask) / 2: (5.20 + 5.40) / 2 = 5.30
        assert "| 5.30 |" in body
        # IV formatted as ##.#%: 0.28 → 28.0%
        assert "28.0%" in body
        # Volume with thousands separators
        assert "6,113" in body
        assert "9,408" in body

    @pytest.mark.asyncio
    async def test_net_metrics_debit_format(self):
        """Net metrics block uses debit-specific labels and $ prefix."""
        with patch("app.api.export_routes._build_technicals_section", new_callable=AsyncMock, return_value=""), \
             patch("app.api.export_routes._build_earnings_section", new_callable=AsyncMock, return_value=""):
            body, _ = await _build_trade_markdown(
                _make_trade_candidate(), _mock_db(), chain_contracts=_DEBIT_CHAIN_CONTRACTS,
            )
        assert "**Entry debit:** $2.40 per contract ($240.00 for 1 contract)" in body
        assert "**Spread width:** $10.00" in body
        assert "**Debit % of width:** 24.0%" in body
        assert "**Max profit:** $7.60 per contract ($760.00)" in body
        assert "**Max loss:** $2.40 per contract ($240.00)" in body
        assert "**Breakeven:** $477.60" in body
        assert "**R:R:** 3.17 : 1" in body
        assert "**Underlying spot:** $485.50" in body

    @pytest.mark.asyncio
    async def test_cushion_to_breakeven_negative(self):
        """Bear put debit with spot above breakeven → negative cushion with narrative."""
        with patch("app.api.export_routes._build_technicals_section", new_callable=AsyncMock, return_value=""), \
             patch("app.api.export_routes._build_earnings_section", new_callable=AsyncMock, return_value=""):
            body, _ = await _build_trade_markdown(
                _make_trade_candidate(), _mock_db(), chain_contracts=_DEBIT_CHAIN_CONTRACTS,
            )
        # cushion = breakeven - spot = 477.60 - 485.50 = -7.90
        # cushion_pct = -7.90 / 485.50 = -1.63%
        assert "\u2212$7.90" in body  # Unicode minus
        assert "\u22121.63%" in body
        assert "price is ABOVE breakeven at entry (unfavorable for bear put)" in body

    @pytest.mark.asyncio
    async def test_greeks_iv_section(self):
        """Greeks & IV section present with correct net Greeks for BEAR_PUT_DEBIT."""
        with patch("app.api.export_routes._build_technicals_section", new_callable=AsyncMock, return_value=""), \
             patch("app.api.export_routes._build_earnings_section", new_callable=AsyncMock, return_value=""):
            body, _ = await _build_trade_markdown(
                _make_trade_candidate(), _mock_db(), chain_contracts=_DEBIT_CHAIN_CONTRACTS,
            )
        assert "## Greeks & IV (position-level)" in body
        # Net delta: BUY*1*(-0.42) + SELL*(-1)*(-0.25) = -0.42 + (-0.25) = wait...
        # BUY leg: side_sign=+1, qty=1, delta=-0.42 → +1 * 1 * (-0.42) = -0.42
        # SELL leg: side_sign=-1, qty=1, delta=-0.25 → -1 * 1 * (-0.25) = +0.25
        # net_delta = -0.42 + 0.25 = -0.17
        assert "**Net delta:** \u22120.17" in body
        # Net theta: +1*1*(-0.12) + (-1)*1*(-0.08) = -0.12 + 0.08 = -0.04
        assert "**Net theta:** \u22120.04" in body
        # Net vega: +1*1*(0.35) + (-1)*1*(0.28) = 0.35 - 0.28 = +0.07
        assert "**Net vega:** +0.07" in body
        # Net gamma: +1*1*(0.018) + (-1)*1*(0.014) = 0.018 - 0.014 = +0.004
        assert "**Net gamma:** +0.004" in body
        # IV Rank from net_metrics: 45.0 → 45.0%
        assert "**IV Rank (underlying):** 45.0%" in body
        # Spread mid IV: (1*0.28 + 1*0.30) / 2 = 0.29 → 29.0%
        assert "**Spread mid IV:** 29.0%" in body

    @pytest.mark.asyncio
    async def test_net_delta_sign_matches_direction(self):
        """Bear put debit must have negative net delta (profits from downward move)."""
        with patch("app.api.export_routes._build_technicals_section", new_callable=AsyncMock, return_value=""), \
             patch("app.api.export_routes._build_earnings_section", new_callable=AsyncMock, return_value=""):
            body, _ = await _build_trade_markdown(
                _make_trade_candidate(), _mock_db(), chain_contracts=_DEBIT_CHAIN_CONTRACTS,
            )
        # Net delta must be negative for bear direction
        assert "**Net delta:** \u2212" in body

    @pytest.mark.asyncio
    async def test_no_dollar_outside_net_metrics(self):
        """$ prefix appears only in Net metrics block, not in legs, Greeks, or other sections."""
        with patch("app.api.export_routes._build_technicals_section", new_callable=AsyncMock, return_value=""), \
             patch("app.api.export_routes._build_earnings_section", new_callable=AsyncMock, return_value=""):
            body, _ = await _build_trade_markdown(
                _make_trade_candidate(), _mock_db(), chain_contracts=_DEBIT_CHAIN_CONTRACTS,
            )
        sections = body.split("## ")
        for section in sections:
            if section.startswith("Net metrics"):
                continue  # $ allowed here
            if section.startswith("Technicals"):
                continue  # $ allowed per OTA-641
            assert "$" not in section, f"Found $ outside Net metrics/Technicals: {section[:80]}"


class TestCreditSpreadSnapshot:
    """Snapshot test: BULL_PUT_CREDIT position with chain data (OTA-639)."""

    @pytest.mark.asyncio
    async def test_legs_table_columns(self):
        """Legs table has all 12 v2 columns with volume/OI from chain."""
        with patch("app.api.export_routes._build_technicals_section", new_callable=AsyncMock, return_value=""), \
             patch("app.api.export_routes._build_earnings_section", new_callable=AsyncMock, return_value=""):
            body, _ = await _build_position_markdown(
                _make_position(), None, _mock_db(), chain_contracts=_CREDIT_CHAIN_CONTRACTS,
            )
        assert "| Side | Type | Strike | Expiration | Qty | Bid | Ask | Mid | Delta | IV | Volume | OI |" in body
        # Mid for SELL 470 put: (3.00 + 3.20) / 2 = 3.10
        assert "| 3.10 |" in body
        # Volume with separators
        assert "4,250" in body
        assert "12,300" in body
        assert "2,890" in body
        assert "7,450" in body

    @pytest.mark.asyncio
    async def test_net_metrics_credit_format(self):
        """Net metrics block uses credit-specific labels and $ prefix."""
        with patch("app.api.export_routes._build_technicals_section", new_callable=AsyncMock, return_value=""), \
             patch("app.api.export_routes._build_earnings_section", new_callable=AsyncMock, return_value=""):
            body, _ = await _build_position_markdown(
                _make_position(), None, _mock_db(), chain_contracts=_CREDIT_CHAIN_CONTRACTS,
            )
        assert "**Entry credit:** $1.80 per contract ($180.00 for 1 contract)" in body
        assert "**Spread width:** $10.00" in body
        assert "**Credit % of width:** 18.0%" in body
        assert "**Max profit:** $1.80 per contract ($180.00)" in body
        assert "**Max loss:** $8.20 per contract ($820.00)" in body
        assert "**Breakeven:** $468.20" in body
        assert "**R:R:** 0.22 : 1" in body
        assert "**Underlying spot:** $485.50" in body

    @pytest.mark.asyncio
    async def test_cushion_to_short_strike_positive(self):
        """Bull put credit with spot above short strike → positive cushion."""
        with patch("app.api.export_routes._build_technicals_section", new_callable=AsyncMock, return_value=""), \
             patch("app.api.export_routes._build_earnings_section", new_callable=AsyncMock, return_value=""):
            body, _ = await _build_position_markdown(
                _make_position(), None, _mock_db(), chain_contracts=_CREDIT_CHAIN_CONTRACTS,
            )
        # cushion = spot - short_strike = 485.50 - 470 = +15.50
        # cushion_pct = 15.50 / 485.50 = +3.19%
        assert "**Cushion to short strike:** +$15.50 (+3.19%)" in body

    @pytest.mark.asyncio
    async def test_greeks_iv_section(self):
        """Greeks & IV section with correct net Greeks for BULL_PUT_CREDIT."""
        with patch("app.api.export_routes._build_technicals_section", new_callable=AsyncMock, return_value=""), \
             patch("app.api.export_routes._build_earnings_section", new_callable=AsyncMock, return_value=""):
            body, _ = await _build_position_markdown(
                _make_position(), None, _mock_db(), chain_contracts=_CREDIT_CHAIN_CONTRACTS,
            )
        assert "## Greeks & IV (position-level)" in body
        # Net delta: SELL*(-1)*(-0.25) + BUY*(+1)*(-0.15) = 0.25 + (-0.15) = +0.10
        assert "**Net delta:** +0.10" in body
        # Net theta: (-1)*(-0.08) + (+1)*(-0.05) = 0.08 + (-0.05) = +0.03
        assert "**Net theta:** +0.03" in body
        # Net vega: (-1)*(0.28) + (+1)*(0.18) = -0.28 + 0.18 = -0.10
        assert "**Net vega:** \u22120.10" in body
        # Net gamma: (-1)*(0.014) + (+1)*(0.009) = -0.014 + 0.009 = -0.005
        assert "**Net gamma:** \u22120.005" in body
        # IV Rank from position.entry_iv_rank: 45.0 → 45.0%
        assert "**IV Rank (underlying):** 45.0%" in body
        # Spread mid IV: (1*0.30 + 1*0.32) / 2 = 0.31 → 31.0%
        assert "**Spread mid IV:** 31.0%" in body

    @pytest.mark.asyncio
    async def test_net_delta_sign_matches_direction(self):
        """Bull put credit must have positive net delta (mildly bullish)."""
        with patch("app.api.export_routes._build_technicals_section", new_callable=AsyncMock, return_value=""), \
             patch("app.api.export_routes._build_earnings_section", new_callable=AsyncMock, return_value=""):
            body, _ = await _build_position_markdown(
                _make_position(), None, _mock_db(), chain_contracts=_CREDIT_CHAIN_CONTRACTS,
            )
        assert "**Net delta:** +0.10" in body

    @pytest.mark.asyncio
    async def test_no_dollar_outside_net_metrics(self):
        """$ prefix appears only in Net metrics block."""
        with patch("app.api.export_routes._build_technicals_section", new_callable=AsyncMock, return_value=""), \
             patch("app.api.export_routes._build_earnings_section", new_callable=AsyncMock, return_value=""):
            body, _ = await _build_position_markdown(
                _make_position(), None, _mock_db(), chain_contracts=_CREDIT_CHAIN_CONTRACTS,
            )
        sections = body.split("## ")
        for section in sections:
            if section.startswith("Net metrics"):
                continue
            if section.startswith("Technicals"):
                continue
            assert "$" not in section, f"Found $ outside allowed blocks: {section[:80]}"


class TestChainEnrichmentFailFast:
    """Test that missing chain contract raises 422 with diagnostic."""

    def test_missing_leg_raises_422(self):
        """If chain_contracts is provided but leg doesn't match → 422."""
        from fastapi import HTTPException
        legs = [{"side": "BUY", "option_type": "PUT", "strike": 999.0, "expiration": "2026-06-01", "qty": 1}]
        chain = [{"option_type": "PUT", "strike": 480.0, "expiration": "2026-06-01", "volume": 100, "open_interest": 200}]
        with pytest.raises(HTTPException) as exc_info:
            _enrich_legs_from_chain(legs, chain)
        assert exc_info.value.status_code == 422
        assert "strike=999.0" in exc_info.value.detail
