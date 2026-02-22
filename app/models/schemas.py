"""
Pydantic schemas for request/response validation.

WHY Pydantic: FastAPI uses Pydantic models to validate incoming data and
serialize responses. If someone sends a bad request (wrong type, missing field),
FastAPI returns a clear error automatically. These schemas are the "contract"
between your API and its consumers (web app, Excel, MCP).
"""

from pydantic import BaseModel, Field, EmailStr
from typing import Optional
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
    profit_target_pct: Optional[float] = Field(None, ge=0, le=100)
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
