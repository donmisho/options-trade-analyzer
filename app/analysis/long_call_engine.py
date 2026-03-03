"""
Naked Options Analysis Engine (formerly Long Call Engine)

WHY THE RENAME:
The original LongCallEngine only analyzed call options. But the scoring
logic — delta alignment, theta efficiency, IV value, reward:risk, and
liquidity — works identically for puts. The only differences are:
  - Type filter: "call" vs "put"
  - Breakeven: call = strike + premium, put = strike - premium
  - Breakeven distance: calls measure upside needed, puts measure downside

Rather than duplicate the engine, we generalize it to handle both types.
The engine accepts an option_types parameter (["call"], ["put"], or
["call", "put"]) and processes each contract accordingly.

SCORING CRITERIA (unchanged from original):
  1. Delta Alignment (30%): Sweet spot 0.30-0.60. Too low = lottery
     ticket, too high = overpaying for directional exposure.
  2. Theta Efficiency (25%): runway_days = premium / abs(daily_theta).
     More days = more time for your thesis to play out.
  3. IV Value (20%): Lower IV = cheaper options = better entry.
  4. Reward:Risk (15%): (delta × underlying_price × move_pct) / premium.
  5. Liquidity (10%): Volume + OI. Can you get filled at a fair price?

BACKWARD COMPATIBILITY:
  - LongCallEngine is an alias for NakedOptionEngine
  - LongCallWeights is an alias for NakedOptionWeights
  - LongCallFilters is an alias for NakedOptionFilters
  - ScoredLongCall is an alias for ScoredNakedOption
  - All old imports continue to work without changes
"""

from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class NakedOptionWeights:
    """Weights for naked option scoring — must sum to 1.0"""
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
class NakedOptionFilters:
    """Filters applied before scoring"""
    min_delta: float = 0.25          # Below this = lottery ticket
    max_delta: float = 0.65          # Above this = just buy stock
    max_premium: float = 1500.0      # Per contract in dollars (×100)
    min_open_interest: int = 50
    min_volume: int = 5
    min_days_to_exp: int = 7         # Don't buy weeklies
    max_days_to_exp: int = 90        # Don't go too far out
    max_bid_ask_spread_pct: float = 0.15  # 15% max spread vs mid
    # NEW: Which option types to include (default: calls only for backward compat)
    option_types: list = None        # ["call"], ["put"], or ["call", "put"]

    def __post_init__(self):
        if self.option_types is None:
            self.option_types = ["call"]


@dataclass
class ScoredNakedOption:
    """A single scored naked option candidate (call or put)"""
    strike: float
    expiration: str
    days_to_exp: int
    option_type: str               # NEW: "call" or "put"

    # Option details
    bid: float
    ask: float
    mid_price: float
    premium_dollars: float         # mid × 100

    # Greeks
    delta: float
    gamma: float
    theta: float
    vega: float
    iv: float                      # Implied volatility %

    # Liquidity
    volume: int
    open_interest: int
    bid_ask_spread_pct: float      # (ask-bid)/mid as %

    # Calculated values
    breakeven: float               # call: strike + premium, put: strike - premium
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


class NakedOptionEngine:
    """
    Scores and ranks naked option candidates (calls and/or puts) from
    an options chain.

    Usage:
        engine = NakedOptionEngine(weights, filters)
        results = engine.analyze(chain_data, underlying_price)
    """

    def __init__(
        self,
        weights: Optional[NakedOptionWeights] = None,
        filters: Optional[NakedOptionFilters] = None,
    ):
        self.weights = weights or NakedOptionWeights()
        self.weights.validate()
        self.filters = filters or NakedOptionFilters()

    def analyze(
        self,
        contracts: list[dict],
        underlying_price: float,
        max_results: Optional[int] = None,
    ) -> dict:
        """
        Analyze option contracts and return ranked results.

        WHAT CHANGED FROM ORIGINAL:
        - Filters by option_types list instead of hardcoded "call"
        - Returns key "options" (plus backward-compat "calls")
        - Each result has an option_type field
        """

        # Filter to requested option types
        # WHY: The chain from Schwab contains both calls and puts.
        # We filter to only the types the user toggled on in the UI.
        allowed = set(self.filters.option_types)
        filtered = [
            c for c in contracts
            if c.get("option_type") in allowed
        ]

        # Build scored candidates
        candidates = []
        for c in filtered:
            scored = self._evaluate_option(c, underlying_price)
            if scored:
                candidates.append(scored)

        if not candidates:
            return {
                "options": [],
                "calls": [],          # backward compat
                "total_valid": 0,
                "underlying_price": underlying_price,
            }

        # Score and rank
        scored = self._score_all(candidates)
        scored.sort(key=lambda s: s.composite_score, reverse=True)

        if max_results:
            scored = scored[:max_results]

        result_dicts = [s.to_dict() for s in scored]
        return {
            "options": result_dicts,
            "calls": result_dicts,    # backward compat for frontend
            "total_valid": len(candidates),
            "underlying_price": underlying_price,
        }

    def _evaluate_option(
        self, contract: dict, price: float
    ) -> Optional[ScoredNakedOption]:
        """
        Build a ScoredNakedOption from a raw contract, applying filters.

        WHAT CHANGED FROM ORIGINAL _evaluate_call:
        - Accepts both calls and puts
        - Breakeven calculation is type-aware
        - Breakeven distance measures the correct direction
        - Returns ScoredNakedOption with option_type field
        """
        option_type = contract.get("option_type", "call")

        # abs(delta) because put deltas are negative from the provider
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
        # BREAKEVEN differs by type:
        #   Call: stock must rise ABOVE strike + premium to profit
        #   Put:  stock must fall BELOW strike - premium to profit
        if option_type == "put":
            breakeven = strike - mid
            # Distance is how far DOWN the stock must move (as positive %)
            be_distance = ((price - breakeven) / price) * 100
        else:
            breakeven = strike + mid
            # Distance is how far UP the stock must move (as positive %)
            be_distance = ((breakeven - price) / price) * 100

        # Theta runway: how many days until theta alone eats the premium
        theta_per_day = abs(theta) * 100  # Daily $ decay per contract
        theta_runway = premium / theta_per_day if theta_per_day > 0 else 999

        return ScoredNakedOption(
            strike=strike,
            expiration=exp,
            days_to_exp=dte,
            option_type=option_type,
            bid=bid,
            ask=ask,
            mid_price=round(mid, 2),
            premium_dollars=round(premium, 2),
            delta=round(delta, 4),
            gamma=round(gamma, 4),
            theta=round(theta, 4),
            vega=round(vega, 4),
            iv=round(iv * 100 if iv < 1 else iv, 2),
            volume=volume,
            open_interest=oi,
            bid_ask_spread_pct=round(ba_spread_pct * 100, 2),
            breakeven=round(breakeven, 2),
            breakeven_distance_pct=round(be_distance, 2),
            theta_per_day_dollars=round(theta_per_day, 2),
            theta_runway_days=round(theta_runway, 1),
        )

    def _score_all(
        self, candidates: list[ScoredNakedOption]
    ) -> list[ScoredNakedOption]:
        """
        Normalize and apply weighted scoring.

        UNCHANGED from original — the scoring math is identical for
        calls and puts. Delta sweet spot, theta runway, IV preference,
        R:R ratio, and liquidity all work the same way regardless of
        option type.
        """
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

        # Delta alignment: score peaks at 0.45 (sweet spot)
        delta_scores = []
        for c in candidates:
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
            higher_is_better=False
        )

        # Reward:Risk: delta × 100 / premium
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


# ── Backward-compatible aliases ──────────────────────────────────
# WHY: The old class names are used throughout the codebase —
# analysis_routes.py, __init__.py, client.js, etc. These aliases
# mean all existing imports continue to work with zero changes.
# New code should prefer the Naked* names.
LongCallWeights = NakedOptionWeights
LongCallFilters = NakedOptionFilters
ScoredLongCall = ScoredNakedOption
LongCallEngine = NakedOptionEngine
