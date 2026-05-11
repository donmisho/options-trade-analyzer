"""
Snapshot tests for Export MD v2 envelope (OTA-638).

Tests the v2 header block (Schema version, Strategy profile, DTE, spread_type ENUM,
Current P&L, Last monitored) and footer against committed expected output.

Uses lightweight stub objects instead of real DB models to keep the test
independent of the database layer.
"""

import json
import re
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.api.export_routes import (
    _build_trade_markdown,
    _build_position_markdown,
    format_spread_type_enum,
    _fmt_signed_pnl,
    _compute_dte,
    _V2_FOOTER,
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


# ─── Trade snapshot ──────────────────────────────────────────────────────────

class TestTradeV2Envelope:
    def test_header_contains_schema_version(self):
        body, _ = _build_trade_markdown(_make_trade_candidate())
        assert "**Schema version:** 2.0" in body

    def test_header_contains_strategy_profile(self):
        body, _ = _build_trade_markdown(_make_trade_candidate())
        assert "**Strategy profile:** Trend Rider" in body

    def test_header_contains_current_pnl_na(self):
        body, _ = _build_trade_markdown(_make_trade_candidate())
        assert "**Current P&L:** N/A" in body

    def test_spread_type_is_enum(self):
        body, _ = _build_trade_markdown(_make_trade_candidate())
        assert "**Spread type:** BEAR_PUT_DEBIT" in body
        # No friendly name
        assert "Bear Put Debit" not in body

    def test_dte_is_integer(self):
        body, _ = _build_trade_markdown(_make_trade_candidate())
        match = re.search(r"\*\*DTE:\*\* (\d+)", body)
        assert match is not None
        assert int(match.group(1)) >= 0

    def test_no_last_monitored_on_trade(self):
        body, _ = _build_trade_markdown(_make_trade_candidate())
        assert "**Last monitored:**" not in body

    def test_footer_v2(self):
        body, _ = _build_trade_markdown(_make_trade_candidate())
        assert _V2_FOOTER in body
        # Old v1 footer should NOT be present
        assert "Step 0 parse contract" not in body

    def test_no_dollar_sign(self):
        body, _ = _build_trade_markdown(_make_trade_candidate())
        assert "$" not in body

    def test_legacy_strategy_key_none(self):
        """Trade with no scan_strategy_key → 'unassigned'."""
        c = _make_trade_candidate()
        c.scan_strategy_key = None
        body, _ = _build_trade_markdown(c)
        assert "**Strategy profile:** unassigned" in body


# ─── Position snapshot ───────────────────────────────────────────────────────

class TestPositionV2Envelope:
    def test_header_contains_schema_version(self):
        body, _ = _build_position_markdown(_make_position(), None)
        assert "**Schema version:** 2.0" in body

    def test_header_contains_strategy_profile(self):
        body, _ = _build_position_markdown(_make_position(), None)
        assert "**Strategy profile:** Steady Paycheck" in body

    def test_header_contains_last_monitored(self):
        body, _ = _build_position_markdown(_make_position(), None)
        assert "**Last monitored:** 05-11-2026 18:22 UTC" in body

    def test_spread_type_is_enum(self):
        body, _ = _build_position_markdown(_make_position(), None)
        assert "**Spread type:** BULL_PUT_CREDIT" in body
        assert "Bull Put Credit" not in body

    def test_dte_is_integer(self):
        body, _ = _build_position_markdown(_make_position(), None)
        match = re.search(r"\*\*DTE:\*\* (\d+)", body)
        assert match is not None
        assert int(match.group(1)) >= 0

    def test_current_pnl_zero(self):
        body, _ = _build_position_markdown(_make_position(current_pnl=0.0), None)
        assert "**Current P&L:** +0.00" in body

    def test_current_pnl_positive(self):
        body, _ = _build_position_markdown(_make_position(current_pnl=2.50), None)
        assert "**Current P&L:** +2.50" in body

    def test_current_pnl_negative(self):
        body, _ = _build_position_markdown(_make_position(current_pnl=-1.30), None)
        assert "**Current P&L:** -1.30" in body

    def test_footer_v2(self):
        body, _ = _build_position_markdown(_make_position(), None)
        assert _V2_FOOTER in body
        assert "Step 0 parse contract" not in body

    def test_no_dollar_sign(self):
        body, _ = _build_position_markdown(_make_position(), None)
        assert "$" not in body

    def test_full_envelope_shape(self):
        """Assert the header block lines appear in the correct order."""
        body, _ = _build_position_markdown(_make_position(), None)
        lines = body.split("\n")
        # Find header lines by label
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
