"""
AI Provider base interface.

WHY: Same adapter pattern as your market data providers (Tradier/Schwab).
Any AI service that can evaluate trades implements this interface.
Today that's Anthropic (direct) and Azure Foundry. Tomorrow it could be
OpenAI, a local model, or anything else — the rest of your app doesn't
need to know or care which one is behind the curtain.

HOW IT FITS:
  - base.py (this file) defines WHAT an AI provider must do
  - anthropic_adapter.py implements it using Anthropic's API directly
  - foundry_adapter.py implements it using Claude through Azure Foundry
  - The factory (ai_factory.py) picks the right one based on your .env config
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TradeContext:
    """
    Everything the AI needs to evaluate a trade.
    
    WHY a dataclass: This bundles all the inputs into one clean object
    that any adapter can consume. The API endpoint builds this from the
    request body, and the adapter turns it into a prompt.
    
    All fields match the input schema in trade_evaluation_requirements.md.
    """

    # --- Market Context ---
    symbol: str                          # e.g., "QQQ"
    current_price: float                 # e.g., 437.66
    sma_short: float                     # e.g., 437.88 (fast MA)
    sma_mid: float                       # e.g., 437.30 (medium MA)
    sma_long: float                      # e.g., 436.11 (slow MA)
    sma_periods: dict                    # e.g., {"short": 8, "mid": 21, "long": 50}
    ma_alignment: str                    # e.g., "Bullish - price above all 3 SMAs"
    vix: Optional[float] = None          # e.g., 19.50

    # --- Trader Thesis ---
    direction: str = "Bullish"           # "Bullish" / "Bearish" / "Neutral"
    timeframe_days: int = 30             # How many days for the thesis to play out
    expected_move_target: Optional[float] = None  # e.g., 445.00
    conviction: str = "Medium"           # "Low" / "Medium" / "High"

    # --- Proposed Trade ---
    strategy_type: str = "Vertical Spread"
    spread: str = ""                     # e.g., "440/445 Call Debit Spread"
    expiration: str = ""                 # e.g., "2026-03-20"
    debit_paid: float = 0.0
    max_profit: float = 0.0
    rr_ratio: float = 0.0
    prob_of_profit: float = 0.0
    composite_score: Optional[float] = None
    risk_budget: float = 500.0
    num_contracts: int = 1
    total_cost: float = 0.0

    # --- Pre-calculated Exit Levels ---
    # These are computed by the app BEFORE sending to the AI
    # (per trade_evaluation_requirements.md: "don't ask the AI to calculate math")
    exit_levels: dict = field(default_factory=dict)


@dataclass
class TradeVerdict:
    """
    The AI's response, structured for the UI.
    
    WHY structured: The UI needs to parse the verdict (EXECUTE/WAIT/PASS)
    separately from the analysis text. By returning a structured object,
    the API endpoint can send the verdict as a color-coded banner and
    the analysis as formatted text, without messy string parsing.
    """

    verdict: str                         # "EXECUTE" / "WAIT" / "PASS"
    raw_response: str                    # Full text from Claude
    exit_levels: dict                    # Pre-calculated exit levels (passed through)
    model_used: str = ""                 # e.g., "claude-sonnet-4-6" for logging
    provider: str = ""                   # "anthropic" or "foundry"
    input_tokens: int = 0               # For cost tracking
    output_tokens: int = 0              # For cost tracking


class AIProvider(ABC):
    """
    Abstract interface for AI trade evaluation.
    
    Any AI service must implement:
      - evaluate_trade(): Send trade context, get a verdict back
      - health_check(): Verify the connection is working
    """

    @abstractmethod
    async def evaluate_trade(self, context: TradeContext) -> TradeVerdict:
        """
        Evaluate a proposed trade and return a verdict.
        
        Takes the full trade context (market data, thesis, trade details,
        pre-calculated exits) and returns a structured verdict with
        Claude's analysis.
        """
        ...

    @abstractmethod
    async def follow_up(
        self,
        question: str,
        conversation_history: list[dict],
    ) -> str:
        """
        Ask a follow-up question about a previous evaluation.
        
        WHY separate: Follow-ups need the full conversation history
        (the original evaluation + any prior follow-ups) so Claude
        has context. The conversation_history is a list of
        {"role": "user"/"assistant", "content": "..."} dicts.
        """
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Test if the AI provider connection is working."""
        ...
