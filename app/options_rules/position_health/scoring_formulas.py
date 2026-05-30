"""
Position-health scoring formulas.

OTA-745: exit_level_safety_score
OTA-746: pnl_band_score
"""

from __future__ import annotations

from app.options_rules.position_health import health_formula


@health_formula("exit_level_safety_score")
def exit_level_safety_score(named_values: dict, params: dict) -> float:
    """Score position safety relative to Claude's exit levels.

    Pure function: (named_values, params) -> float in [0, 100].

    Returns:
        0   — stop breached
        warning_breached_score — warning breached (not stopped)
        graduated value — inside the proximity buffer approaching warning
        100 — well clear of warning

    The proximity buffer is the zone between "well clear" and "warning
    breached". Its width is defined by proximity_buffer_fraction as a
    fraction of the warning-stop buffer distance.

    Named values consumed:
        stop_breached (bool|None)
        warning_breached (bool|None)
        warning_proximity_ratio (float|None) — normalised distance from
            warning, in units of the warning-stop buffer. Positive = safe
            side, zero = at warning, negative = past warning.

    Parameters (from junction):
        proximity_buffer_fraction (float) — fraction of buffer defining the
            approaching-warning zone (legacy: 0.20)
        warning_breached_score (float) — score when warning breached but
            stop not breached (low value, e.g. 15)
    """
    stop_breached = named_values.get("stop_breached")
    warning_breached = named_values.get("warning_breached")
    proximity_ratio = named_values.get("warning_proximity_ratio")

    # Stop breached → 0 (worst possible)
    if stop_breached is True:
        return 0.0

    # Warning breached (not stopped) → low fixed score
    if warning_breached is True:
        return float(params.get("warning_breached_score", 15.0))

    # No breach data available → neutral (should not reach here if gates
    # are configured correctly, but defensive)
    if proximity_ratio is None:
        return 50.0

    buffer_fraction = float(params.get("proximity_buffer_fraction", 0.20))

    # proximity_ratio > buffer_fraction → well clear
    if proximity_ratio >= buffer_fraction:
        return 100.0

    # proximity_ratio in [0, buffer_fraction) → inside buffer, graduated
    # Linear interpolation: 0 at ratio=0 (at warning) to 100 at ratio=buffer_fraction
    if proximity_ratio >= 0 and buffer_fraction > 0:
        # Scale from warning_breached_score+1 up to 99
        # (100 is reserved for "well clear", warning_breached_score for "breached")
        floor = float(params.get("warning_breached_score", 15.0)) + 1.0
        ceiling = 99.0
        t = proximity_ratio / buffer_fraction
        return floor + t * (ceiling - floor)

    # proximity_ratio < 0 → past warning (should be caught by warning_breached,
    # but handle defensively)
    return float(params.get("warning_breached_score", 15.0))


@health_formula("pnl_band_score")
def pnl_band_score(named_values: dict, params: dict) -> float:
    """Score from P&L percentage bands.

    Pure function: (named_values, params) -> float in [0, 100].

    Maps pnl_pct to a score via four bands defined by three threshold
    parameters. Same formula serves both strategies; each supplies its
    own band parameters via junction rows.

    Named values consumed:
        pnl_pct (float|None) — P&L as fraction of entry price

    Parameters (from junction):
        band_1_threshold (float) — boundary between top two bands (e.g. -0.10)
        band_2_threshold (float) — boundary between middle bands (e.g. -0.25)
        band_3_threshold (float) — boundary between bottom bands (e.g. -0.50)

    Legacy mapping (health_grade.py:102-112):
        pnl_pct >= 0      → A → 100
        pnl_pct >= -0.10  → B → 75
        pnl_pct >= -0.25  → C → 50
        pnl_pct >= -0.50  → D → 25
        pnl_pct <  -0.50  → F → 0
    """
    pnl_pct = named_values.get("pnl_pct")
    if pnl_pct is None:
        return 0.0

    band_1 = float(params.get("band_1_threshold", -0.10))
    band_2 = float(params.get("band_2_threshold", -0.25))
    band_3 = float(params.get("band_3_threshold", -0.50))

    if pnl_pct >= 0:
        return 100.0
    if pnl_pct >= band_1:
        return 75.0
    if pnl_pct >= band_2:
        return 50.0
    if pnl_pct >= band_3:
        return 25.0
    return 0.0
