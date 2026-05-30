"""
Black-Scholes probability computation — thin re-export.

The canonical implementation now lives in
``app.ota_adapters._shared.black_scholes`` (moved in OTA-716).
This module re-exports the public API so that existing callers
(analysis_routes, evaluation_routes, tests) continue to work
without import changes.
"""

from app.ota_adapters._shared.black_scholes import (  # noqa: F401
    ProbabilityMatrix,
    black_scholes_probability,
    build_probability_matrix,
    compute_probability_matrix,
)
