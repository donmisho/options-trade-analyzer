"""
Position-health post-scoring adjustments.

OTA-747: stop_breached_floor, warning_breached_cap

These run AFTER the weighted sum and enforce categorical guarantees:
    stop breached  -> score forced to floor (default 0 -> F band)
    warning breached (not stopped) -> score capped at ceiling (default 24 -> D band)

Both read _current_score (injected by the pipeline before each adjustment)
to compute the exact delta needed. The engine adds the delta and clamps [0,100].
"""

from __future__ import annotations

from app.options_rules.position_health import health_adjustment


@health_adjustment("stop_breached_floor")
def stop_breached_floor(named_values: dict, params: dict) -> float:
    """Force score to a floor when stop is breached.

    When stop_breached is True, returns a delta that drives the score
    to exactly floor_score (default 0 -> F band).

    Parameters (from junction):
        floor_score (float) — target floor (default 0.0)
    """
    stop_breached = named_values.get("stop_breached")
    if stop_breached is not True:
        return 0.0

    floor = float(params.get("floor_score", 0.0))
    current = float(named_values.get("_current_score", 0.0))
    return floor - current


@health_adjustment("warning_breached_cap")
def warning_breached_cap(named_values: dict, params: dict) -> float:
    """Cap score at a ceiling when warning is breached (not stopped).

    When warning_breached is True and stop_breached is not True,
    returns a delta that caps the score at cap_score (default 24).
    If the score is already at or below the cap, no adjustment.

    Parameters (from junction):
        cap_score (float) — maximum allowed score (default 24.0)
    """
    warning_breached = named_values.get("warning_breached")
    stop_breached = named_values.get("stop_breached")

    if warning_breached is not True or stop_breached is True:
        return 0.0

    cap = float(params.get("cap_score", 24.0))
    current = float(named_values.get("_current_score", 0.0))

    if current <= cap:
        return 0.0  # already at or below cap

    return cap - current  # negative delta to bring score down to cap
