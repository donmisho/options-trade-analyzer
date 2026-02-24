"""
Directional Strategy Comparison Engine

WHY THIS EXISTS:
This is NEW functionality that maps to your "Directional Trade
Comparison" prompt template. Instead of you manually describing a
trade thesis to Claude, the API takes your parameters and returns
a structured comparison of 2-4 strategies.

HOW IT WORKS:
1. You provide: symbol, direction, target price, timeframe, budget
2. Engine fetches the chain and builds the best candidate for each
   strategy type:
   - Long call/put (for the directional bet)
   - Vertical spread (debit spread matching direction)
   - Wider vertical spread (more profit potential, higher cost)
3. Each strategy is evaluated on: cost, max profit, breakeven,
   required move, probability, and whether it fits your budget
4. One strategy is flagged as "recommended" based on best fit

This replaces the manual process of you typing out the comparison
prompt and me running the numbers. Same logic, automated.
"""

from dataclasses import dataclass, asdict
from typing import Optional
from .vertical_engine import VerticalSpreadEngine, ScoringWeights, SpreadFilters
from .long_call_engine import LongCallEngine, LongCallWeights, LongCallFilters


@dataclass
class Thesis:
    """User's trade thesis"""
    symbol: str
    direction: str           # "bullish" or "bearish"
    target_price: float      # Where you think it's going
    timeframe_days: int      # How long you expect it to take
    risk_budget: float       # Max dollars you'll risk on this trade
    current_price: float = 0 # Filled by engine from quote


@dataclass
class StrategyCandidate:
    """One strategy evaluated against the thesis"""
    strategy_name: str       # e.g., "Bear Put 525/520", "Long 520 Put"
    strategy_type: str       # "vertical_spread", "long_option"
    
    # Core metrics
    cost: float              # Total cost to enter
    max_profit: float        # Best case (per contract × qty)
    max_profit_str: str      # "$630" or "Unlimited"
    max_loss: float
    breakeven: float
    required_move_pct: float # % the stock needs to move for profit
    prob_of_profit: float    # Estimated probability
    
    # Thesis fit
    fits_budget: bool
    buffer_pct: float        # How much room for error (± %)
    
    # Details
    contracts: int           # How many contracts for the budget
    expiration: str
    strikes: str             # "525/520" or "520"
    option_type: str         # "call" or "put"
    
    # Verdict
    is_recommended: bool = False
    verdict: str = ""        # "Best match", "Needs bigger drop", etc.
    verdict_reason: str = "" # Explanation of why
    
    def to_dict(self):
        return asdict(self)


class DirectionalEngine:
    """
    Compares strategies for a given directional thesis.
    
    Usage:
        engine = DirectionalEngine()
        result = engine.compare(thesis, chain_data)
    """
    
    def compare(
        self,
        thesis: Thesis,
        contracts: list[dict],
    ) -> dict:
        """
        Build and compare strategy candidates for this thesis.
        
        Returns 2-4 strategies ranked by thesis fit.
        """
        candidates = []
        price = thesis.current_price
        
        if thesis.direction == "bullish":
            candidates.extend(self._build_bullish_candidates(
                thesis, contracts, price
            ))
        else:
            candidates.extend(self._build_bearish_candidates(
                thesis, contracts, price
            ))
        
        if not candidates:
            return {
                "thesis": asdict(thesis),
                "strategies": [],
                "recommended": None,
            }
        
        # Score and recommend
        self._evaluate_candidates(candidates, thesis)
        
        # Sort by a simple fitness score
        candidates.sort(
            key=lambda c: self._fitness_score(c, thesis),
            reverse=True
        )
        
        # Mark the best as recommended
        if candidates:
            candidates[0].is_recommended = True
        
        return {
            "thesis": asdict(thesis),
            "strategies": [c.to_dict() for c in candidates],
            "recommended": candidates[0].strategy_name if candidates else None,
        }
    
    def _build_bullish_candidates(
        self, thesis: Thesis, contracts: list[dict], price: float
    ) -> list[StrategyCandidate]:
        """Build bull call spread + long call candidates."""
        candidates = []
        
        # Filter to relevant contracts (calls, right expiration range)
        calls = [
            c for c in contracts
            if c.get("option_type") == "call"
            and self._dte_in_range(c, thesis.timeframe_days)
        ]
        
        if not calls:
            return []
        
        calls.sort(key=lambda x: x["strike"])
        
        # Strategy 1: ATM-ish bull call spread (narrow)
        narrow = self._best_bull_call_spread(
            calls, price, thesis.risk_budget, max_width=5
        )
        if narrow:
            candidates.append(narrow)
        
        # Strategy 2: Wider bull call spread (more profit potential)
        wide = self._best_bull_call_spread(
            calls, price, thesis.risk_budget, max_width=10
        )
        if wide and (not narrow or wide.strikes != narrow.strikes):
            candidates.append(wide)
        
        # Strategy 3: Straight long call
        long = self._best_long_call(calls, price, thesis.risk_budget)
        if long:
            candidates.append(long)
        
        return candidates
    
    def _build_bearish_candidates(
        self, thesis: Thesis, contracts: list[dict], price: float
    ) -> list[StrategyCandidate]:
        """Build bear put spread + long put candidates."""
        candidates = []
        
        puts = [
            c for c in contracts
            if c.get("option_type") == "put"
            and self._dte_in_range(c, thesis.timeframe_days)
        ]
        
        if not puts:
            return []
        
        puts.sort(key=lambda x: x["strike"])
        
        # Strategy 1: ATM-ish bear put spread (narrow)
        narrow = self._best_bear_put_spread(
            puts, price, thesis.risk_budget, max_width=5
        )
        if narrow:
            candidates.append(narrow)
        
        # Strategy 2: Wider bear put spread
        wide = self._best_bear_put_spread(
            puts, price, thesis.risk_budget, max_width=10
        )
        if wide and (not narrow or wide.strikes != narrow.strikes):
            candidates.append(wide)
        
        # Strategy 3: Straight long put
        long = self._best_long_put(puts, price, thesis.risk_budget)
        if long:
            candidates.append(long)
        
        return candidates
    
    def _best_bull_call_spread(
        self, calls, price, budget, max_width
    ) -> Optional[StrategyCandidate]:
        """Find the best bull call spread within budget."""
        best = None
        best_score = -999
        
        for i, long_leg in enumerate(calls):
            for short_leg in calls[i + 1:]:
                width = short_leg["strike"] - long_leg["strike"]
                if width <= 0 or width > max_width:
                    continue
                
                long_mid = ((long_leg.get("bid", 0) or 0) + (long_leg.get("ask", 0) or 0)) / 2
                short_mid = ((short_leg.get("bid", 0) or 0) + (short_leg.get("ask", 0) or 0)) / 2
                debit = long_mid - short_mid
                if debit <= 0.05:
                    continue
                
                # 1 contract = 100 shares
                cost_one = round(debit * 100, 2)
                max_profit_one = round((width - debit) * 100, 2)
                
                if cost_one > budget:
                    continue
                
                breakeven = long_leg["strike"] + debit
                req_move = ((breakeven - price) / price) * 100
                prob = 1 - abs(short_leg.get("delta", 0.3) or 0.3)
                
                ev = (prob * max_profit_one) - ((1 - prob) * cost_one)
                score = ev / cost_one if cost_one > 0 else 0
                
                if score > best_score:
                    best_score = score
                    best = StrategyCandidate(
                        strategy_name=f"Bull Call {long_leg['strike']:g}/{short_leg['strike']:g}",
                        strategy_type="vertical_spread",
                        cost=cost_one,
                        max_profit=max_profit_one,
                        max_profit_str=f"${max_profit_one:,.2f}",
                        max_loss=cost_one,
                        breakeven=round(breakeven, 2),
                        required_move_pct=round(req_move, 2),
                        prob_of_profit=round(prob, 4),
                        fits_budget=True,
                        buffer_pct=0,
                        contracts=1,
                        expiration=long_leg["expiration"],
                        strikes=f"{long_leg['strike']:g}/{short_leg['strike']:g}",
                        option_type="call",
                    )
        
        return best
    
    def _best_bear_put_spread(
        self, puts, price, budget, max_width
    ) -> Optional[StrategyCandidate]:
        """Find the best bear put spread within budget."""
        best = None
        best_score = -999
        
        for i, long_leg in enumerate(puts):
            for j in range(i):
                short_leg = puts[j]
                width = long_leg["strike"] - short_leg["strike"]
                if width <= 0 or width > max_width:
                    continue
                
                long_mid = ((long_leg.get("bid", 0) or 0) + (long_leg.get("ask", 0) or 0)) / 2
                short_mid = ((short_leg.get("bid", 0) or 0) + (short_leg.get("ask", 0) or 0)) / 2
                debit = long_mid - short_mid
                if debit <= 0.05:
                    continue
                
                # 1 contract = 100 shares
                cost_one = round(debit * 100, 2)
                max_profit_one = round((width - debit) * 100, 2)
                
                if cost_one > budget:
                    continue
                
                breakeven = long_leg["strike"] - debit
                req_move = ((price - breakeven) / price) * 100
                prob = 1 - abs(short_leg.get("delta", 0.3) or 0.3)
                
                ev = (prob * max_profit_one) - ((1 - prob) * cost_one)
                score = ev / cost_one if cost_one > 0 else 0
                
                if score > best_score:
                    best_score = score
                    best = StrategyCandidate(
                        strategy_name=f"Bear Put {long_leg['strike']:g}/{short_leg['strike']:g}",
                        strategy_type="vertical_spread",
                        cost=cost_one,
                        max_profit=max_profit_one,
                        max_profit_str=f"${max_profit_one:,.2f}",
                        max_loss=cost_one,
                        breakeven=round(breakeven, 2),
                        required_move_pct=round(req_move, 2),
                        prob_of_profit=round(prob, 4),
                        fits_budget=True,
                        buffer_pct=0,
                        contracts=1,
                        expiration=long_leg["expiration"],
                        strikes=f"{long_leg['strike']:g}/{short_leg['strike']:g}",
                        option_type="put",
                    )
        
        return best
    
    def _best_long_call(
        self, calls, price, budget
    ) -> Optional[StrategyCandidate]:
        """Find the best single long call within budget."""
        best = None
        best_delta = 0
        
        for c in calls:
            delta = abs(c.get("delta", 0) or 0)
            if delta < 0.30 or delta > 0.55:
                continue
            
            mid = ((c.get("bid", 0) or 0) + (c.get("ask", 0) or 0)) / 2
            if mid <= 0:
                continue
            
            cost = mid * 100
            if cost > budget:
                continue
            
            breakeven = c["strike"] + mid
            req_move = ((breakeven - price) / price) * 100
            
            # Pick the one closest to 0.45 delta
            if best is None or abs(delta - 0.45) < abs(best_delta - 0.45):
                best_delta = delta
                best = StrategyCandidate(
                    strategy_name=f"Long {c['strike']} Call",
                    strategy_type="long_option",
                    cost=round(cost, 2),
                    max_profit=0,  # Unlimited
                    max_profit_str="Unlimited",
                    max_loss=round(cost, 2),
                    breakeven=round(breakeven, 2),
                    required_move_pct=round(req_move, 2),
                    prob_of_profit=round(delta, 4),
                    fits_budget=True,
                    buffer_pct=0,
                    contracts=1,
                    expiration=c["expiration"],
                    strikes=str(c["strike"]),
                    option_type="call",
                )
        
        return best
    
    def _best_long_put(
        self, puts, price, budget
    ) -> Optional[StrategyCandidate]:
        """Find the best single long put within budget."""
        best = None
        best_delta = 0
        
        for c in puts:
            delta = abs(c.get("delta", 0) or 0)
            if delta < 0.30 or delta > 0.55:
                continue
            
            mid = ((c.get("bid", 0) or 0) + (c.get("ask", 0) or 0)) / 2
            if mid <= 0:
                continue
            
            cost = mid * 100
            if cost > budget:
                continue
            
            breakeven = c["strike"] - mid
            req_move = ((price - breakeven) / price) * 100
            
            if best is None or abs(delta - 0.45) < abs(best_delta - 0.45):
                best_delta = delta
                best = StrategyCandidate(
                    strategy_name=f"Long {c['strike']} Put",
                    strategy_type="long_option",
                    cost=round(cost, 2),
                    max_profit=0,
                    max_profit_str="Unlimited",
                    max_loss=round(cost, 2),
                    breakeven=round(breakeven, 2),
                    required_move_pct=round(req_move, 2),
                    prob_of_profit=round(delta, 4),
                    fits_budget=True,
                    buffer_pct=0,
                    contracts=1,
                    expiration=c["expiration"],
                    strikes=str(c["strike"]),
                    option_type="put",
                )
        
        return best
    
    def _evaluate_candidates(
        self, candidates: list[StrategyCandidate], thesis: Thesis
    ):
        """Add verdicts and buffer calculations to each candidate."""
        target_move = ((thesis.target_price - thesis.current_price) 
                       / thesis.current_price) * 100
        
        for c in candidates:
            # Buffer: how much room for error between breakeven and target
            # WHY: A strategy with a 1% required move but a 5% expected move
            # has a 4% buffer. More buffer = more margin for thesis imprecision.
            if thesis.direction == "bullish":
                c.buffer_pct = round(
                    abs(target_move) - abs(c.required_move_pct), 2
                )
            else:
                c.buffer_pct = round(
                    abs(target_move) - abs(c.required_move_pct), 2
                )
            
            # Generate verdict
            if not c.fits_budget:
                c.verdict = "Over budget"
                c.verdict_reason = f"Costs ${c.cost:.0f}, budget is ${thesis.risk_budget:.0f}"
            elif c.buffer_pct < -2:
                c.verdict = "Needs bigger move"
                c.verdict_reason = (
                    f"Requires {abs(c.required_move_pct):.1f}% move, "
                    f"thesis expects only {abs(target_move):.1f}%"
                )
            elif c.buffer_pct < 0:
                c.verdict = "Tight fit"
                c.verdict_reason = "Breakeven is near your target — little margin for error"
            elif c.prob_of_profit > 0.60:
                c.verdict = "Best match"
                c.verdict_reason = (
                    f"{c.buffer_pct:.1f}% buffer with "
                    f"{c.prob_of_profit*100:.0f}% probability"
                )
            elif c.strategy_type == "long_option":
                c.verdict = "High risk, high reward"
                c.verdict_reason = "Unlimited upside but no buffer — needs conviction"
            else:
                c.verdict = "Good alternative"
                c.verdict_reason = f"{c.buffer_pct:.1f}% buffer, fits budget"
    
    def _fitness_score(
        self, candidate: StrategyCandidate, thesis: Thesis
    ) -> float:
        """Simple fitness score for ranking."""
        score = 0
        if candidate.fits_budget:
            score += 20
        score += candidate.prob_of_profit * 30
        score += min(candidate.buffer_pct, 10) * 3  # Cap buffer contribution
        if candidate.strategy_type == "vertical_spread":
            score += 5  # Slight preference for defined risk
        return score
    
    def _dte_in_range(self, contract: dict, target_days: int) -> bool:
        """Check if contract expiration is within ±50% of target timeframe."""
        from datetime import datetime, date
        try:
            exp_date = datetime.strptime(contract["expiration"], "%Y-%m-%d").date()
            dte = (exp_date - date.today()).days
            return (target_days * 0.5) <= dte <= (target_days * 2.0)
        except (ValueError, TypeError, KeyError):
            return False
