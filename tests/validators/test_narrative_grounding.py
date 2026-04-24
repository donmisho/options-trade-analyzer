"""
Tests for OTA-504 / OTA-509 / OTA-510 — Narrative Grounding Validator

Phase 2 covers OTA-509 (EV grounding rule).
Phase 3 will add OTA-510 (SMA grounding rules) to this same file.
"""

import math
import pytest

from app.validators.narrative_grounding import (
    EvaluationFields,
    ValidationError,
    validate_ev_grounding,
    validate_sma_grounding,
    validate_narrative,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def amzn_fields(**overrides) -> EvaluationFields:
    """AMZN April 22 regression fixture: price above all SMAs, negative EV."""
    defaults = dict(
        price=255.36,
        sma_8=252.52,
        sma_21=252.39,
        sma_50=251.86,
        expected_value=-5.86,
    )
    defaults.update(overrides)
    return EvaluationFields(**defaults)


def golden_fields(**overrides) -> EvaluationFields:
    """Golden-path fixture: price above all SMAs, positive EV."""
    defaults = dict(
        price=260.00,
        sma_8=252.52,
        sma_21=252.39,
        sma_50=251.86,
        expected_value=89.00,
    )
    defaults.update(overrides)
    return EvaluationFields(**defaults)


# ═══════════════════════════════════════════════════════════════════════════════
# OTA-509 — EV grounding rule
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidateEvGrounding:

    # ── Positive case (should catch) ─────────────────────────────────────────

    def test_amzn_positive_ev_assertion_with_negative_ev(self):
        """AMZN regression: 'positive EV of $89' narrative + computed EV -5.86 → 1 error."""
        narrative = (
            "The positive EV of $89 and strong IV rank support the trade. "
            "SMA alignment is mixed but the setup has merit."
        )
        errors = validate_ev_grounding(narrative, amzn_fields())
        assert len(errors) == 1
        assert errors[0].code == "EV_CONTRADICTION"
        assert errors[0].field_context == "expected_value"

    def test_favorable_ev_phrasing_flagged(self):
        """'favorable EV' is also caught."""
        narrative = "The favorable EV gives this trade a positive expected return."
        errors = validate_ev_grounding(narrative, amzn_fields())
        assert len(errors) == 1
        assert errors[0].code == "EV_CONTRADICTION"

    def test_ev_of_dollar_amount_flagged(self):
        """'EV of $89' pattern is caught."""
        narrative = "With an EV of $89 the trade looks attractive."
        errors = validate_ev_grounding(narrative, amzn_fields())
        assert len(errors) == 1

    def test_ev_of_bare_number_flagged(self):
        """'EV of 89' (no dollar sign) is caught."""
        narrative = "Expected value EV of 89 supports entry."
        errors = validate_ev_grounding(narrative, amzn_fields())
        assert len(errors) == 1

    # ── Negative cases (should NOT fire) ─────────────────────────────────────

    def test_narrative_correctly_states_negative_ev(self):
        """Narrative correctly acknowledges negative EV → 0 errors."""
        narrative = "The EV of -5.86 makes this a pass; negative expected value disqualifies the trade."
        errors = validate_ev_grounding(narrative, amzn_fields())
        assert errors == []

    def test_narrative_says_negative_ev_signals_caution(self):
        """'negative EV signals caution' → 0 errors (false-positive guard)."""
        narrative = "The negative EV signals caution — avoid entering this trade."
        errors = validate_ev_grounding(narrative, amzn_fields())
        assert errors == []

    def test_no_ev_mention_in_narrative(self):
        """Narrative mentions nothing about EV → 0 errors."""
        narrative = "SMA alignment is mixed and IV rank is elevated. Watch the 252 level."
        errors = validate_ev_grounding(narrative, amzn_fields())
        assert errors == []

    # ── Edge case ────────────────────────────────────────────────────────────

    def test_ev_exactly_zero_does_not_fire(self):
        """Rule only fires when EV < 0; EV == 0 is boundary — no error."""
        narrative = "The positive EV of $89 supports this trade."
        errors = validate_ev_grounding(narrative, amzn_fields(expected_value=0.0))
        assert errors == []

    def test_positive_ev_with_positive_ev_field_no_error(self):
        """'positive EV' narrative + computed EV > 0 → 0 errors."""
        narrative = "The positive EV of $89 and favorable conditions support entry."
        errors = validate_ev_grounding(narrative, golden_fields())
        assert errors == []

    def test_ev_nan_skips_rule(self):
        """When expected_value is NaN (not available), rule is skipped."""
        narrative = "The positive EV of $89 supports the trade."
        errors = validate_ev_grounding(narrative, amzn_fields(expected_value=math.nan))
        assert errors == []


# ═══════════════════════════════════════════════════════════════════════════════
# OTA-510 — SMA grounding rule
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidateSmaGrounding:

    # ── Sub-rule A: positional contradiction ─────────────────────────────────

    def test_amzn_below_all_smas_when_above(self):
        """AMZN regression A: 'sits just below all three SMAs' + price > all three → 1 SMA_POSITION error."""
        narrative = "AMZN sits just below all three SMAs with mixed trend alignment."
        errors = validate_sma_grounding(narrative, amzn_fields())
        codes = [e.code for e in errors]
        assert "SMA_POSITION" in codes

    def test_below_50_when_above(self):
        """'below 50' with price > sma_50 → 1 SMA_POSITION error."""
        narrative = "The stock trades below 50 SMA suggesting bearish pressure."
        errors = validate_sma_grounding(narrative, amzn_fields())
        assert any(e.code == "SMA_POSITION" for e in errors)

    def test_false_positive_above_all_smas(self):
        """'above all three SMAs' + price > all three → 0 errors."""
        narrative = "AMZN trades above all three SMAs with bullish alignment."
        errors = validate_sma_grounding(narrative, amzn_fields())
        sma_position_errors = [e for e in errors if e.code == "SMA_POSITION"]
        assert sma_position_errors == []

    def test_false_positive_above_50(self):
        """'above 50' narrative + price > sma_50 → 0 SMA_POSITION errors."""
        narrative = "Price is above the 50-day SMA providing support."
        errors = validate_sma_grounding(narrative, amzn_fields())
        assert not any(e.code == "SMA_POSITION" for e in errors)

    # ── Sub-rule B: numerical hallucination ──────────────────────────────────

    def test_amzn_hallucinated_sma21_value(self):
        """AMZN regression B: narrative cites 'SMA-21 at 257.64' when input set has ~252.x → 1 SMA_HALLUCINATION error."""
        narrative = "With SMA-21 at 257.64 acting as resistance, the trade is under pressure."
        errors = validate_sma_grounding(narrative, amzn_fields())
        assert any(e.code == "SMA_HALLUCINATION" for e in errors)

    def test_correct_sma_value_no_hallucination(self):
        """Narrative correctly cites 'SMA-8 at 252.52' matching exact input → 0 SMA_HALLUCINATION errors."""
        narrative = "The stock is consolidating around SMA-8 at 252.52."
        errors = validate_sma_grounding(narrative, amzn_fields())
        assert not any(e.code == "SMA_HALLUCINATION" for e in errors)

    def test_sma_value_within_tolerance_no_hallucination(self):
        """Value within 10-cent tolerance (252.60 vs nearest 252.52 = 0.08 diff) → 0 errors."""
        narrative = "Price near SMA-8 at 252.60 as support."
        errors = validate_sma_grounding(narrative, amzn_fields())
        assert not any(e.code == "SMA_HALLUCINATION" for e in errors)

    def test_sma_value_at_boundary_no_hallucination(self):
        """abs(v - nearest) == 0.10 exactly → 0 errors (boundary is within tolerance)."""
        # sma_8=252.52; 252.52 + 0.10 = 252.62 → exactly at boundary → no error
        narrative = "SMA-8 at 252.62 provided support during the dip."
        errors = validate_sma_grounding(narrative, amzn_fields())
        assert not any(e.code == "SMA_HALLUCINATION" for e in errors)

    def test_sma_hyphen_format(self):
        """'SMA-21 at 257.64' format is matched."""
        narrative = "SMA-21 at 257.64 is overhead resistance."
        errors = validate_sma_grounding(narrative, amzn_fields())
        assert any(e.code == "SMA_HALLUCINATION" for e in errors)

    def test_sma_no_hyphen_format(self):
        """'SMA21 at 257.64' (no hyphen) is matched."""
        narrative = "SMA21 at 257.64 overhead."
        errors = validate_sma_grounding(narrative, amzn_fields())
        assert any(e.code == "SMA_HALLUCINATION" for e in errors)

    def test_sma_space_format(self):
        """'sma 50 at $252.39' (space, dollar sign) is matched and passes (value in set)."""
        narrative = "The stock is sitting right at sma 50 at $251.86."
        errors = validate_sma_grounding(narrative, amzn_fields())
        assert not any(e.code == "SMA_HALLUCINATION" for e in errors)


# ═══════════════════════════════════════════════════════════════════════════════
# Composed validate_narrative entry point
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidateNarrative:

    def test_amzn_both_contradictions(self):
        """AMZN full regression: narrative contains both EV and SMA contradictions → 2+ errors."""
        narrative = (
            "The positive EV of $89 and strong IV rank support the trade. "
            "AMZN sits just below all three SMAs with mixed trend alignment, "
            "with SMA-21 at 257.64 acting as resistance."
        )
        errors = validate_narrative(narrative, amzn_fields())
        codes = [e.code for e in errors]
        assert "EV_CONTRADICTION" in codes
        assert "SMA_POSITION" in codes
        # SMA_HALLUCINATION may also fire — that's correct
        assert len(errors) >= 2

    def test_golden_path_no_errors(self):
        """Golden path: positive EV narrative + price above SMAs + correct SMA values → 0 errors."""
        narrative = (
            "AMZN trades above all three SMAs with bullish alignment. "
            "The EV of 89.00 supports entry; IV rank is favorable for this structure. "
            "Watch SMA-8 at 252.52 as near-term support."
        )
        errors = validate_narrative(narrative, golden_fields())
        assert errors == []

    def test_clean_narrative_negative_ev_acknowledged(self):
        """Narrative that correctly states negative EV and correct SMA positioning → 0 errors."""
        narrative = (
            "The negative EV of -5.86 disqualifies this trade. "
            "Price trades above SMA-50 but the structure does not support entry."
        )
        errors = validate_narrative(narrative, amzn_fields())
        assert errors == []
