"""
Analysis engines for the Options Analyzer.

Phase 2 adds three engines:
  - VerticalSpreadEngine: Score and rank bull call + bear put spreads
  - LongCallEngine: Score and rank long call candidates
  - DirectionalEngine: Compare strategies for a directional thesis
"""

from .vertical_engine import (
    VerticalSpreadEngine,
    ScoringWeights,
    SpreadFilters,
    ScoredSpread,
)
from .long_call_engine import (
    LongCallEngine,
    LongCallWeights,
    LongCallFilters,
    ScoredLongCall,
)
from .directional_engine import (
    DirectionalEngine,
    Thesis,
    StrategyCandidate,
)

__all__ = [
    "VerticalSpreadEngine",
    "ScoringWeights",
    "SpreadFilters",
    "ScoredSpread",
    "LongCallEngine",
    "LongCallWeights",
    "LongCallFilters",
    "ScoredLongCall",
    "DirectionalEngine",
    "Thesis",
    "StrategyCandidate",
]
