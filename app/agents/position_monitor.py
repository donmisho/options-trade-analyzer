"""
Position Monitor Agent — Phase 3.5 Stream B2.

Runs after market close (4:15pm ET Mon-Fri via APScheduler, or on-demand via
POST /api/v1/agents/position-monitor/run). For every open position:

  1. Refreshes market context from all registered ContextSource adapters
     (cache hit = no Schwab call; only fetches when TTL has expired)
  2. Builds a batch prompt with all positions + their current signals
  3. Calls Claude via FoundryEvalAdapter.chat()
  4. Parses PositionHealthUpdate JSON array
  5. Writes health grades + current P&L back to positions table
  6. Flags positions needing Insight Engine escalation (Phase 3.6)
  7. Writes full run to agent_run_log

WHY batch: one Claude call per run regardless of position count. Batching is
10× cheaper than per-position calls and still gives the model full context to
compare positions side-by-side.
"""

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional, List, TYPE_CHECKING

from pydantic import BaseModel
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.context_store import ContextStore
from app.agents.telemetry import invoke_with_tracing
from app.models.database import Position, AgentRunLog
from app.providers.base import ContextSource
from app.skills.skill_loader import get_skill

if TYPE_CHECKING:
    from app.ai.foundry_adapter import FoundryEvalAdapter

logger = logging.getLogger(__name__)


# ─── Output schema ────────────────────────────────────────────────────────────

class PositionHealthUpdate(BaseModel):
    position_id: str
    health_grade: str           # A|B|C|D|F
    current_pnl: float
    needs_insight: bool
    insight_context: Optional[dict] = None


# ─── Run result ───────────────────────────────────────────────────────────────

@dataclass
class AgentRunResult:
    run_id: str
    positions_processed: int
    insights_triggered: int
    run_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    error: Optional[str] = None


# ─── Agent ────────────────────────────────────────────────────────────────────

class PositionMonitorAgent:
    """
    Autonomous position health agent.

    Inject at app startup via init_agents_routes(). Context sources are
    iterated on every run — registering a new ContextSource (sentiment, etc.)
    requires no changes here.
    """

    def __init__(
        self,
        ai_adapter: "FoundryEvalAdapter",
        context_sources: List[ContextSource],
    ):
        self._adapter = ai_adapter
        self._context_sources = context_sources
        self._skill = get_skill("position-monitor")
        self._last_run: Optional[AgentRunResult] = None

    async def run(
        self,
        db: AsyncSession,
        user_id: Optional[str] = None,
    ) -> AgentRunResult:
        """
        Main entry point. Process all (or one user's) open positions.
        Returns a summary. Always writes to agent_run_log.
        """
        run_id = str(uuid.uuid4())

        # 1. Load open positions
        positions = await self._load_open_positions(db, user_id)
        if not positions:
            logger.info("PositionMonitorAgent: no open positions — nothing to do")
            result = AgentRunResult(run_id=run_id, positions_processed=0, insights_triggered=0)
            self._last_run = result
            return result

        logger.info(f"PositionMonitorAgent: processing {len(positions)} positions")

        # 2. Refresh context for every unique symbol (cache-first)
        context_store = ContextStore(db)
        symbol_contexts: dict[str, list] = {}
        for symbol in {p.symbol for p in positions}:
            signals = []
            for source in self._context_sources:
                try:
                    value = await context_store.refresh_if_stale(symbol, source)
                    if value:
                        signals.append({
                            "source_id":   source.source_id,
                            "signal_type": source.signal_type,
                            "value":       value,
                        })
                except Exception as e:
                    logger.warning(
                        f"PositionMonitorAgent: context fetch failed "
                        f"{symbol}/{source.source_id}: {e}"
                    )
            symbol_contexts[symbol] = signals

        # 3. Build prompt
        current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        positions_payload = self._build_positions_payload(positions, symbol_contexts, current_date)
        system_prompt = self._skill.get("POSITION_MONITOR_SYSTEM")
        user_message = self._skill.render(
            "POSITION_MONITOR_USER",
            position_count=len(positions),
            current_date=current_date,
            positions_json=json.dumps(positions_payload, indent=2),
        )

        # 4. Call Claude
        updates: List[PositionHealthUpdate] = []
        raw_text = ""
        input_tokens = output_tokens = 0
        model_name = ""
        error_msg = None

        async with invoke_with_tracing(
            "position-monitor", "health_check",
            session_id=run_id,
            prompt_version=self._skill.prompt_version,
        ) as span_ctx:
            try:
                result = await self._adapter.chat(
                    system_prompt, user_message, max_tokens=2000
                )
                raw_text = result["text"]
                input_tokens = result["input_tokens"]
                output_tokens = result["output_tokens"]
                model_name = result.get("model", "")
                span_ctx["input_tokens"] = input_tokens
                span_ctx["output_tokens"] = output_tokens
            except Exception as e:
                logger.error(f"PositionMonitorAgent: Claude call failed: {e}")
                error_msg = str(e)

        # 5. Parse health updates
        if raw_text:
            updates = self._parse_updates(raw_text)

        # 6. Apply updates to positions table
        if updates:
            await self._apply_updates(db, updates)

        # 7. Commit context store + position writes
        await db.commit()

        insights_count = sum(1 for u in updates if u.needs_insight)

        # 8. Write agent_run_log (nullable user_id — this is a system-level run)
        db.add(AgentRunLog(
            run_id=run_id,
            agent_name="position-monitor",
            stage="health_check",
            symbol=None,
            user_id=user_id,
            prompt_system=system_prompt,
            prompt_user=user_message,
            prompt_version=self._skill.prompt_version,
            market_snapshot={"symbols": list(symbol_contexts.keys())},
            trade_snapshot={"position_ids": [p.position_id for p in positions]},
            model_response_raw=raw_text,
            verdict=None,
            verdict_summary=(
                f"{len(updates)} updates, {insights_count} escalations"
                if not error_msg else f"ERROR: {error_msg}"
            ),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model_name=model_name,
            created_at=datetime.now(timezone.utc),
        ))
        await db.commit()

        run_result = AgentRunResult(
            run_id=run_id,
            positions_processed=len(positions),
            insights_triggered=insights_count,
            error=error_msg,
        )
        self._last_run = run_result
        logger.info(
            f"PositionMonitorAgent: done — {len(positions)} positions, "
            f"{insights_count} escalations, run_id={run_id}"
        )
        return run_result

    # ── Private helpers ────────────────────────────────────────────────────────

    async def _load_open_positions(
        self,
        db: AsyncSession,
        user_id: Optional[str],
    ) -> List[Position]:
        stmt = select(Position).where(
            or_(Position.status == "FOLLOWING", Position.status == "LIVE")
        )
        if user_id:
            stmt = stmt.where(Position.user_id == user_id)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    def _build_positions_payload(
        self,
        positions: List[Position],
        symbol_contexts: dict,
        current_date: str,
    ) -> list:
        payload = []
        for pos in positions:
            entry_date = pos.entry_date
            if entry_date.tzinfo is None:
                entry_date = entry_date.replace(tzinfo=timezone.utc)
            days_held = (datetime.now(timezone.utc) - entry_date).days

            # Parse exit levels from claude_exit_levels JSON
            exit_levels = None
            if pos.claude_exit_levels:
                try:
                    raw = pos.claude_exit_levels
                    exit_levels = json.loads(raw) if isinstance(raw, str) else raw
                except (ValueError, TypeError):
                    pass

            # Estimate DTE from trade_structure
            dte_remaining = None
            try:
                ts = pos.trade_structure
                ts_dict = json.loads(ts) if isinstance(ts, str) else (ts or {})
                exp_str = ts_dict.get("expiration") or (
                    ts_dict.get("legs", [{}])[0].get("expiration") if ts_dict.get("legs") else None
                )
                if exp_str:
                    from datetime import date
                    exp_date = date.fromisoformat(exp_str[:10])
                    dte_remaining = max(0, (exp_date - date.today()).days)
            except Exception:
                pass

            payload.append({
                "position_id":            pos.position_id,
                "symbol":                 pos.symbol,
                "strategy_key":           pos.strategy_key,
                "strategy_label":         pos.strategy_key.replace("-", " ").title(),
                "entry_price":            float(pos.entry_price) if pos.entry_price else 0.0,
                "entry_date":             pos.entry_date.strftime("%Y-%m-%d"),
                "entry_underlying_price": float(pos.entry_underlying_price) if pos.entry_underlying_price else 0.0,
                "current_context":        symbol_contexts.get(pos.symbol, []),
                "exit_levels":            exit_levels,
                "days_held":              days_held,
                "dte_remaining":          dte_remaining,
            })
        return payload

    def _parse_updates(self, raw: str) -> List[PositionHealthUpdate]:
        """Parse Claude's JSON response into PositionHealthUpdate list."""
        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            inner = "\n".join(lines[1:]).strip()
            if inner.endswith("```"):
                inner = inner[:-3].strip()
            text = inner
        try:
            data = json.loads(text)
            return [PositionHealthUpdate(**item) for item in data]
        except Exception as e:
            logger.error(f"PositionMonitorAgent: failed to parse updates: {e}\nRaw: {raw[:300]}")
            return []

    async def _apply_updates(
        self,
        db: AsyncSession,
        updates: List[PositionHealthUpdate],
    ) -> None:
        """Write health grade + current P&L back to positions table."""
        now = datetime.now(timezone.utc)
        for update in updates:
            result = await db.execute(
                select(Position).where(Position.position_id == update.position_id)
            )
            pos = result.scalar_one_or_none()
            if not pos:
                logger.warning(
                    f"PositionMonitorAgent: position {update.position_id} not found — skipping"
                )
                continue
            pos.health_grade = update.health_grade
            pos.current_pnl = update.current_pnl
            pos.last_monitored_at = now
            pos.updated_at = now
