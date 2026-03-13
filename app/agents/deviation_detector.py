"""
DeviationDetector — Phase 3.6 Stream A2.

Generic, domain-agnostic deviation detection. Four rule types cover the
common cases: threshold crossings, directional trends, statistical anomalies,
and multi-signal correlations.

All methods are pure functions — no I/O, no database access, no API calls.
Each returns a DeviationResult dataclass. InsightEngine feeds the result
directly into the Claude prompt.

WHY pure functions: makes testing trivial (no mocks needed), makes the
detector reusable across domains, and keeps the logic easy to reason about.
"""

import statistics
from typing import List

from app.models.schemas import DeviationResult


class DeviationDetector:
    """
    Generic deviation detection. All methods are stateless.

    Instantiate once per InsightEngine; safe to share across requests.
    """

    def check_threshold(
        self,
        current_value: float,
        warning_threshold: float,
        stop_threshold: float,
        metric_name: str,
        direction: str = "below",   # 'below' | 'above'
    ) -> DeviationResult:
        """
        Detect when a value crosses a predefined threshold.

        Used for: exit warning levels crossing, P&L hitting stop levels,
        quality control limits, budget overruns.

        direction='below': deviation when current < warning (e.g., price drops below exit level)
        direction='above': deviation when current > warning (e.g., defect rate exceeds limit)
        """
        if direction == "below":
            at_warning = current_value <= warning_threshold
            at_stop = current_value <= stop_threshold
            pct_from_warning = (
                (warning_threshold - current_value) / abs(warning_threshold) * 100
                if warning_threshold != 0 else 0.0
            )
        else:
            at_warning = current_value >= warning_threshold
            at_stop = current_value >= stop_threshold
            pct_from_warning = (
                (current_value - warning_threshold) / abs(warning_threshold) * 100
                if warning_threshold != 0 else 0.0
            )

        if not at_warning:
            return DeviationResult(
                detected=False,
                deviation_score=0,
                observation={"metric": metric_name, "current": current_value},
                baseline={"warning_threshold": warning_threshold, "stop_threshold": stop_threshold},
                description=f"{metric_name} ({current_value}) is within normal bounds.",
            )

        # Score: warning zone = 50-75, stop zone = 75-100
        if at_stop:
            score = min(100, 75 + int(pct_from_warning * 5))
            desc = (
                f"{metric_name} ({current_value}) has breached the stop threshold "
                f"({stop_threshold}). Immediate action required."
            )
        else:
            score = min(74, 50 + int(pct_from_warning * 3))
            desc = (
                f"{metric_name} ({current_value}) has crossed the warning threshold "
                f"({warning_threshold}). Position is stressed."
            )

        return DeviationResult(
            detected=True,
            deviation_type="THRESHOLD",
            deviation_score=score,
            observation={"metric": metric_name, "current": current_value, "pct_from_warning": round(pct_from_warning, 2)},
            baseline={"warning_threshold": warning_threshold, "stop_threshold": stop_threshold},
            description=desc,
        )

    def check_trend(
        self,
        values: List[float],
        periods: int = 3,
        direction: str = "degrading",   # 'degrading' | 'improving'
    ) -> DeviationResult:
        """
        Detect when a metric has moved consistently in one direction.

        Used for: P&L declining 3 days in a row, defect rate rising week-over-week,
        customer health score steadily dropping.

        values: time series with most recent value LAST.
        periods: how many consecutive steps must move in the same direction.
        """
        if len(values) < periods + 1:
            return DeviationResult(
                detected=False,
                deviation_score=0,
                observation={"values": values},
                baseline={"required_periods": periods},
                description=f"Insufficient data for trend detection (need {periods + 1} points, have {len(values)}).",
            )

        recent = values[-(periods + 1):]   # last N+1 values

        if direction == "degrading":
            # Every step must be strictly decreasing
            consistently_moving = all(recent[i] > recent[i + 1] for i in range(periods))
        else:
            # Every step must be strictly increasing
            consistently_moving = all(recent[i] < recent[i + 1] for i in range(periods))

        if not consistently_moving:
            return DeviationResult(
                detected=False,
                deviation_score=0,
                observation={"values": recent, "direction": direction},
                baseline={"required_periods": periods},
                description=f"No consistent {direction} trend detected over {periods} periods.",
            )

        total_change = abs(recent[-1] - recent[0])
        pct_change = (total_change / abs(recent[0]) * 100) if recent[0] != 0 else 0.0
        score = min(100, 40 + int(pct_change * 2))

        dir_word = "declined" if direction == "degrading" else "improved"
        desc = (
            f"Metric has {dir_word} consistently for {periods} consecutive periods "
            f"({recent[0]:.2f} → {recent[-1]:.2f}, {pct_change:.1f}% change)."
        )

        return DeviationResult(
            detected=True,
            deviation_type="TREND",
            deviation_score=score,
            observation={"values": recent, "direction": direction, "total_change": round(total_change, 4)},
            baseline={"required_periods": periods, "start_value": recent[0]},
            description=desc,
        )

    def check_anomaly(
        self,
        current_value: float,
        historical_values: List[float],
        std_dev_threshold: float = 2.0,
    ) -> DeviationResult:
        """
        Detect when a value is statistically unusual vs. its history.

        Used for: unusual trading volume, abnormal price move relative to
        typical daily range, unexpected sensor reading.

        std_dev_threshold: how many standard deviations from mean to flag.
        """
        if len(historical_values) < 5:
            return DeviationResult(
                detected=False,
                deviation_score=0,
                observation={"current": current_value},
                baseline={"history_length": len(historical_values)},
                description="Insufficient history for anomaly detection (need >= 5 points).",
            )

        mean = statistics.mean(historical_values)
        std = statistics.stdev(historical_values)

        if std == 0:
            return DeviationResult(
                detected=False,
                deviation_score=0,
                observation={"current": current_value, "mean": mean},
                baseline={"std_dev": 0},
                description="Historical values have zero variance — anomaly detection not applicable.",
            )

        z_score = abs(current_value - mean) / std
        detected = z_score >= std_dev_threshold

        if not detected:
            return DeviationResult(
                detected=False,
                deviation_score=0,
                observation={"current": current_value, "z_score": round(z_score, 2)},
                baseline={"mean": round(mean, 4), "std_dev": round(std, 4), "threshold": std_dev_threshold},
                description=f"Value ({current_value}) is within {std_dev_threshold}σ of historical mean ({mean:.2f}).",
            )

        score = min(100, int(z_score / std_dev_threshold * 50))
        direction = "above" if current_value > mean else "below"
        desc = (
            f"Value ({current_value}) is {z_score:.1f}σ {direction} the historical mean "
            f"({mean:.2f} ± {std:.2f}). This is statistically anomalous."
        )

        return DeviationResult(
            detected=True,
            deviation_type="ANOMALY",
            deviation_score=score,
            observation={"current": current_value, "z_score": round(z_score, 2), "direction": direction},
            baseline={"mean": round(mean, 4), "std_dev": round(std, 4), "threshold": std_dev_threshold},
            description=desc,
        )

    def check_correlation(
        self,
        signals: List[dict],    # [{name, value, expected_value}, ...]
        threshold: int = 2,     # minimum adverse signals to trigger
    ) -> DeviationResult:
        """
        Detect when multiple signals are moving adversely at the same time.

        Used for: price down + sentiment down + volume spiking simultaneously.
        Each signal dict: {name, value, expected_value}.
        A signal is adverse when value and expected_value differ in direction
        (i.e., value < expected_value for things we want to go up, or
        the caller sets them up so adverse = value > expected_value).

        Simple rule: if |value - expected_value| / |expected_value| > 2%,
        the signal is considered adverse.
        """
        if not signals:
            return DeviationResult(
                detected=False,
                deviation_score=0,
                observation={"signals": []},
                baseline={"threshold": threshold},
                description="No signals provided.",
            )

        adverse = []
        for sig in signals:
            name = sig.get("name", "unknown")
            value = sig.get("value", 0)
            expected = sig.get("expected_value", 0)
            if expected == 0:
                continue
            deviation_pct = abs(value - expected) / abs(expected)
            if deviation_pct > 0.02:
                adverse.append({
                    "name": name,
                    "value": value,
                    "expected": expected,
                    "deviation_pct": round(deviation_pct * 100, 1),
                })

        detected = len(adverse) >= threshold

        if not detected:
            return DeviationResult(
                detected=False,
                deviation_score=0,
                observation={"adverse_count": len(adverse), "adverse_signals": adverse},
                baseline={"threshold": threshold, "total_signals": len(signals)},
                description=f"{len(adverse)} adverse signal(s) detected — below threshold of {threshold}.",
            )

        score = min(100, 40 + len(adverse) * 15)
        names = ", ".join(s["name"] for s in adverse)
        desc = (
            f"{len(adverse)} adverse signals are coinciding: {names}. "
            f"Multi-signal correlation detected."
        )

        return DeviationResult(
            detected=True,
            deviation_type="CORRELATION",
            deviation_score=score,
            observation={"adverse_count": len(adverse), "adverse_signals": adverse},
            baseline={"threshold": threshold, "total_signals": len(signals)},
            description=desc,
        )
