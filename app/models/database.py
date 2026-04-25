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
    Column, Integer, String, Float, Boolean, DateTime, Date, Text, Numeric,
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
    market_data_provider = Column(String(50), default="schwab")
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


class ValidationAssessment(Base):
    """
    One row per trade assessed during a structured validation run.

    Tracks human agreement with Claude/engine verdicts to establish
    baseline agreement rates across Jira milestones.
    """
    __tablename__ = "validation_assessments"

    assessment_id   = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    assessment_date = Column(DateTime, nullable=False)
    jira_ticket     = Column(String(20), nullable=False)
    ticker          = Column(String(20), nullable=False)
    tab             = Column(String(20), nullable=False)   # 'VERTICALS' | 'PUTS_AND_CALLS'
    strike          = Column(String(20), nullable=False)
    expiration      = Column(String(20), nullable=False)
    score           = Column(Numeric(5, 2), nullable=False)
    verdict         = Column(String(20), nullable=False)   # 'EXECUTE' | 'WATCH' | 'PASS'
    agreement       = Column(Boolean, nullable=False)      # True = agree, False = disagree
    notes           = Column(String(500), nullable=True)
    created_at      = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_validation_assessments_ticket", "jira_ticket"),
        Index("ix_validation_assessments_ticker", "ticker"),
    )


class StrategyConfig(Base):
    """
    Per-user overrides to strategy defaults (Phase 2.9).

    Stores user-customised parameters for each strategy as a JSON blob.
    The canonical defaults live in strategy_definitions.STRATEGY_DEFINITIONS;
    this table holds only the deltas the user has chosen to change.
    """
    __tablename__ = "strategy_configs"

    config_id    = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id      = Column(String(36), nullable=False)
    strategy_key = Column(String(50), nullable=False)   # 'steady-paycheck' etc.
    config_json  = Column(Text, nullable=False)          # JSON: user overrides to defaults
    created_at   = Column(DateTime, default=datetime.utcnow)
    updated_at   = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_strategy_configs_user_key", "user_id", "strategy_key"),
    )


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
    user_id = Column(String(36), nullable=False)  # WHY no FK: SKIP_AUTH dev mode compat (same as UserWatchlist)
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


class PositionAssessment(Base):
    """
    Versioned Claude assessment for a tracked position (Phase 2.11 OTA-263).

    assessment_type='ORIGINAL' is created when the position is first followed
    or taken. Subsequent evaluations (triggered by the UI or position monitor)
    are 'UPDATE'. version_number increments per position (1, 2, 3...).

    claude_read, exit_levels, and market_snapshot are stored as-is from the
    TradeEvaluationCard so the full historical record can always be reconstructed.
    """
    __tablename__ = "position_assessments"

    assessment_id  = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    position_id    = Column(String(36), ForeignKey("positions.position_id"), nullable=False)
    version_number = Column(Integer, nullable=False)
    assessment_type = Column(String(20), nullable=False)   # 'ORIGINAL' | 'UPDATE'
    verdict        = Column(String(20), nullable=False)    # 'EXECUTE' | 'WAIT' | 'PASS'
    score          = Column(Integer, nullable=False)        # 0-100
    synopsis       = Column(String(200))                   # 5-7 word Claude summary
    claude_read    = Column(Text, nullable=False)           # full analysis text
    exit_levels    = Column(Text)                           # JSON: take_profit, warning, hard_stop, calendar_exit
    market_snapshot = Column(Text)                          # JSON: underlying_price, iv, delta, spread_mark
    agent_run_id   = Column(String(36))                    # FK to agent_run_log (nullable)
    created_at     = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_position_assessments_position", "position_id", "created_at"),
    )


# ─── Dashboard ────────────────────────────────────────────────────────────────


class DashboardLayout(Base):
    """
    Per-user dashboard layout: grid positions and widget configs.

    layout_json — react-grid-layout position array (JSON)
    widgets_json — widget config array (JSON, includes type/title/settings)

    One row per user (unique=True on user_id). Upserted on save.
    """
    __tablename__ = "dashboard_layouts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), nullable=False, unique=True, index=True)
    layout_json = Column(Text, nullable=False)
    widgets_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DashboardMedia(Base):
    """
    Image metadata for media widgets. One row per image per widget.

    blob_name references a blob in the Azure Blob Storage dashboard-media container.
    SAS URLs are generated at read time (never stored) so they are always fresh.
    """
    __tablename__ = "dashboard_media"

    id = Column(Integer, primary_key=True, autoincrement=True)
    widget_id = Column(String(100), nullable=False, index=True)
    blob_name = Column(String(500), nullable=False)
    caption = Column(String(200), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_dashboard_media_widget", "widget_id", "sort_order"),
    )


# ─── Options Chain Snapshots (OTA-200) ────────────────────────────────────────


class OptionsChainSnapshot(Base):
    """
    Daily options chain snapshot for a symbol, used as the data foundation
    for backtesting (Phase 3.3.x).

    One row per symbol per day — the UniqueConstraint prevents duplicates.
    chain_json stores the full serialized chain as returned by provider.get_chain().
    Normalization into individual contract rows comes in a later phase.

    System-level (not per-user): collection runs nightly for all watchlist symbols.
    """
    __tablename__ = "options_chain_snapshots"

    snapshot_id      = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    symbol           = Column(String(20), nullable=False, index=True)
    snapshot_date    = Column(Date, nullable=False, index=True)
    captured_at      = Column(DateTime, nullable=False)
    underlying_price = Column(Float, nullable=False)
    chain_json       = Column(Text, nullable=False)    # full serialized chain from provider
    contract_count   = Column(Integer, nullable=False) # number of contracts in snapshot
    dte_min          = Column(Integer, nullable=True)  # min DTE in snapshot
    dte_max          = Column(Integer, nullable=True)  # max DTE in snapshot
    provider         = Column(String(50), nullable=False, default="schwab")

    __table_args__ = (
        UniqueConstraint("symbol", "snapshot_date", name="uq_chain_snapshot_symbol_date"),
    )


# ─── Named Watchlists (OTA-444) ───────────────────────────────────────────────


class NamedWatchlist(Base):
    """
    A named watchlist owned by a user. Users can have multiple watchlists.

    One watchlist per user is marked is_default=True and is created lazily
    on first access. The default watchlist cannot be deleted.

    WHY no FK on user_id: Same SKIP_AUTH dev mode compat reason as UserWatchlist.
    """
    __tablename__ = "watchlists"

    id         = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name       = Column(String(100), nullable=False)
    user_id    = Column(String(255), nullable=False)
    is_default = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    symbols = relationship(
        "WatchlistEntry",
        back_populates="watchlist",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_watchlists_user", "user_id"),
    )


class WatchlistEntry(Base):
    """
    A symbol inside a named watchlist.

    UNIQUE on (watchlist_id, symbol): duplicate adds are handled at the
    application layer (return existing row, no error).
    """
    __tablename__ = "watchlist_symbols"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    watchlist_id = Column(
        String(36),
        ForeignKey("watchlists.id", ondelete="CASCADE"),
        nullable=False,
    )
    symbol   = Column(String(20), nullable=False)
    added_at = Column(DateTime, default=datetime.utcnow)

    watchlist = relationship("NamedWatchlist", back_populates="symbols")

    __table_args__ = (
        UniqueConstraint("watchlist_id", "symbol", name="uq_watchlist_symbol"),
        Index("ix_watchlist_symbols_watchlist", "watchlist_id"),
    )


# ─── BFF Session Store (OTA-461) ──────────────────────────────────────────────


class UserSession(Base):
    """
    Server-side session for the BFF identity management pattern.

    Created when a user completes the OIDC login flow. The session_id is
    stored in an httponly cookie on the browser — the actual tokens are
    encrypted and stored here, never exposed to the client.

    csrf_token is returned to the browser via GET /auth/me and must be
    sent as the X-CSRF-Token header on all state-changing requests.
    """
    __tablename__ = "user_sessions"

    id                      = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id              = Column(String(128), unique=True, nullable=False)
    user_id                 = Column(String(255), nullable=False)
    provider                = Column(String(50), nullable=False, default="entra")
    email                   = Column(String(255))
    display_name            = Column(String(255))
    access_token_encrypted  = Column(Text)
    refresh_token_encrypted = Column(Text)
    id_token                = Column(Text)
    token_expires_at        = Column(DateTime)
    csrf_token              = Column(String(128), nullable=False)
    created_at              = Column(DateTime, default=datetime.utcnow)
    expires_at              = Column(DateTime, nullable=False)
    last_active_at          = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_user_sessions_expires_at", "expires_at"),
    )
