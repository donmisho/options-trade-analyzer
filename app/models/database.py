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

import uuid
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Text, Numeric,
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
    Persisted AI recommendations, one row per (user, trade_key).

    WHY: The agent_run_log stores every invocation. This table stores the
    current recommendation for each trade — the "what Claude said last" record.
    Upserted on each evaluation so the UI can show the prior recommendation
    before asking for a new one (enabling triage vs deep-dive stage logic).

    Linked back to agent_run_log via run_id for full traceability.

    NOTE: user_id was added in migration v2. Existing rows have user_id=NULL.
    The unique constraint on trade_key is kept for backward compat; the
    application layer now scopes queries by user_id when available.
    """
    __tablename__ = "trade_recommendations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    trade_key = Column(String(255), nullable=False, index=True)
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

    __table_args__ = (
        UniqueConstraint("user_id", "trade_key", name="uq_trade_recommendations_user_key"),
        Index("ix_trade_recommendations_user_symbol", "user_id", "symbol"),
    )


# ─── Market Data Persistence ──────────────────────────────────────────────────


class SymbolQuote(Base):
    """
    Snapshot of a stock quote at the moment it was requested.

    Every call to GET /market/quote/{symbol} writes one row. This creates
    a price history keyed to the user who requested it, enabling later
    analysis of how price moved relative to trade decisions.
    """
    __tablename__ = "symbol_quotes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    symbol = Column(String(10), nullable=False)

    price = Column(Float, nullable=True)
    bid = Column(Float, nullable=True)
    ask = Column(Float, nullable=True)
    change = Column(Float, nullable=True)
    change_pct = Column(Float, nullable=True)
    volume = Column(Integer, nullable=True)
    provider = Column(String(50), nullable=True)

    captured_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_symbol_quotes_user_symbol_time", "user_id", "symbol", "captured_at"),
        Index("ix_symbol_quotes_symbol_time", "symbol", "captured_at"),
    )


class OptionChainSnapshot(Base):
    """
    Full raw option chain captured at the time of an analysis request.

    Stored as a JSON blob alongside the underlying price and metadata.
    Referenced by AnalysisRun so the exact input data can be reconstructed
    for any historical analysis — critical for algorithm backtesting.
    """
    __tablename__ = "option_chain_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    symbol = Column(String(10), nullable=False)
    underlying_price = Column(Float, nullable=True)
    provider = Column(String(50), nullable=True)
    contract_count = Column(Integer, nullable=True)  # len(contracts) for quick filtering
    chain_data = Column(JSON, nullable=False)          # full list of contracts
    captured_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_option_chain_snapshots_user_symbol", "user_id", "symbol", "captured_at"),
        Index("ix_option_chain_snapshots_symbol_time", "symbol", "captured_at"),
    )


# ─── Analysis Run Persistence ─────────────────────────────────────────────────


class AnalysisRun(Base):
    """
    One row per call to the analysis engine (/analyze/verticals or /analyze/long-calls).

    Records the exact config and scoring weights used so results can be
    reproduced and compared as the algorithm evolves. The filter_params
    and scoring_weights columns are the "why these trades scored this way"
    record — essential for algorithm quality measurement.
    """
    __tablename__ = "analysis_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    symbol = Column(String(10), nullable=False)
    analysis_type = Column(String(20), nullable=False)  # "verticals" | "naked"
    underlying_price = Column(Float, nullable=True)
    provider = Column(String(50), nullable=True)

    # FK to the raw chain used — nullable because chain capture can fail independently
    chain_snapshot_id = Column(Integer, ForeignKey("option_chain_snapshots.id"), nullable=True)

    # Exact parameters used (snapshot so algo changes don't alter historical records)
    scoring_weights = Column(JSON, nullable=False)
    filter_params = Column(JSON, nullable=False)

    # Outcome counts
    result_count = Column(Integer, nullable=True)   # rows returned to frontend (capped)
    total_valid = Column(Integer, nullable=True)    # total that passed filters before cap

    ran_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    analyzed_trades = relationship("AnalyzedTrade", back_populates="run")

    __table_args__ = (
        Index("ix_analysis_runs_user_symbol", "user_id", "symbol", "ran_at"),
        Index("ix_analysis_runs_symbol_time", "symbol", "ran_at"),
    )


class AnalyzedTrade(Base):
    """
    Every individual trade scored during an analysis run.

    This is the core algorithm quality dataset. By storing the full score
    breakdown (each component score before weighting) alongside the weights
    used, we can:
      - Replay any historical analysis exactly
      - Measure how composite scores correlated with actual price outcomes
      - A/B test different weighting schemes against the same chain data
      - Track how a specific strike/expiration scored across multiple sessions

    Covers both vertical spreads and naked options in one table.
    Type-specific fields are nullable (e.g. short_strike is NULL for naked options).
    """
    __tablename__ = "analyzed_trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey("analysis_runs.id"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    symbol = Column(String(10), nullable=False)
    analysis_type = Column(String(20), nullable=False)  # "vertical" | "naked"

    # Trade identity
    spread_type = Column(String(20), nullable=True)    # bull_call | bear_put | long_call | long_put
    long_strike = Column(Float, nullable=True)          # buy leg (verticals) or strike (naked)
    short_strike = Column(Float, nullable=True)         # sell leg (verticals only)
    option_type = Column(String(10), nullable=True)     # call | put
    expiration = Column(String(20), nullable=True)
    dte = Column(Integer, nullable=True)

    # Market context at time of analysis
    underlying_price = Column(Float, nullable=True)

    # Pricing (vertical spreads)
    net_debit = Column(Float, nullable=True)
    max_profit = Column(Float, nullable=True)
    max_loss = Column(Float, nullable=True)
    breakeven = Column(Float, nullable=True)
    rr_ratio = Column(Float, nullable=True)
    prob_of_profit = Column(Float, nullable=True)
    ev_raw = Column(Float, nullable=True)

    # Naked option specifics
    premium_dollars = Column(Float, nullable=True)
    delta = Column(Float, nullable=True)
    theta_per_day = Column(Float, nullable=True)
    iv = Column(Float, nullable=True)

    # Liquidity
    long_volume = Column(Integer, nullable=True)
    short_volume = Column(Integer, nullable=True)
    long_oi = Column(Integer, nullable=True)
    short_oi = Column(Integer, nullable=True)

    # Scores — the full breakdown before weighting, not just the composite
    composite_score = Column(Float, nullable=False)
    score_breakdown = Column(JSON, nullable=False)
    # score_breakdown shape (verticals): {ev_score, rr_score, prob_score, liquidity_score, theta_score}
    # score_breakdown shape (naked):     {delta_score, theta_score, iv_score, rr_score, liquidity_score}
    scoring_weights = Column(JSON, nullable=False)  # weights used (duplicated from run for self-contained rows)

    captured_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    run = relationship("AnalysisRun", back_populates="analyzed_trades")

    __table_args__ = (
        Index("ix_analyzed_trades_run", "run_id"),
        Index("ix_analyzed_trades_user_symbol", "user_id", "symbol", "captured_at"),
        Index("ix_analyzed_trades_symbol_expiry", "symbol", "expiration"),
    )


# ─── Signal Context Store ─────────────────────────────────────────────────────


class SymbolContext(Base):
    """
    Short-lived signal data for a symbol from any registered ContextSource.

    WHY: The Position Monitor Agent needs current price, IV, and other signals
    to evaluate position health. Fetching from the brokerage on every run is
    slow and burns API quota. This table acts as a TTL-aware cache — the agent
    checks here first, only re-fetches from the source if the signal is stale.

    The composite index on (symbol, source_id, expires_at) makes the common
    query "is there a fresh signal for this symbol from this source?" fast.
    """
    __tablename__ = "symbol_context"

    context_id  = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    symbol      = Column(String(20), nullable=False, index=True)
    source_id   = Column(String(50), nullable=False)   # e.g. "schwab_quotes"
    signal_type = Column(String(50), nullable=False)   # PRICE | SENTIMENT | FUNDAMENTAL | TECHNICAL | NEWS
    signal_value = Column(Text, nullable=False)        # JSON blob — shape defined by source
    captured_at = Column(DateTime, default=datetime.utcnow)
    expires_at  = Column(DateTime, nullable=False)

    __table_args__ = (
        Index("ix_symbol_context_lookup", "symbol", "source_id", "expires_at"),
    )


# ─── Insight Engine ───────────────────────────────────────────────────────────


class Insight(Base):
    """
    An AI-generated insight for a monitored entity.

    Created by InsightEngine when a deviation is detected. Domain-agnostic —
    the domain field determines what kind of entity is being monitored
    (options position, manufacturing equipment, customer account, etc.).

    Status lifecycle: ACTIVE → DISMISSED | ACTED_ON
    One active insight per entity per deviation type — duplicates are suppressed
    (existing row is updated instead of creating a new one).
    """
    __tablename__ = "insights"

    insight_id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    domain              = Column(String(50), nullable=False)     # 'options' | 'manufacturing'
    entity_id           = Column(String(100), nullable=False)    # position_id, machine_id
    entity_label        = Column(String(200), nullable=False)    # human-readable
    observation         = Column(Text, nullable=False)           # JSON
    baseline            = Column(Text, nullable=False)           # JSON
    deviation_score     = Column(Integer, nullable=False)        # 0-100
    deviation_type      = Column(String(50), nullable=False)     # THRESHOLD|TREND|ANOMALY|CORRELATION
    title               = Column(String(200), nullable=False)
    body                = Column(String(1000), nullable=False)
    severity            = Column(String(20), nullable=False)     # INFO|WARNING|CRITICAL
    recommended_actions = Column(Text)                           # JSON array
    status              = Column(String(20), default="ACTIVE")   # ACTIVE|DISMISSED|ACTED_ON
    source_signals      = Column(Text)                           # JSON: which sources triggered
    agent_run_id        = Column(String(36))                     # FK to agent_run_log
    created_at          = Column(DateTime, default=datetime.utcnow)
    dismissed_at        = Column(DateTime)
    acted_on_at         = Column(DateTime)

    __table_args__ = (
        Index("ix_insights_domain_entity", "domain", "entity_id", "status"),
        Index("ix_insights_created", "created_at"),
    )


# ─── Position Tracking ────────────────────────────────────────────────────────


class Position(Base):
    """
    A tracked options position, paper or live.

    One row per position the user has chosen to follow. Status progresses
    from FOLLOWING → CLOSED (or EXPIRED). Claude fields (probability_matrix,
    exit_levels, verdict) are populated in Phase 2.11 by the monitoring agent.

    trade_structure stores the full leg definition (strikes, expiration, quantity)
    as JSON so any strategy type can be represented without schema changes.

    WHY UUID primary key: positions may be created client-side and synced later;
    UUIDs avoid insert-order collisions across devices or parallel sessions.
    """
    __tablename__ = "positions"

    position_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    symbol = Column(String(20), nullable=False)
    strategy_key = Column(String(50), nullable=False)
    trade_structure = Column(Text, nullable=False)           # JSON
    source = Column(String(10), nullable=False)              # PAPER | LIVE
    status = Column(String(20), nullable=False, default="FOLLOWING")

    entry_price = Column(Numeric(10, 4))
    entry_date = Column(DateTime, nullable=False)
    entry_greeks = Column(Text)                              # JSON
    entry_iv_rank = Column(Numeric(5, 2))
    entry_sma_alignment = Column(Text)                       # JSON
    entry_underlying_price = Column(Numeric(10, 4))

    # Populated by monitoring agent (Phase 2.11)
    claude_probability_matrix = Column(Text)                 # JSON
    claude_exit_levels = Column(Text)                        # JSON
    claude_verdict = Column(Text)                            # JSON
    claude_score = Column(Integer)

    health_grade = Column(String(2))                         # A|B|C|D|F
    current_price = Column(Numeric(10, 4))
    current_pnl = Column(Numeric(10, 4))
    last_monitored_at = Column(DateTime)

    exit_price = Column(Numeric(10, 4))
    exit_date = Column(DateTime)
    exit_reason = Column(String(50))
    outcome_pnl = Column(Numeric(10, 4))

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_positions_user_status", "user_id", "status"),
        Index("ix_positions_user_symbol", "user_id", "symbol"),
    )
