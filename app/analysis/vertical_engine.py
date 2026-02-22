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
  3. Probability of Profit: estimated from short leg delta
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
    spread_types: list = field(default_factory=lambda: ["bull_call", "bear_put"])


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
        
        # Probability of profit (approximation from short delta)
        # WHY: Delta ≈ probability of expiring ITM. For a bull call spread,
        # probability of profit ≈ delta of the short (sold) call, because
        # profit happens when the stock is above the long strike + debit.
        # This is a rough estimate — true probability requires a pricing model.
        prob = abs(short_leg.get("delta", 0) or 0)
        
        # For bear put: prob = abs(short put delta)
        # Both cases: we want the probability the short leg expires worthless
        # ... actually for bull call, prob_of_profit ≈ 1 - short_delta
        # For bear put, prob_of_profit ≈ 1 - abs(short_delta)
        # The short delta is already the ITM probability of the short leg
        prob_of_profit = 1 - prob  # Probability short expires OTM = we profit
        
        # Expected Value
        ev = (prob_of_profit * max_profit) - ((1 - prob_of_profit) * max_loss)
        
        # Net Greeks
        long_delta = long_leg.get("delta", 0) or 0
        short_delta_raw = short_leg.get("delta", 0) or 0
        net_delta = long_delta - short_delta_raw
        
        long_theta = long_leg.get("theta", 0) or 0
        short_theta = short_leg.get("theta", 0) or 0
        net_theta = long_theta - short_theta  # Long theta is negative, short is positive for us
        
        long_vega = long_leg.get("vega", 0) or 0
        short_vega = short_leg.get("vega", 0) or 0
        net_vega = long_vega - short_vega
        
        # Required move %
        if spread_type == "bull_call":
            required_move = ((breakeven - price) / price) * 100
        else:
            required_move = ((price - breakeven) / price) * 100
        
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
                spreads[0].ev_score = 1.0
                spreads[0].rr_score = 1.0
                spreads[0].prob_score = 1.0
                spreads[0].liquidity_score = 1.0
                spreads[0].theta_score = 1.0
                spreads[0].composite_score = 1.0
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
            # Theta efficiency: net_theta / net_debit (less negative = better)
            # A spread with -0.01 theta on $2 debit is better than -0.05 on $2
            abs(s.net_theta / s.net_debit) if s.net_debit > 0 else 0
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
        # For theta: lower absolute ratio = better (less decay per dollar)
        theta_scores = normalize(thetas, higher_is_better=False)
        
        w = self.weights
        for i, s in enumerate(spreads):
            s.ev_score = round(ev_scores[i], 4)
            s.rr_score = round(rr_scores[i], 4)
            s.prob_score = round(prob_scores[i], 4)
            s.liquidity_score = round(liq_scores[i], 4)
            s.theta_score = round(theta_scores[i], 4)
            s.composite_score = round(
                s.ev_score * w.expected_value +
                s.rr_score * w.reward_risk +
                s.prob_score * w.probability +
                s.liquidity_score * w.liquidity +
                s.theta_score * w.theta_efficiency,
                4
            )
        
        return spreads
