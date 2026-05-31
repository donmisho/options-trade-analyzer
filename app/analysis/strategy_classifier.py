"""
Strategy Classifier — OTA-506

Determines the best-fit strategy for a specific trade based on effective DTE.

DTE eligibility bounds (dte_min / dte_max) live on the canonical
StrategyConfig in strategy_definitions.py. Both the classifier and the
scorer read the same source. OTA-772 consolidated the former separate
STRATEGY_DTE_REQUIREMENTS dict into STRATEGIES. OTA-778 split the former
StrategyDefinition into generic StrategyConfig and OptionsStrategyParams.

Strategy keys use the internal kebab-case identifiers used throughout the
codebase (strategy_definitions.py, strategy_scorer.py, frontend config files).
"""

from dataclasses import dataclass
from typing import List, Optional

from app.analysis.strategy_definitions import STRATEGIES
from app.analysis.strategy_scorer import StrategyScore
from app.analysis.strategy_routing import is_compatible


# ─── Output type ──────────────────────────────────────────────────────────────

@dataclass
class StrategyClassification:
    """
    Result of classify_best_strategy().

    best_fit=None means no strategy is viable for the given effective DTE.
    reason is always set — it explains either the winning strategy or why
    no strategy qualified.

    This is a valid classifier output, not an error condition.
    Callers must NOT raise on best_fit=None; display reason as informational text.
    """
    best_fit: Optional[str]   # strategy key, e.g. "trend-rider"; None if none viable
    reason: str               # human-readable explanation
    score: Optional[int] = None  # score of the winning strategy (None if no winner)


# ─── DTE filter ───────────────────────────────────────────────────────────────

def filter_strategies_by_effective_dte(
    candidates: List[StrategyScore],
    effective_dte: int,
) -> List[StrategyScore]:
    """
    Return only candidates whose DTE eligibility range includes effective_dte.
    Both bounds are inclusive.

    Reads dte_min / dte_max from the canonical STRATEGIES dict
    (strategy_definitions.py). Strategies not found in STRATEGIES are passed
    through unchanged (fail-open) so unknown or future strategies don't
    silently disappear from the viable set.

    Args:
        candidates: scored strategies to filter
        effective_dte: the effective DTE of the specific trade under evaluation
                       (may differ from nominal DTE if an earnings gate fired)
    """
    result = []
    for c in candidates:
        strategy = STRATEGIES.get(c.strategy_key)
        if strategy is None:
            # Unknown strategy key — pass through rather than silently drop
            result.append(c)
            continue
        if strategy.dte_min <= effective_dte <= strategy.dte_max:
            result.append(c)
    return result


# ─── Classifier entry point ───────────────────────────────────────────────────

def classify_best_strategy(
    candidates: List[StrategyScore],
    effective_dte: int,
    trade_structure: Optional[str] = None,
) -> StrategyClassification:
    """
    Filter candidates by structural compatibility (OTA-636) and effective DTE
    eligibility, then return the highest-scoring viable strategy.

    Returns StrategyClassification with best_fit=None when no strategy
    qualifies. Never raises.

    Args:
        candidates: scored strategies (from score_all_strategies or a
                    synthetic list for testing). Each must have .strategy_key,
                    .label, and .score attributes.
        effective_dte: effective DTE of the trade — MUST be the post
                       gate-override value, not nominal DTE.
        trade_structure: if provided, only strategies whose compatible_structures
                         include this value are considered. None = skip structural filter.
    """
    # OTA-636: structural compatibility filter
    if trade_structure:
        viable = [
            c for c in candidates
            if is_compatible(c.strategy_key, trade_structure)
        ]
    else:
        viable = list(candidates)

    # DTE eligibility filter
    viable = filter_strategies_by_effective_dte(viable, effective_dte)

    if not viable:
        reason_parts = []
        if trade_structure:
            reason_parts.append(f"structure '{trade_structure}'")
        reason_parts.append(f"effective DTE {effective_dte}")
        return StrategyClassification(
            best_fit=None,
            score=None,
            reason=f"No viable strategy for {' + '.join(reason_parts)}",
        )

    best = max(viable, key=lambda c: c.score)
    return StrategyClassification(
        best_fit=best.strategy_key,
        score=best.score,
        reason=(
            f"Best fit: {best.label} "
            f"(score {best.score}, effective DTE {effective_dte})"
        ),
    )
