"""
Database models using SQLAlchemy ORM.

WHY SQLAlchemy: It's the standard Python ORM. Using it means we can start with
SQLite for development and switch to PostgreSQL for production by changing one
connection string. The models define the shape of our data — every table, column,
and relationship.

MULTI-USER: Every table that holds user-specific data has a user_id foreign key.
This is the foundation of data isolation — queries always filter by the
authenticated user's ID.
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Text,
    ForeignKey, JSON, Index, UniqueConstraint
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    """
    User accounts. Each person who uses the app gets a row here.
    
    Roles:
      - admin: Full access, user management, MCP integration
      - trader: Can connect brokerage, trade with per-trade MFA
      - viewer: Analysis tools only, no brokerage connection
    """
    __tablename__ = "users"

    id = Column(String(36), primary_key=True)  # UUID
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=True)  # Null for Entra ID users
    role = Column(String(20), nullable=False, default="viewer")  # admin, trader, viewer
    is_active = Column(Boolean, default=True)

    # MFA - the actual TOTP secret is in Key Vault, referenced by this flag
    mfa_enabled = Column(Boolean, default=False)
    mfa_verified = Column(Boolean, default=False)  # True after first successful TOTP verify

    # Provider assignments for this user
    market_data_provider = Column(String(50), default="tradier")
    account_provider = Column(String(50), nullable=True)
    trading_provider = Column(String(50), nullable=True)
    trading_enabled = Column(Boolean, default=False)  # Kill switch per user

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    config = relationship("UserConfig", back_populates="user", uselist=False)
    trades = relationship("TradeLog", back_populates="user")
    audit_events = relationship("AuditLog", back_populates="user")


class UserConfig(Base):
    """
    Per-user analysis configuration: filters, scoring weights, risk settings.
    
    This replaces the Setup sheet's B28-B80 cells from the Excel tool.
    Each user gets their own config with their own preferences.
    """
    __tablename__ = "user_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id"), unique=True, nullable=False)

    # --- Symbol / Defaults ---
    default_symbol = Column(String(10), default="QQQ")

    # --- DTE Filters ---
    min_dte = Column(Integer, default=14)
    max_dte = Column(Integer, default=45)

    # --- Strike Filters ---
    strike_range_pct = Column(Float, default=10.0)  # % from current price
    min_open_interest = Column(Integer, default=10)
    min_volume = Column(Integer, default=1)

    # --- Spread Filters ---
    min_spread_width = Column(Float, default=1.0)
    max_spread_width = Column(Float, default=10.0)

    # --- Scoring Weights (must sum to 1.0) ---
    weight_expected_value = Column(Float, default=0.40)
    weight_reward_risk = Column(Float, default=0.30)
    weight_probability = Column(Float, default=0.20)
    weight_liquidity = Column(Float, default=0.10)

    # --- Risk Management ---
    max_risk_per_trade = Column(Float, default=500.0)
    profit_target_pct = Column(Float, default=50.0)  # Take profit at 50% of max
    stop_loss_pct = Column(Float, default=100.0)  # Stop at 100% loss (full debit)

    # --- Full config as JSON for extensibility ---
    # Any settings not in dedicated columns go here
    extra_settings = Column(JSON, default=dict)

    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="config")


class TradeLog(Base):
    """
    Trade journal: every trade validated, previewed, or executed.
    
    This is your trade history — what you traded, why, and how it turned out.
    Critical for learning and for the audit trail.
    """
    __tablename__ = "trade_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)

    # What
    symbol = Column(String(10), nullable=False)
    strategy = Column(String(50), nullable=False)  # bull_call_spread, long_call, etc.
    legs = Column(JSON, nullable=False)  # [{strike, type, side, quantity}, ...]
    quantity = Column(Integer, default=1)

    # Pricing at time of trade
    underlying_price = Column(Float)
    net_debit = Column(Float)
    max_profit = Column(Float)
    max_loss = Column(Float)
    breakeven = Column(Float)

    # Execution
    status = Column(String(20), nullable=False)  # previewed, validated, executed, cancelled, expired
    broker_order_id = Column(String(100), nullable=True)
    fill_price = Column(Float, nullable=True)

    # MFA verification
    mfa_challenge_used = Column(Boolean, default=False)

    # Audit
    session_id = Column(String(100))
    ip_address = Column(String(45))
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="trades")

    __table_args__ = (
        Index("ix_trade_log_user_date", "user_id", "created_at"),
    )


class AuditLog(Base):
    """
    Security audit trail: logins, config changes, trade actions, failures.
    
    WHY: When real money is involved, you need to know exactly what happened
    and when. This table is append-only — rows are never updated or deleted.
    """
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)  # Null for failed logins

    event_type = Column(String(50), nullable=False)
    # Event types: login_success, login_failure, mfa_setup, mfa_verify,
    #   config_change, trade_preview, trade_execute, trade_cancel,
    #   provider_connect, provider_disconnect, role_change

    detail = Column(JSON, nullable=True)  # Event-specific data
    ip_address = Column(String(45), nullable=True)
    session_id = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="audit_events")

    __table_args__ = (
        Index("ix_audit_log_user_event", "user_id", "event_type"),
        Index("ix_audit_log_created", "created_at"),
    )


class UserWatchlist(Base):
    """
    Per-user watchlist: the symbols shown in the sidebar.

    WHY no FK on user_id: Allows SKIP_AUTH dev mode (user_id = "dev-user")
    to work without needing a real user row in the users table.
    The position column preserves sidebar order (0 = top).
    """
    __tablename__ = "user_watchlist"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), nullable=False, index=True)
    symbol = Column(String(10), nullable=False)
    name = Column(String(100), nullable=True)
    position = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "symbol", name="uq_user_watchlist_symbol"),
        Index("ix_user_watchlist_user_pos", "user_id", "position"),
    )


class UserFavorite(Base):
    """
    Per-user starred trades.

    trade_id is the same unique key the frontend builds (e.g. "SPY-call-450-460-2024-01-19").
    trade_data stores the full snapshot so the Favorites page can show the
    original pricing and score without re-fetching.

    WHY no FK on user_id: Same reason as UserWatchlist — dev mode compatibility.
    """
    __tablename__ = "user_favorites"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), nullable=False, index=True)
    trade_id = Column(String(300), nullable=False)   # Unique trade key from frontend
    symbol = Column(String(10), nullable=False)
    label = Column(String(300), nullable=True)        # Display name
    strategy = Column(String(50), nullable=True)      # bull_call_spread, long_call, etc.
    trade_data = Column(JSON, nullable=False)          # Full trade snapshot
    saved_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "trade_id", name="uq_user_favorites_trade"),
        Index("ix_user_favorites_user", "user_id"),
    )


class SchwabToken(Base):
    """
    Schwab OAuth tokens for persistent storage.

    WHY: Schwab tokens were previously stored in-memory in the provider instance.
    This meant every backend restart required users to re-authenticate via OAuth.
    By storing tokens in the database, we can:
    1. Persist tokens across restarts
    2. Auto-refresh expired tokens using the refresh_token
    3. Support multiple users each with their own Schwab connection

    SECURITY: In production, tokens should be encrypted at rest using Azure Key Vault
    or similar. For now we store them as-is (database is behind auth).
    """
    __tablename__ = "schwab_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id"), unique=True, nullable=False, index=True)

    # OAuth tokens
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text, nullable=False)

    # Token expiration times
    token_expires_at = Column(DateTime, nullable=False)
    refresh_expires_at = Column(DateTime, nullable=False)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", backref="schwab_token")

    __table_args__ = (
        Index("ix_schwab_tokens_user", "user_id"),
    )


class AgentRunLog(Base):
    """
    Full audit trail for every AI agent invocation.

    WHY: OpenTelemetry traces expire after 90 days and lack relational structure.
    This table is the permanent business record — every stage of every agent call,
    including the exact prompt and model response. Linked to Application Insights
    traces via otel_trace_id for cross-referencing.

    See app/skills/ota-agentic-strategy/SKILL.md for the full observability design.
    """
    __tablename__ = "agent_run_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(36), nullable=False)  # UUID linking multi-stage sessions

    agent_name = Column(String(100), nullable=False)
    stage = Column(String(50), nullable=False)       # triage | deep_dive | followup
    trade_key = Column(String(255), nullable=True)   # "{symbol}:{spread}:{expiration}"
    symbol = Column(String(20), nullable=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)

    # Full inputs sent to the model
    prompt_system = Column(Text, nullable=True)
    prompt_user = Column(Text, nullable=True)
    prompt_version = Column(String(50), nullable=True)
    market_snapshot = Column(JSON, nullable=True)   # price, SMAs, VIX at call time
    trade_snapshot = Column(JSON, nullable=True)    # trade metrics at call time

    # Full outputs
    model_response_raw = Column(Text, nullable=True)
    verdict = Column(String(20), nullable=True)     # EXECUTE | WAIT | PASS | STRONG | MEDIUM | WEAK
    verdict_summary = Column(Text, nullable=True)

    # Telemetry linkage
    otel_trace_id = Column(String(64), nullable=True)  # links to Application Insights trace

    # Performance
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    model_name = Column(String(100), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_agent_run_log_run_id", "run_id"),
        Index("ix_agent_run_log_user", "user_id"),
        Index("ix_agent_run_log_trade_key", "trade_key"),
    )


class TradeRecommendation(Base):
    """
    Persisted AI recommendations, one row per trade key.

    WHY: The agent_run_log stores every invocation. This table stores the
    current recommendation for each trade — the "what Claude said last" record.
    Upserted on each evaluation so the UI can show the prior recommendation
    before asking for a new one (enabling triage vs deep-dive stage logic).

    Linked back to agent_run_log via run_id for full traceability.
    """
    __tablename__ = "trade_recommendations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_key = Column(String(255), nullable=False, unique=True, index=True)
    symbol = Column(String(20), nullable=False)
    spread_label = Column(String(100), nullable=False)
    expiration = Column(String(20), nullable=False)

    verdict = Column(String(20), nullable=False)    # EXECUTE | WAIT | PASS | STRONG | MEDIUM | WEAK
    rank = Column(String(20), nullable=True)
    verdict_summary = Column(Text, nullable=False)

    market_snapshot = Column(JSON, nullable=False)
    trade_snapshot = Column(JSON, nullable=False)

    run_id = Column(String(36), nullable=True)      # links back to agent_run_log
    prompt_version = Column(String(50), nullable=True)

    evaluated_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
