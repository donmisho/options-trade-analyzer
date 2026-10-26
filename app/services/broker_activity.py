"""
Broker activity normalization (OTA-855).

Pure functions, no I/O: they turn Trader API payloads into the columns of the
broker_* tables, work out the fill context numbers, and shape stored rows the
way the Short-DTE Trade Lab dashboard reads them (the thinkorswim statement's
Trades-sheet columns). Keeping them pure keeps them testable without Schwab.
"""

import json
import re
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, Optional

# OCC option symbol: root padded to 6, yymmdd, C|P, strike × 1000 as 8 digits.
OPTION_SYMBOL_RE = re.compile(r"^(?P<root>[A-Z.$/]{1,6}?)\s*(?P<yy>\d{2})(?P<mm>\d{2})(?P<dd>\d{2})(?P<pc>[CP])(?P<strike>\d{8})$")

# Index option roots whose underlying quote lives under a different symbol.
INDEX_ROOTS = {
    "SPXW": "SPX", "SPX": "SPX", "NDXP": "NDX", "NDX": "NDX", "RUTW": "RUT", "RUT": "RUT",
    "XSP": "XSP", "VIXW": "VIX", "VIX": "VIX", "DJX": "DJX", "OEX": "OEX", "XEO": "OEX",
}

MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
SHORT_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

MARKET_TZ = "America/New_York"


def zone(name: str):
    """A tzinfo for an IANA name; zoneinfo first, pytz (bundled with APScheduler) on a Windows box without tzdata."""
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:
        import pytz
        return pytz.timezone(name)


def to_float(value) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_time(text) -> Optional[datetime]:
    """Schwab times: '2026-10-24T14:31:05+0000', '...Z', with or without fractions. Returns aware UTC."""
    if not text:
        return None
    if isinstance(text, datetime):
        return text if text.tzinfo else text.replace(tzinfo=timezone.utc)
    s = str(text).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    m = re.search(r"([+-])(\d{2})(\d{2})$", s)
    if m and ":" not in s[-6:]:
        s = s[:-5] + f"{m.group(1)}{m.group(2)}:{m.group(3)}"
    try:
        moment = datetime.fromisoformat(s)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def parse_date(text) -> Optional[date]:
    moment = parse_time(text)
    return moment.astimezone(zone(MARKET_TZ)).date() if moment else None


def parse_option_symbol(symbol) -> Optional[dict]:
    """'SPY   261024C00580000' → {root, expiration, put_call, strike}."""
    if not symbol:
        return None
    m = OPTION_SYMBOL_RE.match(str(symbol).strip().upper())
    if not m:
        return None
    try:
        expiration = date(2000 + int(m.group("yy")), int(m.group("mm")), int(m.group("dd")))
    except ValueError:
        return None
    return {
        "root": m.group("root"),
        "expiration": expiration,
        "put_call": "CALL" if m.group("pc") == "C" else "PUT",
        "strike": int(m.group("strike")) / 1000.0,
    }


def underlying_of(root_or_symbol: Optional[str]) -> Optional[str]:
    """The quote symbol of an option root: SPXW → SPX, SPY → SPY."""
    if not root_or_symbol:
        return None
    root = str(root_or_symbol).strip().upper().lstrip("$")
    return INDEX_ROOTS.get(root, root)


def fmt_strike(value: Optional[float]) -> str:
    if value is None:
        return ""
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    return text


def _leg_from_instrument(instrument: dict, amount, cost, price, effect) -> dict:
    asset_type = (instrument.get("assetType") or "").upper()
    parsed = parse_option_symbol(instrument.get("symbol")) if asset_type == "OPTION" else None
    strike = to_float(instrument.get("strikePrice"))
    if strike is None and parsed:
        strike = parsed["strike"]
    expiration = parse_date(instrument.get("expirationDate"))
    if expiration is None and parsed:
        expiration = parsed["expiration"]
    put_call = (instrument.get("putCall") or (parsed["put_call"] if parsed else None) or None)
    underlying = instrument.get("underlyingSymbol") or (parsed["root"] if parsed else instrument.get("symbol"))
    return {
        "asset_type": asset_type,
        "symbol": instrument.get("symbol"),
        "description": instrument.get("description"),
        "underlying_symbol": underlying_of(underlying) if asset_type == "OPTION" else (underlying or None),
        "root": parsed["root"] if parsed else None,
        "put_call": put_call.upper() if put_call else None,
        "strike": strike,
        "expiration": expiration.isoformat() if expiration else None,
        "multiplier": to_float(instrument.get("optionPremiumMultiplier")) or (100.0 if asset_type == "OPTION" else 1.0),
        "amount": to_float(amount),
        "cost": to_float(cost),
        "price": to_float(price),
        "position_effect": (effect or "").upper() or None,
    }


def _structure(legs: list) -> str:
    options = [l for l in legs if l["asset_type"] == "OPTION"]
    if not options:
        return "Equity" if legs else "Unknown"
    if len(options) == 1:
        return "Single"
    if len(options) == 2:
        a, b = options
        if a["expiration"] == b["expiration"] and a["put_call"] == b["put_call"]:
            return "Vertical"
        if a["strike"] == b["strike"] and a["put_call"] == b["put_call"]:
            return "Calendar"
        if a["put_call"] == b["put_call"]:
            return "Diagonal"
        return "Combo"
    return "Multi"


def _ordered_legs(legs: list) -> list:
    """Long legs first (the way the statement writes 580/585 for a bought 580 and a sold 585), then by strike."""
    return sorted(legs, key=lambda l: (0 if (l["amount"] or 0) > 0 else 1, l["strike"] or 0))


def _tos_description(side: str, qty: float, structure: str, underlying: str, legs: list, price: Optional[float]) -> str:
    """'BOT +1 VERTICAL SPY 100 24 OCT 26 580/585 CALL @1.20', close to the statement's wording."""
    options = [l for l in legs if l["asset_type"] == "OPTION"]
    verb = "BOT" if side == "Buy" else "SOLD"
    signed = f"{'+' if side == 'Buy' else '-'}{fmt_strike(qty)}"
    if not options:
        return f"{verb} {signed} {underlying} @{price if price is not None else ''}".strip()
    exp = options[0]["expiration"]
    exp_text = ""
    if exp:
        d = date.fromisoformat(exp)
        exp_text = f"{d.day} {MONTHS[d.month - 1]} {d.strftime('%y')}"
    strikes = "/".join(fmt_strike(l["strike"]) for l in _ordered_legs(options))
    kind = (options[0]["put_call"] or "").upper()
    struct = f"{structure.upper()} " if structure not in ("Single", "Unknown") else ""
    mult = int(options[0]["multiplier"] or 100)
    return f"{verb} {signed} {struct}{underlying} {mult} {exp_text} {strikes} {kind} @{fmt_strike(price) if price is not None else ''}".replace("  ", " ").strip()


def normalize_transaction(raw: dict) -> dict:
    """
    One Trader API transaction → the broker_transactions columns.

    transferItems carry the legs (an instrument with amount, cost, price and
    positionEffect) and the fees (CURRENCY items with a feeType). Legs with a
    positive amount were bought; cost is the cash effect, negative when money
    left the account.
    """
    items = raw.get("transferItems") or []
    legs, commissions, fees = [], 0.0, 0.0
    for item in items:
        instrument = item.get("instrument") or {}
        fee_type = item.get("feeType")
        if fee_type or (instrument.get("assetType") or "").upper() == "CURRENCY":
            value = to_float(item.get("cost"))
            if value is None:
                value = to_float(item.get("amount")) or 0.0
            if (fee_type or "").upper() == "COMMISSION":
                commissions += value
            else:
                fees += value
            continue
        legs.append(_leg_from_instrument(instrument, item.get("amount"), item.get("cost"), item.get("price"), item.get("positionEffect")))

    option_legs = [l for l in legs if l["asset_type"] == "OPTION"]
    primary_pool = option_legs or legs
    ordered = _ordered_legs(primary_pool) if primary_pool else []
    primary = ordered[0] if ordered else None
    structure = _structure(legs)
    leg_cost = sum(l["cost"] or 0.0 for l in legs) if legs else None
    quantity = None
    if primary is not None:
        quantity = abs(primary["amount"]) if primary["amount"] is not None else None
    if len(legs) == 1 and primary is not None:
        side = "Buy" if (primary["amount"] or 0) > 0 else "Sell"
    elif leg_cost is not None:
        side = "Buy" if leg_cost < 0 else "Sell"
    else:
        side = None
    price = None
    if len(legs) == 1 and primary is not None and primary["price"] is not None:
        price = abs(primary["price"])
    elif leg_cost is not None and quantity:
        mult = primary["multiplier"] if primary and primary["multiplier"] else 1.0
        price = round(abs(leg_cost) / (quantity * mult), 4)
    effects = {l["position_effect"] for l in legs if l["position_effect"]}
    position_effect = effects.pop() if len(effects) == 1 else ("MIXED" if effects else None)
    moment = parse_time(raw.get("time")) or parse_time(raw.get("tradeDate")) or datetime.now(timezone.utc)
    trade_date = parse_date(raw.get("tradeDate")) or moment.astimezone(zone(MARKET_TZ)).date()
    underlying = primary["underlying_symbol"] if primary else None
    asset_type = "OPTION" if option_legs and len(legs) == len(option_legs) else ("MULTI" if option_legs else (primary["asset_type"] if primary else None))
    description = raw.get("description")
    if not description and primary is not None and side and quantity is not None:
        description = _tos_description(side, quantity, structure, underlying or "", legs, price)
    return {
        "activity_id": int(raw.get("activityId")) if raw.get("activityId") is not None else None,
        "order_id": int(raw["orderId"]) if raw.get("orderId") not in (None, "") else None,
        "position_id": int(raw["positionId"]) if raw.get("positionId") not in (None, "") else None,
        "activity_type": raw.get("activityType"),
        "transaction_type": raw.get("type") or "TRADE",
        "status": raw.get("status"),
        "sub_account": raw.get("subAccount"),
        "time": moment,
        "trade_date": trade_date,
        "settlement_date": parse_date(raw.get("settlementDate")),
        "description": (description or "")[:400] or None,
        "asset_type": asset_type,
        "structure": structure,
        "side": side,
        "position_effect": position_effect,
        "underlying_symbol": underlying,
        "option_symbol": primary["symbol"] if primary and primary["asset_type"] == "OPTION" else None,
        "put_call": primary["put_call"] if primary else None,
        "strike_price": primary["strike"] if primary else None,
        "strikes_text": "/".join(fmt_strike(l["strike"]) for l in ordered if l["asset_type"] == "OPTION") or None,
        "expiration_date": min((date.fromisoformat(l["expiration"]) for l in option_legs if l["expiration"]), default=None),
        "quantity": quantity,
        "price": price,
        "leg_cost": round(leg_cost, 4) if leg_cost is not None else None,
        "commissions": round(commissions, 4),
        "fees": round(fees, 4),
        "net_amount": to_float(raw.get("netAmount")),
        "leg_count": len(legs),
        "legs_json": json.dumps(legs, default=str),
        "raw_json": json.dumps(raw, default=str),
    }


def normalize_order(raw: dict, parent_order_id: Optional[int] = None) -> list[dict]:
    """
    One order payload → rows for it and, flattened, for each child strategy
    (an OCO bracket's stop and target, a trigger's follow-up orders).
    """
    legs = []
    for leg in raw.get("orderLegCollection") or []:
        instrument = leg.get("instrument") or {}
        entry = _leg_from_instrument(instrument, None, None, None, leg.get("positionEffect"))
        entry["instruction"] = (leg.get("instruction") or "").upper() or None
        entry["quantity"] = to_float(leg.get("quantity"))
        entry["amount"] = (entry["quantity"] or 0.0) * (1 if (entry["instruction"] or "").startswith("BUY") else -1)
        legs.append(entry)
    option_legs = [l for l in legs if l["asset_type"] == "OPTION"]
    ordered = _ordered_legs(option_legs or legs) if legs else []
    primary = ordered[0] if ordered else None
    effects = {l["position_effect"] for l in legs if l["position_effect"]}
    order_id = int(raw["orderId"]) if raw.get("orderId") not in (None, "") else None
    row = {
        "order_id": order_id,
        "parent_order_id": parent_order_id,
        "order_strategy_type": raw.get("orderStrategyType"),
        "order_type": raw.get("orderType"),
        "status": raw.get("status"),
        "status_description": (raw.get("statusDescription") or "")[:400] or None,
        "session": raw.get("session"),
        "duration": raw.get("duration"),
        "price": to_float(raw.get("price")),
        "stop_price": to_float(raw.get("stopPrice")),
        "stop_price_link_basis": raw.get("stopPriceLinkBasis"),
        "stop_price_link_type": raw.get("stopPriceLinkType"),
        "stop_price_offset": to_float(raw.get("stopPriceOffset")),
        "stop_type": raw.get("stopType"),
        "entered_time": parse_time(raw.get("enteredTime")),
        "close_time": parse_time(raw.get("closeTime")),
        "quantity": to_float(raw.get("quantity")),
        "filled_quantity": to_float(raw.get("filledQuantity")),
        "remaining_quantity": to_float(raw.get("remainingQuantity")),
        "instruction": primary["instruction"] if primary else None,
        "position_effect": effects.pop() if len(effects) == 1 else ("MIXED" if effects else None),
        "structure": _structure(legs),
        "underlying_symbol": primary["underlying_symbol"] if primary else None,
        "option_symbol": primary["symbol"] if primary and primary["asset_type"] == "OPTION" else None,
        "put_call": primary["put_call"] if primary else None,
        "strike_price": primary["strike"] if primary else None,
        "strikes_text": "/".join(fmt_strike(l["strike"]) for l in ordered if l["asset_type"] == "OPTION") or None,
        "expiration_date": min((date.fromisoformat(l["expiration"]) for l in option_legs if l["expiration"]), default=None),
        "leg_count": len(legs),
        "legs_json": json.dumps(legs, default=str),
        "raw_json": json.dumps(raw, default=str),
    }
    # An OCO wrapper inside a trigger strategy carries no orderId of its own: its
    # children hang off the nearest order that has one.
    rows = [row] if order_id is not None else []
    for child in raw.get("childOrderStrategies") or []:
        rows.extend(normalize_order(child, parent_order_id=order_id if order_id is not None else parent_order_id))
    return rows


# ---------------------------------------------------------------------------
# Fill context math
# ---------------------------------------------------------------------------


def candle_date(candle: dict) -> Optional[date]:
    """A pricehistory candle's day: its epoch-millisecond datetime read in New York time."""
    stamp = candle.get("datetime")
    if stamp is None:
        return None
    try:
        moment = datetime.fromtimestamp(int(stamp) / 1000.0, tz=timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None
    return moment.astimezone(zone(MARKET_TZ)).date()


def wilder_atr(candles: Iterable[dict], period: int = 14, before: Optional[date] = None) -> tuple[Optional[float], Optional[date]]:
    """
    ATR with Wilder's smoothing over daily candles, as thinkorswim's ATR study computes it
    (average type Wilder's). Only candles dated before `before` count, so the value is the
    ATR a trader could read at the open of that day. Needs period + 1 candles.
    Returns (atr, date of the last candle used).
    """
    rows = []
    for c in candles:
        d = candle_date(c)
        if d is None or (before is not None and d >= before):
            continue
        rows.append((d, to_float(c.get("high")), to_float(c.get("low")), to_float(c.get("close"))))
    rows = [r for r in rows if None not in r[1:]]
    rows.sort(key=lambda r: r[0])
    if len(rows) < period + 1:
        return None, None
    true_ranges = []
    for prev, cur in zip(rows, rows[1:]):
        _, high, low, _ = cur
        prev_close = prev[3]
        true_ranges.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    atr = sum(true_ranges[:period]) / period
    for tr in true_ranges[period:]:
        atr = (atr * (period - 1) + tr) / period
    return round(atr, 4), rows[-1][0]


def quote_block(quotes: dict, symbol: Optional[str]) -> dict:
    """The 'quote' node for a symbol in a /quotes answer, tolerant of key spelling."""
    if not symbol or not isinstance(quotes, dict):
        return {}
    node = quotes.get(symbol) or quotes.get(symbol.upper()) or {}
    if not node:
        wanted = symbol.replace(" ", "").upper()
        for key, value in quotes.items():
            if str(key).replace(" ", "").upper() == wanted:
                node = value
                break
    return (node or {}).get("quote") or {}


def fill_context_values(
    fill_time: datetime,
    captured_at: datetime,
    underlying_symbol: Optional[str],
    option_symbol: Optional[str],
    underlying_quote: dict,
    option_quote: dict,
    atr: Optional[float],
    atr_as_of: Optional[date],
    kind: str = "live",
) -> dict:
    """The broker_fill_context columns from the quotes and the ATR."""
    last = to_float(underlying_quote.get("lastPrice"))
    net_change = to_float(underlying_quote.get("netChange"))
    prev_close = to_float(underlying_quote.get("closePrice"))
    if net_change is None and last is not None and prev_close is not None:
        net_change = round(last - prev_close, 4)
    bid = to_float(option_quote.get("bidPrice"))
    ask = to_float(option_quote.get("askPrice"))
    mark = to_float(option_quote.get("mark"))
    spread = round(ask - bid, 4) if bid is not None and ask is not None else None
    mid = (bid + ask) / 2 if bid is not None and ask is not None else None
    lag = int((captured_at - fill_time).total_seconds()) if fill_time else None
    return {
        "kind": kind,
        "captured_at": captured_at,
        "lag_seconds": lag,
        "underlying_symbol": underlying_symbol,
        "underlying_last": last,
        "underlying_net_change": net_change,
        "underlying_prev_close": prev_close,
        "atr14": atr,
        "atr_as_of": atr_as_of,
        "atr_used": round(abs(net_change) / atr, 4) if net_change is not None and atr else None,
        "option_symbol": option_symbol,
        "option_bid": bid,
        "option_ask": ask,
        "option_mark": mark,
        "option_last": to_float(option_quote.get("lastPrice")),
        "spread": spread,
        "spread_pct_mid": round(spread / mid, 4) if spread is not None and mid else None,
        "open_interest": int(option_quote["openInterest"]) if to_float(option_quote.get("openInterest")) is not None else None,
        "option_volume": int(option_quote["totalVolume"]) if to_float(option_quote.get("totalVolume")) is not None else None,
        "raw_json": json.dumps({"underlying": underlying_quote, "option": option_quote}, default=str),
    }


def daily_context_from_candles(candles: list, trade_date: date) -> tuple[dict, Optional[float], Optional[date]]:
    """
    For a fill older than the live capture window: the day's own candle stands in for
    the quote (close − previous close as the net change) and the ATR comes from the
    candles before it. Returns (underlying_quote_like, atr, atr_as_of).
    """
    rows = sorted(((candle_date(c), c) for c in candles if candle_date(c)), key=lambda r: r[0])
    today = next((c for d, c in rows if d == trade_date), None)
    prev = [c for d, c in rows if d < trade_date]
    quote = {}
    if today is not None:
        quote["lastPrice"] = to_float(today.get("close"))
        if prev:
            quote["closePrice"] = to_float(prev[-1].get("close"))
    atr, as_of = wilder_atr(candles, before=trade_date)
    return quote, atr, as_of


# ---------------------------------------------------------------------------
# Market hours and windows
# ---------------------------------------------------------------------------


def in_market_hours(now: Optional[datetime] = None) -> bool:
    """Mon–Fri 09:30–16:45 New York time: the regular session plus the closing prints."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    local = now.astimezone(zone(MARKET_TZ))
    if local.weekday() >= 5:
        return False
    minutes = local.hour * 60 + local.minute
    return 9 * 60 + 30 <= minutes <= 16 * 60 + 45


# ---------------------------------------------------------------------------
# Dashboard rows (the Trades-sheet shape the Short-DTE Trade Lab page reads)
# ---------------------------------------------------------------------------

FILL_COLUMNS = [
    "row", "fill_id", "reference_number", "description", "trade_datetime", "trade_date", "last_balance",
    "contract_amount", "trade_week", "trade_direction", "strike", "contract_count", "trade_misc_fees",
    "trade_commissions_and_fees", "total_fees", "contract_price", "expiration_date", "long_strike", "short_strike",
    "sell_amount", "buy_amount", "profit_loss", "net_sell_amount", "net_buy_amount", "net_profit_loss", "account",
    "type", "position_column_count", "symbol", "structure", "day_of_week", "trade_hour", "trade_year", "trade_month",
    "trade_day", "trade_weekday", "trade_week_start", "position_effect", "option_symbol", "activity_id",
    "atr_used", "atr14", "underlying_net_change", "underlying_last", "option_bid", "option_ask", "spread",
    "spread_pct_mid", "context_kind", "context_captured_at", "context_lag_seconds",
]


def _num(value) -> Optional[float]:
    return float(value) if value is not None else None


def fill_row(txn, ctx, account_label: str, display_tz: str = "America/Chicago") -> dict:
    """
    One broker_transactions row (+ its fill context) as the dashboard's fill row.

    Times are given as wall-clock text in display_tz, the zone the statement exports
    use, so rows from the two sources line up. Money follows the statement's signs:
    contract_amount is the legs' cash effect (negative for a buy), fees are negative,
    net_profit_loss is amount plus fees.
    """
    tz = zone(display_tz)
    when = txn.time.replace(tzinfo=timezone.utc) if txn.time.tzinfo is None else txn.time
    local = when.astimezone(tz)
    day = local.date()
    iso_year, iso_week, _ = day.isocalendar()
    monday = day - timedelta(days=day.weekday())
    amount = _num(txn.leg_cost) or 0.0
    misc = _num(txn.fees) or 0.0
    comm = _num(txn.commissions) or 0.0
    net = round(amount + misc + comm, 2)
    qty = _num(txn.quantity) or 0.0
    is_buy = txn.side == "Buy"
    strikes = (txn.strikes_text or "").split("/") if txn.strikes_text else []
    weekday = day.weekday()
    row = {
        "fill_id": txn.id,
        "reference_number": str(txn.order_id) if txn.order_id is not None else "",
        "description": txn.description or "",
        "trade_datetime": local.strftime("%Y-%m-%d %H:%M:%S"),
        "trade_date": day.isoformat(),
        "last_balance": "",
        "contract_amount": round(amount, 2),
        "trade_week": f"Week {iso_week}",
        "trade_direction": "Call" if (txn.put_call or "").upper() == "CALL" else ("Put" if (txn.put_call or "").upper() == "PUT" else ""),
        "strike": txn.strikes_text or "",
        "contract_count": qty if is_buy else -qty,
        "trade_misc_fees": round(misc, 2),
        "trade_commissions_and_fees": round(comm, 2),
        "total_fees": round(-(misc + comm), 2),
        "contract_price": _num(txn.price),
        "expiration_date": txn.expiration_date.isoformat() if txn.expiration_date else "",
        "long_strike": to_float(strikes[0]) if strikes else "",
        "short_strike": to_float(strikes[1]) if len(strikes) > 1 else "",
        "sell_amount": 0 if is_buy else round(amount, 2),
        "buy_amount": round(-amount, 2) if is_buy else 0,
        "profit_loss": round(amount, 2),
        "net_sell_amount": 0 if is_buy else net,
        "net_buy_amount": -net if is_buy else 0,
        "net_profit_loss": net,
        "account": account_label,
        "type": "Buy" if is_buy else "Sell",
        "position_column_count": qty,
        "symbol": txn.underlying_symbol or "",
        "structure": txn.structure or "Single",
        "day_of_week": f"{weekday + 1}-{SHORT_DAYS[weekday]}",
        "trade_hour": local.strftime("%H:00"),
        "trade_year": day.year,
        "trade_month": MONTH_NAMES[day.month - 1],
        "trade_day": day.isoformat(),
        "trade_weekday": WEEKDAYS[weekday],
        "trade_week_start": monday.isoformat(),
        "position_effect": txn.position_effect or "",
        "option_symbol": txn.option_symbol or "",
        "activity_id": txn.activity_id,
        "atr_used": _num(ctx.atr_used) if ctx else None,
        "atr14": _num(ctx.atr14) if ctx else None,
        "underlying_net_change": _num(ctx.underlying_net_change) if ctx else None,
        "underlying_last": _num(ctx.underlying_last) if ctx else None,
        "option_bid": _num(ctx.option_bid) if ctx else None,
        "option_ask": _num(ctx.option_ask) if ctx else None,
        "spread": _num(ctx.spread) if ctx else None,
        "spread_pct_mid": _num(ctx.spread_pct_mid) if ctx else None,
        "context_kind": ctx.kind if ctx else "",
        "context_captured_at": ctx.captured_at.strftime("%Y-%m-%d %H:%M:%S") if ctx and ctx.captured_at else "",
        "context_lag_seconds": ctx.lag_seconds if ctx else None,
    }
    return row
