"""
Strategy-Structure Routing Predicates — OTA-636

Single source: reads compatible_structures from strategy_definitions.py.
No hardcoded duplicate of the compatibility matrix.

Also provides mappings from compatible_structures values to engine parameters
(vertical engine spread_types, long-option engine option_types).
"""

from typing import List, Optional

from app.analysis.strategy_definitions import STRATEGIES


# ─── Structure → engine-parameter mappings ───────────────────────────────────
# compatible_structures value  →  VerticalSpreadEngine spread_type
STRUCTURE_TO_SPREAD_TYPE = {
    "bull_put_credit":   "bull_put",
    "bear_call_credit":  "bear_call",
    "bull_call_debit":   "bull_call",
    "bear_put_debit":    "bear_put",
}

# compatible_structures value  →  LongCallEngine option_type
STRUCTURE_TO_OPTION_TYPE = {
    "long_call": "call",
    "long_put":  "put",
}

VERTICAL_STRUCTURES = set(STRUCTURE_TO_SPREAD_TYPE.keys())
SINGLE_LONG_STRUCTURES = set(STRUCTURE_TO_OPTION_TYPE.keys())

# Reverse: engine spread_type → compatible_structures value
SPREAD_TYPE_TO_STRUCTURE = {v: k for k, v in STRUCTURE_TO_SPREAD_TYPE.items()}
# Reverse: engine option_type → compatible_structures value
OPTION_TYPE_TO_STRUCTURE = {v: k for k, v in STRUCTURE_TO_OPTION_TYPE.items()}


# ─── Public predicates ───────────────────────────────────────────────────────

def is_compatible(strategy_key: str, structure: str) -> bool:
    """Return True if *structure* is in the strategy's compatible_structures list."""
    strategy = STRATEGIES.get(strategy_key)
    if strategy is None:
        return False
    return structure in strategy.compatible_structures


def get_compatible_strategies(structure: str) -> List[str]:
    """Inverse lookup: given a trade_structure, return strategy keys that accept it."""
    return [k for k, s in STRATEGIES.items() if structure in s.compatible_structures]


# ─── Engine-parameter helpers ────────────────────────────────────────────────

def get_spread_types_for_strategy(strategy_key: str) -> List[str]:
    """Vertical engine spread_types derived from the strategy's compatible_structures."""
    strategy = STRATEGIES.get(strategy_key)
    if not strategy:
        return []
    return [
        STRUCTURE_TO_SPREAD_TYPE[s]
        for s in strategy.compatible_structures
        if s in STRUCTURE_TO_SPREAD_TYPE
    ]


def get_option_types_for_strategy(strategy_key: str) -> List[str]:
    """Long-option engine option_types derived from the strategy's compatible_structures."""
    strategy = STRATEGIES.get(strategy_key)
    if not strategy:
        return []
    return [
        STRUCTURE_TO_OPTION_TYPE[s]
        for s in strategy.compatible_structures
        if s in STRUCTURE_TO_OPTION_TYPE
    ]


def uses_vertical_engine(strategy_key: str) -> bool:
    """True if any of the strategy's compatible structures are vertical spreads."""
    return bool(get_spread_types_for_strategy(strategy_key))


def uses_long_option_engine(strategy_key: str) -> bool:
    """True if any of the strategy's compatible structures are single-leg longs."""
    return bool(get_option_types_for_strategy(strategy_key))


def normalize_to_structure(spread_type: str = None, option_type: str = None) -> Optional[str]:
    """
    Convert an engine-level type (spread_type or option_type) to a
    compatible_structures value. Returns None if no mapping exists.

    Examples:
        normalize_to_structure(spread_type="bull_put") → "bull_put_credit"
        normalize_to_structure(option_type="call") → "long_call"
    """
    if spread_type and spread_type in SPREAD_TYPE_TO_STRUCTURE:
        return SPREAD_TYPE_TO_STRUCTURE[spread_type]
    if option_type and option_type in OPTION_TYPE_TO_STRUCTURE:
        return OPTION_TYPE_TO_STRUCTURE[option_type]
    return None
