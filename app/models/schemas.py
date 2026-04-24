"""
Pydantic schemas for request/response validation.

WHY Pydantic: FastAPI uses Pydantic models to validate incoming data and
serialize responses. If someone sends a bad request (wrong type, missing field),
FastAPI returns a clear error automatically. These schemas are the "contract"
between your API and its consumers (web app, Excel, MCP).
"""

from pydantic import BaseModel, Field, EmailStr, field_validator
from typing import Optional, List, Literal
from datetime import datetime


# ============================================================
# Auth Schemas
# ============================================================

class UserCreate(BaseModel):
    """Registration request."""
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8)
    invite_code: str  # Required — no open registration


class UserLogin(BaseModel):
    """Login step 1: credentials."""
    username: str
    password: str


class TOTPVerify(BaseModel):
    """Login step 2 / Trade MFA: TOTP code from authenticator app."""
    totp_code: str = Field(..., min_length=6, max_length=6)


class TokenResponse(BaseModel):
    """JWT token returned after successful auth."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    mfa_required: bool = False  # True if TOTP still needed


class UserResponse(BaseModel):
    """User info returned by profile endpoints."""
    id: str
    username: str
    email: str
    role: str
    mfa_enabled: bool
    trading_enabled: bool
    market_data_provider: str
    account_provider: Optional[str]
    created_at: datetime


class MFASetupResponse(BaseModel):
    """Returned when user sets up MFA for the first time."""
    qr_code_uri: str  # otpauth:// URI for QR code generation
    # Note: we DON'T return the raw secret — only the QR URI


# ============================================================
# Config Schemas
# ============================================================

class UserConfigUpdate(BaseModel):
    """Update scoring weights, filters, risk settings."""
    default_symbol: Optional[str] = None
    min_dte: Optional[int] = Field(None, ge=0, le=365)
    max_dte: Optional[int] = Field(None, ge=1, le=730)
    strike_range_pct: Optional[float] = Field(None, ge=1, le=50)
    min_open_interest: Optional[int] = Field(None, ge=0)
    min_volume: Optional[int] = Field(None, ge=0)
    min_spread_width: Optional[float] = Field(None, ge=0.5)
    max_spread_width: Optional[float] = Field(None, ge=1)
    weight_expected_value: Optional[float] = Field(None, ge=0, le=1)
    weight_reward_risk: Optional[float] = Field(None, ge=0, le=1)
    weight_probability: Optional[float] = Field(None, ge=0, le=1)
    weight_liquidity: Optional[float] = Field(None, ge=0, le=1)
    max_risk_per_trade: Optional[float] = Field(None, ge=0)
    profit_target_pct: Optional[float] = Field(None, ge=0, le=300)
    stop_loss_pct: Optional[float] = Field(None, ge=0, le=100)
    extra_settings: Optional[dict] = None


class UserConfigResponse(BaseModel):
    """Full config returned to the user."""
    default_symbol: str
    min_dte: int
    max_dte: int
    strike_range_pct: float
    min_open_interest: int
    min_volume: int
    min_spread_width: float
    max_spread_width: float
    weight_expected_value: float
    weight_reward_risk: float
    weight_probability: float
    weight_liquidity: float
    max_risk_per_trade: float
    profit_target_pct: float
    stop_loss_pct: float
    extra_settings: dict
    updated_at: datetime


# ============================================================
# Market Data Schemas
# ============================================================

class Quote(BaseModel):
    """Current price data for an underlying."""
    symbol: str
    price: float
    change: float
    change_pct: float
    volume: int
    day_high: float
    day_low: float
    previous_close: float
    timestamp: datetime
    week_52_high: Optional[float] = None
    week_52_low: Optional[float] = None
    avg_volume: Optional[int] = None
    volume_ratio: Optional[float] = None
    next_earnings_date: Optional[str] = None
    next_dividend_date: Optional[str] = None


class OptionContract(BaseModel):
    """A single options contract from the chain."""
    symbol: str  # OCC symbol (e.g., QQQ260320C00625000)
    underlying: str
    expiration: str  # YYYY-MM-DD
    dte: int
    strike: float
    option_type: str  # "call" or "put"
    bid: float
    ask: float
    mid: float
    last: Optional[float] = None
    volume: int
    open_interest: int
    implied_volatility: Optional[float] = None
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    rho: Optional[float] = None


class OptionChainResponse(BaseModel):
    """Full options chain response."""
    underlying: str
    underlying_price: float
    contracts: list[OptionContract]
    expirations_available: list[str]
    fetched_at: datetime
    provider: str


# ============================================================
# Trade MFA Schemas
# ============================================================

class TradePreviewRequest(BaseModel):
    """Request to preview a trade before execution."""
    symbol: str
    strategy: str  # bull_call_spread, bear_put_spread, long_call, etc.
    legs: list[dict]  # [{strike, option_type, side, quantity}, ...]
    quantity: int = Field(1, ge=1)


class TradePreviewResponse(BaseModel):
    """Preview result with MFA challenge for execution."""
    # Trade details
    symbol: str
    strategy: str
    legs: list[dict]
    quantity: int
    underlying_price: float

    # Calculated values
    net_debit: float
    max_profit: float
    max_loss: float
    breakeven: float
    reward_risk: float
    prob_of_profit: Optional[float] = None

    # Risk check results
    within_risk_budget: bool
    risk_budget: float
    risk_warnings: list[str]

    # MFA challenge — needed to execute
    challenge_number: str  # 4-digit number shown on screen
    challenge_token: str  # Signed JWT binding challenge to this trade
    challenge_expires_in: int  # Seconds (120)


class TradeExecuteRequest(BaseModel):
    """Execute a previewed trade with MFA verification."""
    challenge_token: str  # From preview response
    challenge_number: str = Field(..., min_length=4, max_length=4)
    totp_code: str = Field(..., min_length=6, max_length=6)


class TradeExecuteResponse(BaseModel):
    """Result of trade execution."""
    trade_id: int
    status: str  # executed, rejected
    broker_order_id: Optional[str] = None
    message: str


# ============================================================
# Provider Schemas
# ============================================================

class ProviderConnectRequest(BaseModel):
    """Connect a brokerage provider."""
    provider: str  # "tradier" or "schwab"
    role: str  # "market_data", "account", "trading"
    # Provider-specific config
    config: dict  # e.g., {"token": "...", "environment": "sandbox"}


class ProviderStatusResponse(BaseModel):
    """Current provider assignments and health."""
    market_data: Optional[dict] = None  # {provider, status, environment}
    account: Optional[dict] = None
    trading: Optional[dict] = None


# ============================================================
# Strategy Scorecard Schemas (Phase 2.9)
# ============================================================

class ScorecardRequest(BaseModel):
    """Request a strategy scorecard for a symbol."""
    symbol: str
    user_config: Optional[dict] = None  # optional overrides (dte_min, delta_max, sma_alignment_score, etc.)


class StrategyScoreItem(BaseModel):
    """Score for a single strategy."""
    strategy_key: str
    label: str
    score: int                          # 0-100
    best_trade: Optional[dict] = None   # top-scoring candidate trade
    signal_summary: str
    metric_scores: dict


class ScorecardResponse(BaseModel):
    """Full scorecard response for a symbol across all strategies."""
    symbol: str
    underlying_price: float
    quote: Optional[dict] = None      # { price, change, change_pct, volume, volume_ratio }
    sma_signal: Optional[dict] = None # { alignment, summary, sma_8, sma_21, sma_50 }
    strategies: list[StrategyScoreItem]


class ProbabilityMatrixRequest(BaseModel):
    """Request a Black-Scholes probability matrix for a trade."""
    symbol: str
    current_price: float = Field(..., gt=0)
    iv: float = Field(..., gt=0, description="Annualized IV as decimal (0.25 = 25%)")
    dte: int = Field(..., ge=1, le=730)
    risk_free_rate: float = Field(default=0.05, ge=0, le=0.20)
    price_range_pct: float = Field(default=0.10, ge=0.02, le=0.50)
    price_step: float = Field(default=10.0, gt=0)


class ProbabilityMatrixResponse(BaseModel):
    """Black-Scholes probability matrix response."""
    symbol: str
    current_price: float
    iv: float
    dte: int
    price_levels: list[float]
    dates: list[str]        # ISO date strings: [expiry-9, expiry-6, expiry-3, expiry]
    matrix: list[list[float]]  # matrix[date_idx][price_idx] = probability


# ============================================================
# Trade Evaluation Card (Phase 2.11)
# ============================================================

class TradeEvaluationCard(BaseModel):
    """
    Structured AI evaluation card for a single strategy.

    Returned by POST /api/v1/evaluate/structured.
    Claude populates verdict, claude_read, key_risks, and thesis_invalidators.
    All numeric fields (entry_price through exit_stop_debit) come from the
    trade data passed in the request; Claude echoes them back unchanged.
    probability_matrix is the pre-computed B-S matrix, also echoed back.
    """
    strategy_key: str
    strategy_label: str
    trade_structure: str            # e.g. "Sell 415P / Buy 410P, Dec 19"
    entry_price: float = 0.0
    max_profit: float = 0.0         # unlimited for long calls → default 0
    max_loss: float = 0.0
    exit_warning_price: float = 0.0 # underlying price that triggers warning
    exit_warning_pnl: float = 0.0   # P&L at warning (negative = loss)
    exit_target_debit: float = 0.0  # debit to close at ~50% profit (spreads only)
    exit_stop_debit: float = 0.0    # debit to close at 2× credit (spreads only)
    probability_matrix: dict = {}   # serialized ProbabilityMatrix from B-S
    score: int                      # 0-100 from strategy scorer (or Claude estimate)
    verdict: str                    # EXECUTE | WAIT | PASS
    claude_read: str                # 2-3 sentences on fit with current conditions
    key_risks: List[str] = []       # 2-3 items, each under 15 words
    thesis_invalidators: List[str] = []  # 2-3 specific price/event conditions
    # Exit levels — underlying stock prices (not option premiums). Populated from
    # Claude's exit_plan response or from top-level fallback fields.
    take_profit: Optional[float] = None    # underlying price at which to close for full profit
    warning_level: Optional[float] = None  # underlying early-warning trigger price
    hard_stop: Optional[float] = None      # underlying price at which to cut the loss
    auto_pass_reason: Optional[str] = None   # set when DTE/credit gate auto-passes before scoring
    dte_warning: Optional[str] = None        # set when DTE is 8-13 (below recommended minimum)
    credit_pct_of_width: Optional[float] = None   # credit spreads only (credit / spread_width)
    debit_pct_of_width: Optional[float] = None    # debit spreads only (debit / spread_width)
    effective_dte: Optional[int] = None      # DTE used for scoring (may differ from nominal if gate override applied)
    asymmetry_penalty: Optional[int] = None    # OTA-505: points deducted for probability skew (0, 8, 15, or 25)
    asymmetry_ratio: Optional[float] = None    # OTA-505: p_max_loss / p_max_profit diagnostic (None if undefined)

    @field_validator("verdict")
    @classmethod
    def verdict_must_be_valid(cls, v: str) -> str:
        if v not in ("EXECUTE", "WAIT", "PASS"):
            raise ValueError(f"verdict must be EXECUTE, WAIT, or PASS; got {v!r}")
        return v

    @field_validator("key_risks", "thesis_invalidators")
    @classmethod
    def between_two_and_three_items(cls, v: List[str]) -> List[str]:
        if v and not (2 <= len(v) <= 3):
            raise ValueError(f"must have 2-3 items when provided; got {len(v)}")
        return v


# ============================================================
# Position Tracking Schemas (Phase 2.10 / 2.2)
# ============================================================

class LegIn(BaseModel):
    """A single option leg within a multi-leg trade structure."""
    side: str           # "long" or "short"
    option_type: str    # "call" or "put"
    strike: float
    expiration: str     # "MM-DD-YYYY"
    contracts: int = 1


class PositionCreate(BaseModel):
    """
    Simplified position create schema (Phase 2.2 spec).
    Uses structured legs list rather than free-form trade_structure dict.
    """
    symbol: str
    strategy: str
    trade_structure: str    # e.g. "bull_put_spread"
    position_type: str      # "paper" or "live"
    legs: list[LegIn]
    entry_price: float
    entry_score: Optional[float] = None
    entry_verdict: Optional[str] = None
    claude_verdict: Optional[str] = None
    claude_score: Optional[float] = None
    claude_summary: Optional[str] = None


class PositionClose(BaseModel):
    """Simplified close schema (Phase 2.2 spec)."""
    close_price: float
    close_reason: Optional[str] = "manual"

class FollowPositionRequest(BaseModel):
    """Follow an existing position (paper or live) for monitoring."""
    symbol: str
    strategy_key: str
    trade_structure: dict           # legs, strikes, expiration
    entry_price: float
    entry_greeks: dict
    entry_iv_rank: float
    entry_sma_alignment: dict
    entry_underlying_price: float
    claude_score: Optional[int] = None
    # Phase 2.11 — populated from TradeEvaluationCard at Follow/Take time
    claude_verdict: Optional[dict] = None       # full TradeEvaluationCard as JSON
    claude_exit_levels: Optional[dict] = None   # exit_warning_price, exit_target_debit, etc.
    claude_probability_matrix: Optional[dict] = None  # pre-computed B-S matrix


class TakePositionRequest(FollowPositionRequest):
    pass  # identical for now — source will be set to LIVE by the route


class ClosePositionRequest(BaseModel):
    """Close an open position with exit price and reason."""
    exit_price: float
    exit_reason: str    # TARGET | WARNING | STOP | EXPIRED | MANUAL


class PositionResponse(BaseModel):
    """Single position returned to the client."""
    position_id: str
    symbol: str
    strategy_key: str
    strategy_label: str
    source: str
    status: str
    entry_price: float
    entry_date: str
    entry_underlying_price: float
    current_price: Optional[float] = None
    current_pnl: Optional[float] = None
    health_grade: Optional[str] = None
    claude_score: Optional[int] = None
    # Phase 2.11 — Claude evaluation data attached at entry
    claude_verdict: Optional[dict] = None
    claude_exit_levels: Optional[dict] = None
    claude_probability_matrix: Optional[dict] = None
    days_held: int
    dte_at_entry: Optional[int] = None
    trade_structure: dict
    # Populated when status == CLOSED
    exit_price: Optional[float] = None
    exit_date: Optional[str] = None
    exit_reason: Optional[str] = None
    outcome_pnl: Optional[float] = None


class PositionListResponse(BaseModel):
    """Paginated list of positions with aggregate stats."""
    positions: list[PositionResponse]
    total: int
    aggregate: dict     # win_rate, avg_pnl, avg_hold_days, by_strategy


class PositionAssessmentCreate(BaseModel):
    """Used by the refresh endpoint to create a new UPDATE assessment."""
    verdict: str
    score: int = Field(..., ge=0, le=100)
    synopsis: Optional[str] = None
    claude_read: str
    exit_levels: Optional[dict] = None
    market_snapshot: Optional[dict] = None
    agent_run_id: Optional[str] = None


class PositionAssessmentResponse(BaseModel):
    """Returned by GET /positions/{id}/assessments."""
    assessment_id: str
    position_id: str
    version_number: int
    assessment_type: str
    verdict: str
    score: int
    synopsis: Optional[str] = None
    claude_read: str
    exit_levels: Optional[dict] = None
    market_snapshot: Optional[dict] = None
    agent_run_id: Optional[str] = None
    created_at: datetime


class PositionCurrentPrice(BaseModel):
    """Per-position result from GET /positions/current-prices."""
    position_id: str
    current_premium: Optional[float] = None
    current_pnl: Optional[float] = None
    pnl_pct: Optional[float] = None
    perf_status: str   # 'green' | 'amber' | 'red' | 'unknown'
    error: Optional[str] = None


class PositionRefreshResponse(BaseModel):
    """Returned by POST /positions/{id}/refresh."""
    assessment: PositionAssessmentResponse
    current_premium: float
    current_pnl: float
    pnl_pct: float
    perf_status: str   # 'green' | 'amber' | 'red'


# ============================================================
# Insight Engine Schemas (Phase 3.6)
# ============================================================

class DeviationResult(BaseModel):
    """
    Result of running a DeviationDetector check.

    Returned by all four check_* methods. Contains everything InsightEngine
    needs to craft an insight: what was detected, how severe it is, and a
    description for Claude's context.
    """
    detected: bool
    deviation_type: Optional[str] = None    # THRESHOLD | TREND | ANOMALY | CORRELATION
    deviation_score: int = 0                # 0-100 severity
    observation: dict = {}                  # what was measured
    baseline: dict = {}                     # what was expected
    description: str = ""                   # human-readable, included in Claude prompt


# ============================================================
# Validation Assessment Schemas (OTA-149)
# ============================================================

class ValidationAssessmentCreate(BaseModel):
    assessment_date: datetime
    jira_ticket: str
    ticker: str
    tab: str          # 'VERTICALS' | 'PUTS_AND_CALLS'
    strike: str
    expiration: str   # mm-dd-yyyy
    score: float
    verdict: str      # 'EXECUTE' | 'WATCH' | 'PASS'
    agreement: bool
    notes: Optional[str] = None


class ValidationAssessmentOut(ValidationAssessmentCreate):
    assessment_id: str
    created_at: datetime

    class Config:
        from_attributes = True


# ============================================================
# Exit Scenario Schemas (Phase 2.11 / OTA-292)
# ============================================================

class ExitScenarioRequest(BaseModel):
    """
    Request for the exit scenario computation engine.
    Pure math — no AI involved.
    """
    spread_type: str            # BEAR_PUT_DEBIT | BULL_CALL_DEBIT | BULL_PUT_CREDIT | BEAR_CALL_CREDIT
    long_strike: float          # strike of the long option leg
    short_strike: float         # strike of the short option leg
    expiry: str                 # ISO date string e.g. "2026-05-15"
    entry_price: float          # per share (e.g. 8.80)
    underlying_price: float     # current underlying price
    iv: float                   # implied volatility as decimal (e.g. 0.28)
    risk_free_rate: float = 0.05


class ExitScenarioRow(BaseModel):
    underlying_price: float
    spread_value: float
    pl_per_contract: float
    pl_pct: float               # pl_per_contract / max_loss (decimal, e.g. 1.84 = +184%)
    probability: float          # discrete PDF probability of landing at this price level
    expected_value: float       # pl_per_contract * probability
    zone: str                   # max_profit | profit | entry | warning | max_loss
    exit_signal: str            # MAX PROFIT | BREAKEVEN | ENTRY | STOP | TIME EXIT | ""


class ExitScenarioResponse(BaseModel):
    rows: List[ExitScenarioRow]
    breakeven: float
    max_profit_price: float     # underlying price at which max profit is achieved
    max_loss_price: float       # underlying price at which max loss is incurred
    total_ev: float             # sum of all expected_value rows
    dte: int
    time_exit_date: str         # mm-dd-yyyy format


# ============================================================
# Trade Verdict Schemas (Phase 2.11 / OTA-297)
# ============================================================

class KeyLevel(BaseModel):
    price: float
    description: str


class TradeVerdictResponse(BaseModel):
    """
    Structured Claude evaluation of a single vertical spread.
    All five fields required — 422 if any are missing.
    """
    ev_commentary: str
    key_level: KeyLevel
    iv_context: str
    verdict: Literal["EXECUTE", "WATCH", "PASS"]
    verdict_rationale: str


class TradeVerdictRequest(BaseModel):
    """
    Request for POST /api/v1/evaluate/trade-verdict.
    Accepts pre-computed spread economics from the exit scenario engine.
    """
    spread_type: str
    long_strike: float
    short_strike: float
    expiry: str
    entry_price: float
    max_profit: float
    max_loss: float
    breakeven: float
    dte: int
    total_ev: float
    ev_pct_of_risk: float       # total_ev / max_loss * 100
    p_max_profit: float         # probability at max profit row (0-1)
    p_breakeven_or_better: float
    p_max_loss: float
    iv: float


class InsightResponse(BaseModel):
    """Insight returned to the frontend."""
    insight_id: str
    domain: str
    entity_id: str
    entity_label: str
    deviation_score: int
    deviation_type: str
    title: str
    body: str
    severity: str
    recommended_actions: Optional[List[dict]] = None
    status: str
    agent_run_id: Optional[str] = None
    created_at: datetime


# ============================================================
# Dashboard Schemas (Phase 2.3)
# ============================================================

class WidgetLayoutItem(BaseModel):
    i: str
    x: int
    y: int
    w: int
    h: int
    minW: int = 2
    minH: int = 2
    isDraggable: bool = False   # Phase 2.3: always False. Phase 2.4: True
    isResizable: bool = False   # Phase 2.3: always False. Phase 2.4: True


class WidgetConfig(BaseModel):
    id: str          # matches WidgetLayoutItem.i
    type: str        # "market_overview"|"actions"|"pnl_by_strategy"|"chart"|"media"
    title: str
    settings: dict = {}


class DashboardLayoutSave(BaseModel):
    layout: list[WidgetLayoutItem]
    widgets: list[WidgetConfig]


class DashboardLayoutResponse(BaseModel):
    layout: list[WidgetLayoutItem]
    widgets: list[WidgetConfig]
    updated_at: Optional[datetime] = None


class MediaItem(BaseModel):
    id: int
    blob_name: str
    caption: Optional[str] = None
    sort_order: int
    sas_url: str    # generated by backend, 15-min expiry — never stored


class DashboardMediaResponse(BaseModel):
    widget_id: str
    items: list[MediaItem]


# ============================================================
# Watchlist Schemas (OTA-258)
# ============================================================

class WatchlistSymbol(BaseModel):
    symbol: str


class WatchlistResponse(BaseModel):
    symbols: list[str]


# ============================================================
# Named Watchlist Schemas (OTA-444, OTA-445)
# ============================================================

class _WatchlistNameBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class NamedWatchlistCreate(_WatchlistNameBase):
    """Create a new named watchlist."""


class NamedWatchlistRename(_WatchlistNameBase):
    """Rename an existing watchlist."""


class NamedWatchlistSymbolAdd(BaseModel):
    symbol: str
