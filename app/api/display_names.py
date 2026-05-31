"""
Presentation-layer display-name mappings.

This module holds presentation concerns — how internal identifiers are labelled
for human-facing output — kept deliberately out of the scoring/engine/adapter/
rule layers. It is the presentation home for COMPONENT_DISPLAY_NAMES, relocated
here from the scoring layer (formerly strategy_scorer.py, then
strategy_definitions.py) under OTA-813. No engine, adapter, or scoring code may
import from this module.
"""

# Display-name mapping: internal metric key -> v2 export label.
# Order matches the QQQ v2 sample row order (OTA-643).
COMPONENT_DISPLAY_NAMES = {
    "expected_value":        "Expected value (EV)",
    "probability_of_profit": "Expected value (EV)",   # folds into EV for display
    "reward_risk":           "Structure fit (vs profile)",
    "credit_width_pct":      "Structure fit (vs profile)",
    "theta_margin_ratio":    "Structure fit (vs profile)",
    "theta_gamma_ratio":     "Structure fit (vs profile)",
    "delta_quality":         "Structure fit (vs profile)",
    "cushion_strike":        "Cushion / strike placement",
    "sma_alignment_score":   "Technical alignment (SMAs)",
    "iv_rank":               "IV environment",
    "iv_percentile_cost":    "IV environment",
    "runway_score":          "DTE fit",
    "payout_ratio":          "DTE fit",
    "delta_otm_score":       "DTE fit",
    "liquidity":             "Liquidity (bid-ask, volume)",
    "bid_ask_tightness":     "Liquidity (bid-ask, volume)",
    "open_interest":         "Liquidity (bid-ask, volume)",
}
