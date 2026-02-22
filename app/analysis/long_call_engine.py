"""
Long Call Analysis Engine

WHY THIS EXISTS:
This replaces the "Naked Calls" sheet from the Excel analyzer.
Given an options chain, it evaluates every call contract as a
standalone long call position and scores it for:

  1. Delta Alignment (30%): Does the option's delta match a good
     directional bet? Sweet spot is 0.30-0.60 — too low means 
     unlikely to profit, too high means overpaying for directional
     exposure you could get cheaper with stock.

  2. Theta Efficiency (25%): How many days of runway do you have
     before time decay eats your premium? Computed as:
     runway_days = premium / abs(daily_theta)
     More days = more time for your thesis to play out.

  3. IV Value (20%): Is implied volatility low relative to what
     you'd expect? Buying calls when IV is elevated means you're
     overpaying. We use IV percentile if available, otherwise
     compare IV to a reasonable baseline.

  4. Reward:Risk (15%): Theoretical upside relative to premium paid.
     Estimated as: (delta × underlying_price × expected_move_pct) / premium
     This tells you how much directional profit you'd capture per
     dollar at risk.

  5. Liquidity (10%): Volume + OI. Can you get filled at a fair price?
"""

from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class LongCallWeights:
    """Weights for long call scoring — must sum to 1.0"""
    delta_alignment: float = 0.30
    theta_efficiency: float = 0.25
    iv_value: float = 0.20
    reward_risk: float = 0.15
    liquidity: float = 0.10

    def validate(self):
        total = sum([
            self.delta_alignment, self.theta_efficiency,
            self.iv_value, self.reward_risk, self.liquidity
        ])
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"Weights must sum to 1.0, got {total:.2f}")


@dataclass
class LongCallFilters:
    """Filters applied before scoring"""
    min_delta: float = 0.25          # Below this = lottery ticket
    max_delta: float = 0.65          # Above this = just buy stock
    max_premium: float = 1500.0      # Per contract in dollars (×100)
    min_open_interest: int = 50
    min_volume: int = 5
    min_days_to_exp: int = 7         # Don't buy weeklies
    max_days_to_exp: int = 90        # Don't go too far out
    max_bid_ask_spread_pct: float = 0.15  # 15% max spread vs mid


@dataclass
class ScoredLongCall:
    """A single scored long call candidate"""
    strike: float
    expiration: str
    days_to_exp: int
    
    # Option details
    bid: float
    ask: float
    mid_price: float
    premium_dollars: float     # mid × 100
    
    # Greeks
    delta: float
    gamma: float
    theta: float
    vega: float
    iv: float                  # Implied volatility %
    
    # Liquidity
    volume: int
    open_interest: int
    bid_ask_spread_pct: float  # (ask-bid)/mid as %
    
    # Calculated values
    breakeven: float           # strike + premium
    breakeven_distance_pct: float  # How far underlying must move
    theta_per_day_dollars: float   # Daily theta decay in $
    theta_runway_days: float       # Days until theta eats premium
    
    # Scores (0-1 normalized)
    delta_score: float = 0.0
    theta_score: float = 0.0
    iv_score: float = 0.0
    rr_score: float = 0.0
    liquidity_score: float = 0.0
    composite_score: float = 0.0
    
    def to_dict(self):
        return asdict(self)


class LongCallEngine:
    """
    Scores and ranks long call candidates from an options chain.
    
    Usage:
        engine = LongCallEngine(weights, filters)
        results = engine.analyze(chain_data, underlying_price)
    """
    
    def __init__(
        self,
        weights: Optional[LongCallWeights] = None,
        filters: Optional[LongCallFilters] = None,
    ):
        self.weights = weights or LongCallWeights()
        self.weights.validate()
        self.filters = filters or LongCallFilters()
    
    def analyze(
        self,
        contracts: list[dict],
        underlying_price: float,
        max_results: Optional[int] = None,
    ) -> dict:
        """Analyze all call contracts and return ranked results."""
        
        # Filter to calls only
        calls = [c for c in contracts if c.get("option_type") == "call"]
        
        # Build scored candidates
        candidates = []
        for c in calls:
            scored = self._evaluate_call(c, underlying_price)
            if scored:
                candidates.append(scored)
        
        if not candidates:
            return {
                "calls": [],
                "total_valid": 0,
                "underlying_price": underlying_price,
            }
        
        # Score and rank
        scored = self._score_all(candidates)
        scored.sort(key=lambda s: s.composite_score, reverse=True)
        
        if max_results:
            scored = scored[:max_results]
        
        return {
            "calls": [s.to_dict() for s in scored],
            "total_valid": len(scored),
            "underlying_price": underlying_price,
        }
    
    def _evaluate_call(
        self, contract: dict, price: float
    ) -> Optional[ScoredLongCall]:
        """Build a ScoredLongCall from a raw contract, applying filters."""
        
        delta = abs(contract.get("delta", 0) or 0)
        bid = contract.get("bid", 0) or 0
        ask = contract.get("ask", 0) or 0
        volume = contract.get("volume", 0) or 0
        oi = contract.get("open_interest", 0) or 0
        theta = contract.get("theta", 0) or 0
        gamma = contract.get("gamma", 0) or 0
        vega = contract.get("vega", 0) or 0
        iv = contract.get("implied_volatility", 0) or contract.get("iv", 0) or 0
        strike = contract["strike"]
        exp = contract["expiration"]
        
        # Calculate DTE from expiration string
        from datetime import datetime, date
        try:
            exp_date = datetime.strptime(exp, "%Y-%m-%d").date()
            dte = (exp_date - date.today()).days
        except (ValueError, TypeError):
            dte = 30  # Fallback
        
        # ── Filters ──
        if delta < self.filters.min_delta or delta > self.filters.max_delta:
            return None
        if volume < self.filters.min_volume:
            return None
        if oi < self.filters.min_open_interest:
            return None
        if dte < self.filters.min_days_to_exp or dte > self.filters.max_days_to_exp:
            return None
        
        mid = (bid + ask) / 2 if (bid + ask) > 0 else 0
        if mid <= 0:
            return None
        
        premium = mid * 100  # Dollar cost per contract
        if premium > self.filters.max_premium:
            return None
        
        # Bid-ask spread filter
        ba_spread_pct = (ask - bid) / mid if mid > 0 else 999
        if ba_spread_pct > self.filters.max_bid_ask_spread_pct:
            return None
        
        # ── Calculations ──
        breakeven = strike + mid
        be_distance = ((breakeven - price) / price) * 100
        
        # Theta runway: how many days until theta alone eats the premium
        # WHY: If theta = -$0.15/day and premium = $3.00, runway = 20 days
        # You need your thesis to play out before theta eats your position
        theta_per_day = abs(theta) * 100  # Daily $ decay per contract
        theta_runway = premium / theta_per_day if theta_per_day > 0 else 999
        
        return ScoredLongCall(
            strike=strike,
            expiration=exp,
            days_to_exp=dte,
            bid=bid,
            ask=ask,
            mid_price=round(mid, 2),
            premium_dollars=round(premium, 2),
            delta=round(delta, 4),
            gamma=round(gamma, 4),
            theta=round(theta, 4),
            vega=round(vega, 4),
            iv=round(iv * 100 if iv < 1 else iv, 2),  # Normalize to %
            volume=volume,
            open_interest=oi,
            bid_ask_spread_pct=round(ba_spread_pct * 100, 2),
            breakeven=round(breakeven, 2),
            breakeven_distance_pct=round(be_distance, 2),
            theta_per_day_dollars=round(theta_per_day, 2),
            theta_runway_days=round(theta_runway, 1),
        )
    
    def _score_all(
        self, candidates: list[ScoredLongCall]
    ) -> list[ScoredLongCall]:
        """Normalize and apply weighted scoring."""
        
        if len(candidates) <= 1:
            if candidates:
                for attr in ["delta_score", "theta_score", "iv_score",
                             "rr_score", "liquidity_score", "composite_score"]:
                    setattr(candidates[0], attr, 1.0)
            return candidates
        
        def normalize(values, higher_is_better=True):
            mn, mx = min(values), max(values)
            rng = mx - mn
            if rng == 0:
                return [0.5] * len(values)
            if higher_is_better:
                return [(v - mn) / rng for v in values]
            return [(mx - v) / rng for v in values]
        
        # Delta alignment: score peaks at 0.45 (sweet spot), drops off either side
        # WHY 0.45: It's the Goldilocks zone — enough directional exposure
        # to profit meaningfully, but not so much you're overpaying
        delta_scores = []
        for c in candidates:
            # Distance from ideal delta (0.45), normalized
            distance = abs(c.delta - 0.45) / 0.45
            delta_scores.append(max(0, 1 - distance))
        
        # Theta efficiency: more runway = better
        runway_scores = normalize(
            [c.theta_runway_days for c in candidates],
            higher_is_better=True
        )
        
        # IV: lower = better (cheaper options)
        iv_scores = normalize(
            [c.iv for c in candidates],
            higher_is_better=False  # Lower IV = better value
        )
        
        # Reward:Risk approximation: delta × price / premium
        # WHY: This estimates how much you'd profit from a 1% move per $ at risk
        rr_values = [
            (c.delta * 100) / c.premium_dollars if c.premium_dollars > 0 else 0
            for c in candidates
        ]
        rr_scores = normalize(rr_values, higher_is_better=True)
        
        # Liquidity
        liq_scores = normalize(
            [c.volume + c.open_interest for c in candidates],
            higher_is_better=True
        )
        
        w = self.weights
        for i, c in enumerate(candidates):
            c.delta_score = round(delta_scores[i], 4)
            c.theta_score = round(runway_scores[i], 4)
            c.iv_score = round(iv_scores[i], 4)
            c.rr_score = round(rr_scores[i], 4)
            c.liquidity_score = round(liq_scores[i], 4)
            c.composite_score = round(
                c.delta_score * w.delta_alignment +
                c.theta_score * w.theta_efficiency +
                c.iv_score * w.iv_value +
                c.rr_score * w.reward_risk +
                c.liquidity_score * w.liquidity,
                4
            )
        
        return candidates
