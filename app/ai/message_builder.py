"""
Builds the user message for trade evaluation.

WHY this is separate from the system prompt:
  - System prompt = HOW to evaluate (static, cached)
  - User message = WHAT to evaluate (dynamic, changes every call)

This separation enables prompt caching — the system prompt is processed
once and cached for 5 minutes. Only the user message (which is short)
gets processed fresh each time.

The user message uses BUY/SELL language instead of long/short, and
net_cost with a sign instead of separate debit/credit fields.
"""


def build_trade_evaluation_message(
    # Market context
    symbol: str,
    current_price: float,
    sma_8: float,
    sma_21: float,
    sma_50: float,
    ma_alignment: str,
    # Thesis
    direction: str,
    conviction: str,
    price_target: float,
    timeframe_days: int,
    risk_budget: float,
    # Trade details
    strategy_label: str,
    buy_strike: float,
    sell_strike: float,
    option_type: str,
    expiration: str,
    net_cost: float,
    max_profit: float,
    max_loss: float,
    breakeven: float,
    reward_risk_ratio: float,
    prob_of_profit: float,
    composite_score: float,
    is_credit: bool = False,
    # Pre-calculated exit levels (computed client-side or server-side)
    exit_levels: dict = None,
) -> str:
    """
    Build the user message for a trade evaluation request.

    All arguments come from the frontend's trade payload and SMA data.
    Exit levels are computed before calling Claude — we don't ask Claude
    to do math.
    """
    if is_credit:
        cost_display = f"Net Credit: ${abs(net_cost):.2f} (you collect)"
    else:
        cost_display = f"Net Debit: ${abs(net_cost):.2f} (you pay)"

    per_contract_cost = abs(net_cost) * 100
    num_contracts = max(1, int(risk_budget / per_contract_cost)) if per_contract_cost > 0 else 1
    total_cost = per_contract_cost * num_contracts

    msg = f"""TRADE EVALUATION REQUEST

=== MARKET CONTEXT ===
Asset: {symbol}
Current Price: ${current_price:.2f}
SMA 8: ${sma_8:.2f} | SMA 21: ${sma_21:.2f} | SMA 50: ${sma_50:.2f}
MA Alignment: {ma_alignment}

=== TRADER THESIS ===
Direction: {direction}
Conviction: {conviction}
Price Target: ${price_target:.2f}
Timeframe: {timeframe_days} days

=== PROPOSED TRADE ===
Strategy: {strategy_label}
Action: Buy {buy_strike} {option_type} / Sell {sell_strike} {option_type}
Expiration: {expiration}
{cost_display}
Max Profit: ${max_profit:.2f} per share (${max_profit * 100:.0f} per contract)
Max Loss: ${max_loss:.2f} per share (${max_loss * 100:.0f} per contract)
Breakeven: ${breakeven:.2f}
R:R Ratio: {reward_risk_ratio:.2f}
Prob of Profit: {prob_of_profit * 100:.0f}%
Composite Score: {composite_score:.2f}
Risk Budget: ${risk_budget:.0f} | Contracts: {num_contracts} | Total Cost: ${total_cost:.0f}"""

    if exit_levels:
        msg += f"""

=== PRE-CALCULATED EXIT LEVELS ===
Stop Loss (spread value): ${exit_levels.get('stop_loss', exit_levels.get('stopLoss', 0)):.2f}
Warning Level: ${exit_levels.get('warning_level', exit_levels.get('warningLevel', 0)):.2f}
Scale-Out Target: ${exit_levels.get('scale_out_target', exit_levels.get('scaleOutTarget', 0)):.2f}
Full Profit Target: ${exit_levels.get('full_profit_target', exit_levels.get('fullProfitTarget', 0)):.2f}
Underlying Stop: ${exit_levels.get('underlying_stop', exit_levels.get('underlyingStop', 0)):.2f}"""

    return msg
