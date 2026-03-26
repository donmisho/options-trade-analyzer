"""
Prompt builder for trade evaluations.

WHY a separate file: Both the Anthropic and Foundry adapters need to
build the same prompt. Rather than duplicating the prompt template in
two places (which would drift out of sync), this module is the single
source of truth for how we talk to Claude about trades.

The system prompt and user prompt are built from the TradeContext dataclass.
The system prompt is a CONSTANT — per trade_evaluation_requirements.md:
"The AI system prompt should be stored as a constant, not user-editable."

Exit levels are COMPUTED here and passed INTO the prompt — per requirements:
"Exit levels should be computed client-side and passed INTO the prompt
(don't ask the AI to calculate math)."
"""

import json
from .base import TradeContext


# ─── System Prompt (constant, not user-editable) ──────────────────

SYSTEM_PROMPT = """You are an expert options trading coach evaluating trade setups for a disciplined retail trader.
Your job is to assess whether a proposed options trade aligns with the trader's thesis, technical
picture, and risk parameters — then deliver a clear, actionable verdict.

RESPONSE FORMAT RULES (follow exactly):
- First line: ⚡ VERDICT: EXECUTE or ⚡ VERDICT: WAIT or ⚡ VERDICT: PASS
- Second section: ## Summary — 2-3 sentence bottom line up front
- Then these sections in order, each starting with ##:
  ## Thesis vs. Chart Alignment
  ## Risk/Reward Quality
  ## Probability vs. Expected Move
  ## Red Flags & Alternatives
- Do NOT include an Exit Plan section — exit levels are displayed separately by the app.
- Do NOT include a "Final Word" or "Conclusion" section.

FORMATTING RULES (critical — the app parses your markdown):
- Section headings: use ## with NO numbering (not "1." or "2."), NO trailing emoji. Example: ## Risk/Reward Quality
- Sub-headings within sections: use **BOLD TEXT** on its own line. Put any emoji BEFORE the text: ✅ **STRONG ALIGNMENT** not **STRONG ALIGNMENT** ✅
- Bullet points: use - for all bullets. Put any emoji at the START of the bullet text: - 🎯 Target reaches strike, not - Target reaches strike 🎯
- Horizontal rules: do NOT use --- or —— between sections
- Numbered lists: do NOT use 1. 2. 3. — use - bullets instead
- Sub-section headers like ### are not allowed — use **BOLD** instead

Be direct. No fluff. The trader is busy and needs fast, clear guidance."""


# ─── Exit Level Calculator ────────────────────────────────────────

def compute_exit_levels(context: TradeContext) -> dict:
    """
    Pre-calculate exit levels from trade parameters.
    
    WHY pre-calculate: These are pure math — no AI needed. Computing
    them here means:
    1. Claude doesn't waste tokens doing arithmetic
    2. The UI can display them instantly (before the API call finishes)
    3. They're consistent — the same formula every time
    
    Formulas from trade_evaluation_requirements.md:
      stopLoss         = debit_paid × 0.50
      warningLevel     = debit_paid × 0.67
      scaleOutTarget   = debit_paid × 1.60
      fullProfitTarget = max_profit × 0.75
      underlyingStop   = min(sma_short, price - price × 0.015)
      underlyingTarget = expected_move_target
    """
    price = context.current_price
    target = context.expected_move_target or (
        price * 1.02 if context.direction == "Bullish" else price * 0.98
    )

    return {
        "stop_loss": round(context.debit_paid * 0.50, 2),
        "warning_level": round(context.debit_paid * 0.67, 2),
        "scale_out_target": round(context.debit_paid * 1.60, 2),
        "full_profit_target": round(context.max_profit * 0.75, 2),
        "underlying_stop": round(
            min(context.sma_short, price - price * 0.015), 2
        ),
        "underlying_target": round(target, 2),
    }


# ─── User Prompt Builder ─────────────────────────────────────────

def build_trade_prompt(context: TradeContext) -> str:
    """
    Assemble the user message from trade context.
    
    This follows the exact prompt template from trade_evaluation_requirements.md.
    All values are injected from the TradeContext dataclass.
    """
    # Compute exit levels (or use pre-computed ones if provided)
    exits = context.exit_levels or compute_exit_levels(context)

    # Determine MA alignment description
    if context.sma_short > context.sma_mid > context.sma_long:
        alignment = "Bullish - price above all 3 SMAs, upward alignment"
    elif context.sma_short < context.sma_mid < context.sma_long:
        alignment = "Bearish - price below all 3 SMAs, downward alignment"
    else:
        alignment = "Mixed - SMAs not cleanly aligned"

    # Override if the context already has an alignment string
    ma_alignment = context.ma_alignment or alignment

    prompt = f"""TRADE EVALUATION REQUEST

=== MARKET CONTEXT ===
Asset: {context.symbol} | Price: ${context.current_price:.2f}
SMA {context.sma_periods.get('short', 8)}: ${context.sma_short:.2f} | SMA {context.sma_periods.get('mid', 21)}: ${context.sma_mid:.2f} | SMA {context.sma_periods.get('long', 50)}: ${context.sma_long:.2f}
MA Alignment: {ma_alignment}
VIX: {context.vix or 'N/A'}

=== MY THESIS ===
Direction: {context.direction}
Timeframe: {context.timeframe_days} days
Expected Move Target: {f'${context.expected_move_target:.2f}' if context.expected_move_target else 'not specified'}
Conviction: {context.conviction}

=== PROPOSED TRADE ===
Strategy: {context.strategy_type}
Spread: {context.spread} | Expiration: {context.expiration}
Debit Paid: ${context.debit_paid:.2f} | Max Profit: ${context.max_profit:.2f} (per contract: ${context.max_profit * 100:.0f})
R:R: {context.rr_ratio:.2f} | Prob of Profit: {context.prob_of_profit * 100:.0f}%
{f'Composite Score: {context.composite_score:.4f}' if context.composite_score else ''}
Risk Budget: ${context.risk_budget:.0f} | Contracts: {context.num_contracts} | Total Cost: ${context.total_cost:.0f}

=== PRE-CALCULATED EXIT LEVELS ===
Stop Loss (spread value): ${exits.get('stop_loss', 0):.2f}
Warning Level: ${exits.get('warning_level', 0):.2f}
Scale-Out Target: ${exits.get('scale_out_target', 0):.2f}
Full Profit Target: ${exits.get('full_profit_target', 0):.2f}
Underlying Stop: ${exits.get('underlying_stop', 0):.2f}
Underlying Target: ${exits.get('underlying_target', 0):.2f}

Please evaluate this trade following your standard output format."""

    return prompt


# ─── Position Refresh Prompt ─────────────────────────────────────

def build_refresh_prompt(position, assessments: list, current_market_data: dict, strategy_def=None) -> str:
    """
    Build the user message for a position refresh Claude call.

    Includes: original entry snapshot, all prior assessments (so Claude sees its
    own history), current market data, and trade structure details.

    Args:
        position: Position ORM object
        assessments: list of PositionAssessment ORM objects, ordered by version_number asc
        current_market_data: dict with keys: date, underlying_price, iv, spread_mark,
                             sma_alignment (optional sub-dict with sma_8/sma_21/sma_50/alignment)
        strategy_def: optional StrategyDefinition dataclass from strategy_definitions.py
    """
    def _safe_json(raw):
        if raw is None:
            return {}
        if isinstance(raw, dict):
            return raw
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return {}

    strategy_label = strategy_def.label if strategy_def else position.strategy_key
    trade_struct = _safe_json(position.trade_structure)
    entry_sma = _safe_json(position.entry_sma_alignment)
    entry_greeks = _safe_json(position.entry_greeks)
    entry_date_str = position.entry_date.strftime("%m-%d-%Y") if position.entry_date else "N/A"

    lines = [
        f"=== POSITION REFRESH: {position.symbol} — {strategy_label} ===",
        "",
        "=== ORIGINAL ENTRY ===",
        f"Entry Date: {entry_date_str}",
        f"Entry Underlying Price: {position.entry_underlying_price}",
        f"Entry Spread / Option Price: {position.entry_price}",
        f"Entry IV Rank: {position.entry_iv_rank}",
    ]

    if entry_sma:
        lines.append(
            f"Entry SMA Alignment: SMA8={entry_sma.get('sma_8','N/A')} | "
            f"SMA21={entry_sma.get('sma_21','N/A')} | SMA50={entry_sma.get('sma_50','N/A')} | "
            f"Trend={entry_sma.get('alignment', entry_sma.get('ma_alignment','N/A'))}"
        )

    if entry_greeks:
        lines.append(f"Entry Greeks: {json.dumps(entry_greeks)}")

    lines += [
        "",
        "=== TRADE STRUCTURE ===",
        json.dumps(trade_struct, indent=2),
        "",
    ]

    if assessments:
        lines.append("=== PRIOR ASSESSMENTS (your history — most recent last) ===")
        for a in sorted(assessments, key=lambda x: x.version_number):
            created_str = a.created_at.strftime("%m-%d-%Y") if a.created_at else "N/A"
            lines.append(
                f"v{a.version_number} [{a.assessment_type}] {created_str} — "
                f"Verdict: {a.verdict} | Score: {a.score}"
            )
            if a.synopsis:
                lines.append(f"  Synopsis: {a.synopsis}")
            lines.append(f"  Analysis: {a.claude_read}")
            if a.exit_levels:
                el = _safe_json(a.exit_levels)
                lines.append(f"  Exit Levels: {json.dumps(el)}")
        lines.append("")

    current_date = current_market_data.get("date", "N/A")
    underlying = current_market_data.get("underlying_price", "N/A")
    iv = current_market_data.get("iv", "N/A")
    spread_mark = current_market_data.get("spread_mark", "N/A")
    sma = current_market_data.get("sma_alignment", {})

    lines += [
        "=== CURRENT MARKET DATA ===",
        f"Date: {current_date}",
        f"Underlying Price: {underlying}",
        f"Spread / Option Mark: {spread_mark}",
        f"IV (annualized): {iv}",
    ]

    if sma:
        lines.append(
            f"SMA 8: {sma.get('sma_8','N/A')} | SMA 21: {sma.get('sma_21','N/A')} | "
            f"SMA 50: {sma.get('sma_50','N/A')} | Trend: {sma.get('alignment', sma.get('ma_alignment','N/A'))}"
        )

    lines += [
        "",
        "Refresh this position evaluation. Return a single JSON object per the POSITION_REFRESH_SYSTEM schema.",
    ]

    return "\n".join(lines)


# ─── Pre-Screen (rule-based, no AI needed) ────────────────────────

def pre_screen_trade(context: TradeContext) -> list[dict]:
    """
    Run instant rule-based checks BEFORE sending to Claude.
    
    WHY pre-screen: These catch obvious problems immediately, without
    waiting for the API call. The flags are shown to the user in the UI
    before they hit "Evaluate", and they're also included in the prompt
    so Claude can reference them.
    
    Returns a list of {"level": "warn"|"alert", "msg": "..."} dicts.
    """
    flags = []

    if context.rr_ratio < 1.5:
        flags.append({
            "level": "warn",
            "msg": f"R:R is {context.rr_ratio:.2f} — below 1.5 preferred minimum",
        })

    if context.total_cost > context.risk_budget:
        flags.append({
            "level": "warn",
            "msg": f"Total cost (${context.total_cost:.0f}) exceeds risk budget (${context.risk_budget:.0f})",
        })

    if context.expected_move_target and context.direction == "Bullish":
        # For a bull spread, the target should reach the short strike
        # We don't have short_strike directly, but we can parse from spread string
        # For now, flag if target < current_price (clearly wrong for bullish)
        if context.expected_move_target < context.current_price:
            flags.append({
                "level": "alert",
                "msg": f"Bullish thesis but target (${context.expected_move_target:.2f}) is below current price (${context.current_price:.2f})",
            })

    if context.expected_move_target and context.direction == "Bearish":
        if context.expected_move_target > context.current_price:
            flags.append({
                "level": "alert",
                "msg": f"Bearish thesis but target (${context.expected_move_target:.2f}) is above current price (${context.current_price:.2f})",
            })

    if context.prob_of_profit < 0.45:
        flags.append({
            "level": "warn",
            "msg": f"Low probability ({context.prob_of_profit * 100:.0f}%) — consider wider spread or different strikes",
        })

    return flags
