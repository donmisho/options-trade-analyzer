"""
Vertical Spread Analysis Engine

WHY THIS EXISTS:
This replaces the "Vertical Spreads" sheet from the Excel analyzer.
Given a symbol's options chain, it builds every valid bull call and
bear put spread combination, scores each one using a weighted composite
formula, and returns them ranked best-to-worst.

HOW SCORING WORKS:
Each spread gets a 0-1 score in 5 categories:
  1. Expected Value (EV): (prob × maxWin) - ((1-prob) × maxLoss)
  2. Reward:Risk (R:R): maxProfit / maxLoss
  3. Probability of Profit: estimated from long leg delta (≈ prob of any profit)
  4. Liquidity: combined volume + open interest of both legs
  5. Theta Efficiency: net theta relative to cost

These raw scores are normalized to 0-1, then multiplied by user-
configurable weights (default: EV 35%, R:R 25%, Prob 20%, Liq 15%,
Theta 5%) and summed into a composite score.

The normalization step is critical — without it, a $500 EV and a
3.0 R:R can't be compared. By mapping everything to 0-1 first, the
weights become meaningful percentages.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional
import math


def _normalize_iv(raw_iv):
    """Schwab returns IV as decimal fraction (0.2616 = 26.16%).
    Guard against double-conversion where value is already a percentage."""
    if raw_iv is None:
        return None
    if raw_iv > 2.0:
        return raw_iv / 100.0
    return raw_iv


# ─── Data Structures ─────────────────────────────────────────────

@dataclass
class ScoringWeights:
    """User-configurable weights that must sum to 1.0"""
    expected_value: float = 0.35
    reward_risk: float = 0.25
    probability: float = 0.20
    liquidity: float = 0.15
    theta_efficiency: float = 0.05

    def validate(self):
        total = (self.expected_value + self.reward_risk + 
                 self.probability + self.liquidity + self.theta_efficiency)
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"Weights must sum to 1.0, got {total:.2f}")


@dataclass
class SpreadFilters:
    """Filters applied before scoring — removes invalid/illiquid spreads"""
    min_short_delta: float = 0.15     # Too far OTM = no premium
    max_short_delta: float = 0.45     # Too close to ATM = high risk
    max_spread_width: int = 10        # Max strike distance
    min_open_interest: int = 50       # Per leg — low OI = bad fills
    min_volume: int = 5               # Per leg — needs activity
    min_reward_risk: float = 0.5      # At least 0.5:1 reward:risk
    min_ev_threshold: float = 0.0    # Minimum raw EV; 0 = only positive EV trades
    spread_types: list = field(default_factory=lambda: ["bull_call", "bear_put"])
    min_net_delta: float = 0.0        # 0 = no filter; minimum net delta of the spread
    max_net_theta: float = 0.0        # 0 = no filter; max absolute theta drain per day


@dataclass
class ScoredSpread:
    """A single scored vertical spread"""
    spread_type: str          # "bull_call" or "bear_put"
    long_strike: float
    short_strike: float
    expiration: str
    
    # Option details
    long_bid: float
    long_ask: float
    short_bid: float
    short_ask: float
    option_type: str          # "call" or "put"
    
    # Calculated values
    net_debit: float          # Cost to enter
    max_profit: float         # Width - debit (per contract)
    max_loss: float           # The debit itself
    breakeven: float          # Strike ± debit depending on type
    spread_width: float       # Distance between strikes
    
    # Greeks
    net_delta: float
    net_theta: float
    net_vega: float
    prob_of_profit: float     # Estimated from short delta
    
    # Liquidity
    long_volume: int
    long_oi: int
    short_volume: int
    short_oi: int
    
    # Scores (0-1 normalized)
    ev_raw: float             # Raw expected value in $
    ev_score: float = 0.0
    rr_score: float = 0.0
    prob_score: float = 0.0
    liquidity_score: float = 0.0
    theta_score: float = 0.0
    composite_score: float = 0.0
    
    # Convenience
    reward_risk_ratio: float = 0.0
    required_move_pct: float = 0.0  # % the underlying must move to profit
    iv: Optional[float] = None      # Short leg implied volatility (decimal, e.g. 0.2616 = 26.16%)

    # Score breakdown — populated by score_spreads() with per-metric details
    # Format: { metric_key: { raw, normalized, weight, contribution, norm_min, norm_max } }
    score_breakdown: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


# ─── Engine ──────────────────────────────────────────────────────

class VerticalSpreadEngine:
    """
    Builds and scores all valid vertical spreads from an options chain.
    
    Usage:
        engine = VerticalSpreadEngine(weights, filters)
        results = engine.analyze(chain_data, underlying_price)
    
    chain_data format (list of dicts, as returned by Tradier adapter):
        [{
            "strike": 525.0,
            "option_type": "call",  
            "expiration": "2026-03-21",
            "bid": 8.20,
            "ask": 8.45,
            "delta": 0.55,
            "gamma": 0.032,
            "theta": -0.18,
            "vega": 0.42,
            "volume": 12450,
            "open_interest": 45200,
        }, ...]
    """
    
    def __init__(
        self,
        weights: Optional[ScoringWeights] = None,
        filters: Optional[SpreadFilters] = None,
    ):
        self.weights = weights or ScoringWeights()
        self.weights.validate()
        self.filters = filters or SpreadFilters()
    
    def analyze(
        self,
        contracts: list[dict],
        underlying_price: float,
        max_results: Optional[int] = None,
    ) -> dict:
        """
        Main entry point. Returns ranked spreads.
        
        WHY we group by expiration first: A spread's two legs must
        share the same expiration date. Grouping avoids O(n²) 
        comparisons across different expiries.
        """
        # Group contracts by expiration and type
        by_exp = {}
        for c in contracts:
            key = (c["expiration"], c["option_type"])
            by_exp.setdefault(key, []).append(c)
        
        # Sort each group by strike
        for key in by_exp:
            by_exp[key].sort(key=lambda x: x["strike"])
        
        # Build all valid spreads
        raw_spreads = []
        
        for (exp, opt_type), chain in by_exp.items():
            if opt_type == "call" and "bull_call" in self.filters.spread_types:
                raw_spreads.extend(
                    self._build_bull_calls(chain, exp, underlying_price)
                )
            if opt_type == "put" and "bear_put" in self.filters.spread_types:
                raw_spreads.extend(
                    self._build_bear_puts(chain, exp, underlying_price)
                )
            if opt_type == "put" and "bull_put" in self.filters.spread_types:
                raw_spreads.extend(
                    self._build_bull_puts(chain, exp, underlying_price)
                )
            if opt_type == "call" and "bear_call" in self.filters.spread_types:
                raw_spreads.extend(
                    self._build_bear_calls(chain, exp, underlying_price)
                )

        if not raw_spreads:
            return {
                "spreads": [],
                "total_valid": 0,
                "underlying_price": underlying_price,
            }
        
        # Hard filter: discard spreads below the EV threshold before scoring.
        # Default threshold is 0 (only positive EV); user can raise or lower via system vars.
        raw_spreads = [s for s in raw_spreads if s.ev_raw >= self.filters.min_ev_threshold]

        if not raw_spreads:
            return {
                "spreads": [],
                "total_valid": 0,
                "underlying_price": underlying_price,
            }

        # Score and rank
        scored = self._score_all(raw_spreads)
        scored.sort(key=lambda s: s.composite_score, reverse=True)
        
        if max_results:
            scored = scored[:max_results]
        
        return {
            "spreads": [s.to_dict() for s in scored],
            "total_valid": len(scored),
            "underlying_price": underlying_price,
        }
    
    # ─── Spread Builders ──────────────────────────────────────
    
    def _build_bull_calls(
        self, calls: list[dict], exp: str, price: float
    ) -> list[ScoredSpread]:
        """
        Bull Call Spread: BUY lower strike, SELL higher strike (both calls).
        
        WHY: Profits when stock goes UP. You buy a call and offset the
        cost by selling a higher call. Max profit = width - debit.
        Max loss = the debit paid.
        """
        spreads = []
        for i, long_leg in enumerate(calls):
            for short_leg in calls[i + 1:]:
                spread = self._try_build_spread(
                    "bull_call", long_leg, short_leg, exp, price
                )
                if spread:
                    spreads.append(spread)
        return spreads
    
    def _build_bear_puts(
        self, puts: list[dict], exp: str, price: float
    ) -> list[ScoredSpread]:
        """
        Bear Put Spread: BUY higher strike, SELL lower strike (both puts).
        
        WHY: Profits when stock goes DOWN. You buy a put and offset the
        cost by selling a lower put. Max profit = width - debit.
        Max loss = the debit paid.
        """
        spreads = []
        for i, long_leg in enumerate(puts):
            for j in range(i):
                short_leg = puts[j]
                spread = self._try_build_spread(
                    "bear_put", long_leg, short_leg, exp, price
                )
                if spread:
                    spreads.append(spread)
        return spreads
    
    def _build_bull_puts(
        self, puts: list[dict], exp: str, price: float
    ) -> list[ScoredSpread]:
        """
        Bull Put Spread: SELL higher strike put, BUY lower strike put (both puts).

        WHY: Profits when stock stays ABOVE the short put strike. You collect
        a credit upfront and keep it if the stock doesn't fall too far.
        Max profit = credit received. Max loss = width - credit.
        """
        spreads = []
        for i, short_leg in enumerate(puts):  # higher index = higher strike put
            for j in range(i):
                long_leg = puts[j]  # lower strike put (protection)
                spread = self._try_build_credit_spread(
                    "bull_put", long_leg, short_leg, exp, price
                )
                if spread:
                    spreads.append(spread)
        return spreads

    def _build_bear_calls(
        self, calls: list[dict], exp: str, price: float
    ) -> list[ScoredSpread]:
        """
        Bear Call Spread: SELL lower strike call, BUY higher strike call (both calls).

        WHY: Profits when stock stays BELOW the short call strike. You collect
        a credit upfront and keep it if the stock doesn't rise too far.
        Max profit = credit received. Max loss = width - credit.
        """
        spreads = []
        for i, short_leg in enumerate(calls):  # lower index = lower strike call (income leg)
            for long_leg in calls[i + 1:]:     # higher strike call (protection)
                spread = self._try_build_credit_spread(
                    "bear_call", long_leg, short_leg, exp, price
                )
                if spread:
                    spreads.append(spread)
        return spreads

    def _try_build_spread(
        self,
        spread_type: str,
        long_leg: dict,
        short_leg: dict,
        exp: str,
        price: float,
    ) -> Optional[ScoredSpread]:
        """
        Attempt to build a spread from two legs. Returns None if it
        fails any filter.
        
        WHY we use mid-price for debit calculation: The bid-ask spread
        means the "true" price is somewhere in the middle. Using the
        ask for the buy and bid for the sell gives a conservative
        (worst-case) estimate. Using mid gives a realistic estimate.
        In practice, limit orders should fill near mid.
        """
        width = abs(long_leg["strike"] - short_leg["strike"])
        
        # Filter: spread width
        if width > self.filters.max_spread_width:
            return None
        if width <= 0:
            return None
        
        # Filter: short leg delta range
        short_delta = abs(short_leg.get("delta", 0) or 0)
        if short_delta < self.filters.min_short_delta:
            return None
        if short_delta > self.filters.max_short_delta:
            return None
        
        # Filter: liquidity
        for leg in [long_leg, short_leg]:
            if (leg.get("volume", 0) or 0) < self.filters.min_volume:
                return None
            if (leg.get("open_interest", 0) or 0) < self.filters.min_open_interest:
                return None
        
        # Calculate debit (cost to enter)
        # WHY mid-price: realistic fill expectation
        long_mid = ((long_leg.get("bid", 0) or 0) + (long_leg.get("ask", 0) or 0)) / 2
        short_mid = ((short_leg.get("bid", 0) or 0) + (short_leg.get("ask", 0) or 0)) / 2
        
        net_debit = long_mid - short_mid  # Buy long, sell short
        
        if net_debit <= 0:
            return None  # Credit spreads are a different strategy
        
        # Max profit / loss (per-contract, multiply by 100 for dollar value)
        max_profit = width - net_debit
        max_loss = net_debit
        
        if max_profit <= 0:
            return None
        
        # Reward:Risk
        rr = max_profit / max_loss if max_loss > 0 else 0
        if rr < self.filters.min_reward_risk:
            return None
        
        # Breakeven
        if spread_type == "bull_call":
            breakeven = long_leg["strike"] + net_debit
        else:  # bear_put
            breakeven = long_leg["strike"] - net_debit
        
# Probability of Profit ≈ |long leg delta|
        #
        # WHY long delta instead of (1 - short delta)?
        # The old formula (1 - short_delta) measured the probability of
        # avoiding MAX LOSS — not the probability of ANY profit. For OTM
        # spreads this inflated probability by 30-50+ percentage points.
        #
        # Example: GLD bear put 460/450 with GLD at $483
        #   Old: short leg (450 put) delta=0.18 → 1-0.18 = 82% (WRONG)
        #   New: long leg (460 put) delta=0.30 → 30% (CORRECT)
        #   Reality: GLD must drop 5.4% to breakeven — 82% was absurd.
        #
        # The long leg's strike is near the breakeven price, so its delta
        # approximates the probability of profit. This works identically
        # for bull call and bear put spreads — no conditional logic needed.
        #
        # Known limitation: delta reflects probability of expiring ITM at
        # the strike, not at breakeven (which is slightly worse by the
        # debit paid). True prob of profit is slightly lower than long
        # delta, typically by 3-8 percentage points. Still far more
        # accurate than the old formula.
        long_delta_val = abs(long_leg.get("delta", 0) or 0)
        prob_of_profit = long_delta_val
        
        # Expected Value
        ev = (prob_of_profit * max_profit) - ((1 - prob_of_profit) * max_loss)
        
        # Net Greeks
        long_delta = long_leg.get("delta", 0) or 0
        short_delta_raw = short_leg.get("delta", 0) or 0
        net_delta = long_delta - short_delta_raw
        
        long_theta = long_leg.get("theta", 0) or 0
        short_theta = short_leg.get("theta", 0) or 0
        net_theta = long_theta - short_theta  # Long theta is negative, short is positive for us

        # Net greeks filters (0 = no filter)
        if self.filters.min_net_delta > 0 and net_delta < self.filters.min_net_delta:
            return None
        if self.filters.max_net_theta > 0 and abs(net_theta) > self.filters.max_net_theta:
            return None

        long_vega = long_leg.get("vega", 0) or 0
        short_vega = short_leg.get("vega", 0) or 0
        net_vega = long_vega - short_vega

        # Required move %
        if spread_type == "bull_call":
            required_move = ((breakeven - price) / price) * 100
        else:
            required_move = ((price - breakeven) / price) * 100
        
        short_iv_raw = short_leg.get("implied_volatility", 0) or short_leg.get("iv", 0) or 0
        short_iv = _normalize_iv(short_iv_raw)

        return ScoredSpread(
            spread_type=spread_type,
            long_strike=long_leg["strike"],
            short_strike=short_leg["strike"],
            expiration=exp,
            long_bid=long_leg.get("bid", 0) or 0,
            long_ask=long_leg.get("ask", 0) or 0,
            short_bid=short_leg.get("bid", 0) or 0,
            short_ask=short_leg.get("ask", 0) or 0,
            option_type=long_leg["option_type"],
            net_debit=round(net_debit, 2),
            max_profit=round(max_profit, 2),
            max_loss=round(max_loss, 2),
            breakeven=round(breakeven, 2),
            spread_width=width,
            net_delta=round(net_delta, 4),
            net_theta=round(net_theta, 4),
            net_vega=round(net_vega, 4),
            prob_of_profit=round(prob_of_profit, 4),
            long_volume=long_leg.get("volume", 0) or 0,
            long_oi=long_leg.get("open_interest", 0) or 0,
            short_volume=short_leg.get("volume", 0) or 0,
            short_oi=short_leg.get("open_interest", 0) or 0,
            ev_raw=round(ev, 2),
            reward_risk_ratio=round(rr, 2),
            required_move_pct=round(required_move, 2),
            iv=round(short_iv, 4) if short_iv is not None else None,
        )

    def _try_build_credit_spread(
        self,
        spread_type: str,
        long_leg: dict,
        short_leg: dict,
        exp: str,
        price: float,
    ) -> Optional[ScoredSpread]:
        """
        Build a credit spread (bull put or bear call).

        WHY SEPARATE FROM _try_build_spread:
        Credit spreads have inverted economics vs. debit spreads:
        - Max profit = credit received (not width - debit)
        - Max loss = width - credit (not the debit itself)
        - Probability: 1 - |short_delta| (short leg expiring OTM)
        - net_debit stored as negative to signal it's a credit
        """
        width = abs(long_leg["strike"] - short_leg["strike"])
        if width > self.filters.max_spread_width or width <= 0:
            return None

        # Short delta filter — same OTM range as debit spreads
        short_delta = abs(short_leg.get("delta", 0) or 0)
        if short_delta < self.filters.min_short_delta:
            return None
        if short_delta > self.filters.max_short_delta:
            return None

        # Liquidity filter
        for leg in [long_leg, short_leg]:
            if (leg.get("volume", 0) or 0) < self.filters.min_volume:
                return None
            if (leg.get("open_interest", 0) or 0) < self.filters.min_open_interest:
                return None

        long_mid = ((long_leg.get("bid", 0) or 0) + (long_leg.get("ask", 0) or 0)) / 2
        short_mid = ((short_leg.get("bid", 0) or 0) + (short_leg.get("ask", 0) or 0)) / 2

        net_credit = short_mid - long_mid
        if net_credit <= 0:
            return None

        max_profit = net_credit
        max_loss = width - net_credit
        if max_loss <= 0:
            return None

        rr = max_profit / max_loss
        if rr < self.filters.min_reward_risk:
            return None

        # Breakeven
        if spread_type == "bull_put":
            breakeven = short_leg["strike"] - net_credit
        else:  # bear_call
            breakeven = short_leg["strike"] + net_credit

        # Probability: short leg expires OTM
        prob_of_profit = 1.0 - abs(short_leg.get("delta", 0) or 0)

        # Expected Value
        ev = (prob_of_profit * max_profit) - ((1 - prob_of_profit) * max_loss)

        # Net Greeks
        long_delta = long_leg.get("delta", 0) or 0
        short_delta_raw = short_leg.get("delta", 0) or 0
        net_delta = long_delta - short_delta_raw
        long_theta = long_leg.get("theta", 0) or 0
        short_theta = short_leg.get("theta", 0) or 0
        net_theta = long_theta - short_theta

        # Net greeks filters (0 = no filter)
        if self.filters.min_net_delta > 0 and net_delta < self.filters.min_net_delta:
            return None
        if self.filters.max_net_theta > 0 and abs(net_theta) > self.filters.max_net_theta:
            return None

        long_vega = long_leg.get("vega", 0) or 0
        short_vega = short_leg.get("vega", 0) or 0
        net_vega = long_vega - short_vega

        # Buffer % — positive means stock has room to move against us before we lose
        if spread_type == "bull_put":
            required_move = ((price - breakeven) / price) * 100
        else:
            required_move = ((breakeven - price) / price) * 100

        short_iv_raw = short_leg.get("implied_volatility", 0) or short_leg.get("iv", 0) or 0
        short_iv = _normalize_iv(short_iv_raw)

        return ScoredSpread(
            spread_type=spread_type,
            long_strike=long_leg["strike"],
            short_strike=short_leg["strike"],
            expiration=exp,
            long_bid=long_leg.get("bid", 0) or 0,
            long_ask=long_leg.get("ask", 0) or 0,
            short_bid=short_leg.get("bid", 0) or 0,
            short_ask=short_leg.get("ask", 0) or 0,
            option_type=long_leg["option_type"],
            net_debit=round(-net_credit, 2),  # negative = credit received
            max_profit=round(max_profit, 2),
            max_loss=round(max_loss, 2),
            breakeven=round(breakeven, 2),
            spread_width=width,
            net_delta=round(net_delta, 4),
            net_theta=round(net_theta, 4),
            net_vega=round(net_vega, 4),
            prob_of_profit=round(prob_of_profit, 4),
            long_volume=long_leg.get("volume", 0) or 0,
            long_oi=long_leg.get("open_interest", 0) or 0,
            short_volume=short_leg.get("volume", 0) or 0,
            short_oi=short_leg.get("open_interest", 0) or 0,
            ev_raw=round(ev, 2),
            reward_risk_ratio=round(rr, 2),
            required_move_pct=round(required_move, 2),
            iv=round(short_iv, 4) if short_iv is not None else None,
        )

    # ─── Scoring ──────────────────────────────────────────────
    
    def _score_all(self, spreads: list[ScoredSpread]) -> list[ScoredSpread]:
        """
        Normalize each metric to 0-1 across the population, then apply weights.
        
        WHY NORMALIZATION MATTERS:
        Raw EV might range from -$200 to +$500, while R:R ranges from 0.5 to 4.0.
        Without normalization, EV would dominate the score just because its numbers
        are bigger. Mapping everything to 0-1 first makes the weights meaningful:
        "35% EV" actually means 35% of the score comes from EV.
        
        WHY MIN-MAX SCALING:
        score = (value - min) / (max - min)
        Simple, interpretable, and the right choice when you want the best spread
        in THIS batch to score 1.0. If you want absolute scoring across batches,
        you'd use fixed ranges instead.
        """
        if len(spreads) <= 1:
            if spreads:
                s = spreads[0]
                s.ev_score = s.rr_score = s.prob_score = s.liquidity_score = s.theta_score = 1.0
                s.composite_score = 100.0
                w = self.weights
                liq_raw = s.long_volume + s.short_volume + s.long_oi + s.short_oi
                th_raw  = s.net_theta / s.max_loss if s.max_loss > 0 else 0
                s.score_breakdown = {
                    "expected_value":   {"raw": s.ev_raw, "normalized": 1.0, "weight": w.expected_value, "contribution": round(w.expected_value * 100, 2), "norm_min": s.ev_raw, "norm_max": s.ev_raw, "formula": "(prob × maxProfit) − ((1−prob) × maxLoss)"},
                    "reward_risk":      {"raw": s.reward_risk_ratio, "normalized": 1.0, "weight": w.reward_risk, "contribution": round(w.reward_risk * 100, 2), "norm_min": s.reward_risk_ratio, "norm_max": s.reward_risk_ratio, "formula": "maxProfit / maxLoss"},
                    "probability":      {"raw": s.prob_of_profit, "normalized": 1.0, "weight": w.probability, "contribution": round(w.probability * 100, 2), "norm_min": s.prob_of_profit, "norm_max": s.prob_of_profit, "formula": "≈ short leg delta"},
                    "liquidity":        {"raw": liq_raw, "normalized": 1.0, "weight": w.liquidity, "contribution": round(w.liquidity * 100, 2), "norm_min": liq_raw, "norm_max": liq_raw, "formula": "longVol + shortVol + longOI + shortOI"},
                    "theta_efficiency": {"raw": th_raw, "normalized": 1.0, "weight": w.theta_efficiency, "contribution": round(w.theta_efficiency * 100, 2), "norm_min": th_raw, "norm_max": th_raw, "formula": "net_theta / max_loss (higher = better)"},
                }
            return spreads
        
        # Extract raw values for normalization
        evs = [s.ev_raw for s in spreads]
        rrs = [s.reward_risk_ratio for s in spreads]
        probs = [s.prob_of_profit for s in spreads]
        liqs = [
            (s.long_volume + s.short_volume + s.long_oi + s.short_oi)
            for s in spreads
        ]
        thetas = [
            # Theta efficiency: net_theta / max_loss
            # Debit spreads have negative net_theta (cost). Credit spreads have
            # positive net_theta (income). Higher is better — credit spreads
            # that collect more theta per dollar at risk score higher.
            s.net_theta / s.max_loss if s.max_loss > 0 else 0
            for s in spreads
        ]
        
        def normalize(values: list[float], higher_is_better: bool = True) -> list[float]:
            """Min-max normalize to 0-1 range"""
            mn, mx = min(values), max(values)
            rng = mx - mn
            if rng == 0:
                return [0.5] * len(values)
            if higher_is_better:
                return [(v - mn) / rng for v in values]
            else:
                return [(mx - v) / rng for v in values]  # Invert
        
        ev_scores = normalize(evs, higher_is_better=True)
        rr_scores = normalize(rrs, higher_is_better=True)
        prob_scores = normalize(probs, higher_is_better=True)
        liq_scores = normalize(liqs, higher_is_better=True)
        theta_scores = normalize(thetas, higher_is_better=True)

        # Capture normalization bounds for score_breakdown
        ev_min, ev_max     = min(evs), max(evs)
        rr_min, rr_max     = min(rrs), max(rrs)
        prob_min, prob_max = min(probs), max(probs)
        liq_min, liq_max   = min(liqs), max(liqs)
        th_min, th_max     = min(thetas), max(thetas)

        w = self.weights
        for i, s in enumerate(spreads):
            s.ev_score        = round(ev_scores[i], 4)
            s.rr_score        = round(rr_scores[i], 4)
            s.prob_score      = round(prob_scores[i], 4)
            s.liquidity_score = round(liq_scores[i], 4)
            s.theta_score     = round(theta_scores[i], 4)
            s.composite_score = round(
                (s.ev_score * w.expected_value +
                s.rr_score * w.reward_risk +
                s.prob_score * w.probability +
                s.liquidity_score * w.liquidity +
                s.theta_score * w.theta_efficiency) * 100,
                2
            )
            liq_raw = liqs[i]
            th_raw  = thetas[i]
            s.score_breakdown = {
                "expected_value": {
                    "raw": round(s.ev_raw, 4), "normalized": s.ev_score,
                    "weight": w.expected_value, "contribution": round(s.ev_score * w.expected_value * 100, 2),
                    "norm_min": round(ev_min, 4), "norm_max": round(ev_max, 4),
                    "formula": "(prob × maxProfit) − ((1−prob) × maxLoss)",
                },
                "reward_risk": {
                    "raw": round(s.reward_risk_ratio, 4), "normalized": s.rr_score,
                    "weight": w.reward_risk, "contribution": round(s.rr_score * w.reward_risk * 100, 2),
                    "norm_min": round(rr_min, 4), "norm_max": round(rr_max, 4),
                    "formula": "maxProfit / maxLoss",
                },
                "probability": {
                    "raw": round(s.prob_of_profit, 4), "normalized": s.prob_score,
                    "weight": w.probability, "contribution": round(s.prob_score * w.probability * 100, 2),
                    "norm_min": round(prob_min, 4), "norm_max": round(prob_max, 4),
                    "formula": "≈ short leg delta",
                },
                "liquidity": {
                    "raw": liq_raw, "normalized": s.liquidity_score,
                    "weight": w.liquidity, "contribution": round(s.liquidity_score * w.liquidity * 100, 2),
                    "norm_min": liq_min, "norm_max": liq_max,
                    "formula": "longVol + shortVol + longOI + shortOI",
                },
                "theta_efficiency": {
                    "raw": round(th_raw, 6), "normalized": s.theta_score,
                    "weight": w.theta_efficiency, "contribution": round(s.theta_score * w.theta_efficiency * 100, 2),
                    "norm_min": round(th_min, 6), "norm_max": round(th_max, 6),
                    "formula": "net_theta / max_loss (higher = better)",
                },
            }

        return spreads
