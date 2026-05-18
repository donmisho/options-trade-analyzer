"""
Stage 5 — Order generation (observational placeholder).

Per Phase 1 finding #5: no API endpoint exists for order generation.
This is a no-op placeholder for Phase 2.
"""

from typing import Dict, Any


def capture() -> Dict[str, Any]:
    """Placeholder — no order generation API available."""
    return {
        "status": "observational_only",
        "reason": "no API endpoint per Phase 1 finding",
        "warnings": [],
        "errors": [],
    }
