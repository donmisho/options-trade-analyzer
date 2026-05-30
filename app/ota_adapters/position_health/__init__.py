"""
Position-health adapter — OTA-734 feature.

Implements the Insight Engine §5 input adapter contract for the
position-health grading surface: produce candidates from open positions,
declare the input catalog, and provide a COMPUTED callback.

OTA-735 (skeleton + interface), OTA-736–740 (producers + catalog),
OTA-741 (parity tests vs health_grade.py)
"""

from app.ota_adapters.position_health.adapter import PositionHealthAdapter

__all__ = ["PositionHealthAdapter"]
