"""QA harness configuration."""

# Environment
TARGET_ENV = "dev"
DEV_API_BASE = "https://oa-dev.tmtctech.ai"

# Candidate bounds
ALLOWED_WIDTHS = [5, 10]
STRIKE_WINDOW_PCT = 0.25  # |strike - underlying| / underlying <= 0.25

# Foundry sampling for Stage 4
EVALUATE_TOP_N_PER_STRATEGY = 3

# Run config
RUNS_PER_SYMBOL = 1  # Phase 2 = single-run only
MIN_DELAY_BETWEEN_RUNS_SEC = 5

# Strategy keys (canonical order)
STRATEGY_KEYS = ["steady-paycheck", "weekly-grind", "trend-rider", "lottery-ticket"]

# Engine-level spread_type to structure mapping
ENGINE_TO_STRUCTURE = {
    "bull_call": "bull_call_debit",
    "bear_put": "bear_put_debit",
    "bull_put": "bull_put_credit",
    "bear_call": "bear_call_credit",
    "call": "long_call",
    "put": "long_put",
}
