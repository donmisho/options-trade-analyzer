"""
Directional gate formulas — registered pre-scoring gates for the
directional thesis-comparison surface.

OTA-837: Two gates the engine's generic predicate path cannot express
(it compares one named value to one bound parameter literal, with no
two-named-value comparison and no arithmetic — OTA-833 Phase 0 finding):

  dir_earnings      — next_earnings_date <= expiration + buffer_days
                      (two named values + date math)
  dir_negative_ev   — resolved EV < threshold, where EV is split across
                      ev_raw (spreads) and total_ev (naked longs)

Gate formulas return bool:
  True  = gate passed, candidate continues
  False = gate failed, engine checks stop_if_fail / terminal_verdict / score_penalty

Gate behaviour (halt vs. record-only, any score_penalty, any terminal_verdict)
is **entirely junction-driven** (insight_engine.md §3.6) and lives in OTA-833's
junction config — never in these formulas. There is no `if strategy_key ==`
branching here: the earnings kill-vs-record-only split (Income hard-stop;
Growth/Longshot record-only) and the unknown-earnings flag-don't-kill path come
from the junction (`stop_if_fail` / `score_penalty`) plus the `earnings_unknown`
flag handled by a separate atomic gate (OTA-833) — not from this code.

Mirrors the screening formula-backed-gate pattern
(app/options_rules/screening/gate_formulas.py, OTA-730/731).

OTA-837
"""

from __future__ import annotations

from datetime import date

from app.options_rules.directional import gate_formula


def _as_date(value) -> date | None:
    """Coerce an ISO ``YYYY-MM-DD`` string (or ``date``) to a ``date``.

    Returns ``None`` for anything unparseable or absent — callers treat a
    ``None`` date as "unknown" and fail-open rather than false-failing.
    """
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


@gate_formula("dir_earnings")
def dir_earnings(named_values: dict, params: dict) -> bool:
    """Block trades whose next earnings event falls inside the holding window.

    Predicate (the engine's generic path cannot express this — two named
    values + date arithmetic):

        fail when  next_earnings_date <= expiration + buffer_days

    Returns ``False`` (gate fails) ONLY when ``next_earnings_date`` is KNOWN
    and falls on or before ``expiration`` plus the junction buffer. Returns
    ``True`` (pass) when:
      - ``next_earnings_date`` is null/unparseable (unknown earnings —
        fail-open; the record-only flag is driven by ``earnings_unknown`` +
        the junction, not here), or
      - ``expiration`` is null/unparseable (cannot evaluate → never
        false-fail), or
      - the earnings event is after ``expiration + buffer_days``.

    No strategy branching: whether a failure halts (Income) or merely records
    a penalty (Growth/Longshot) is the junction's ``stop_if_fail`` /
    ``score_penalty``, set by OTA-833.

    Params (from junction; junction is authoritative):
      buffer_days: int — days past expiration still treated as in-window
                   (default 0 — pure ``next_earnings_date <= expiration``).
    """
    earnings = _as_date(named_values.get("next_earnings_date"))
    if earnings is None:
        return True  # unknown earnings → fail-open, never false-fail

    expiry = _as_date(named_values.get("expiration"))
    if expiry is None:
        return True  # cannot evaluate the window → pass

    buffer_days = int(params.get("buffer_days", 0))
    window_end = expiry.toordinal() + buffer_days
    in_window = earnings.toordinal() <= window_end
    return not in_window  # False when earnings in window → gate fails


@gate_formula("dir_negative_ev")
def dir_negative_ev(named_values: dict, params: dict) -> bool:
    """Block directional trades with negative expected value.

    EV is deliberately split across two named values (OTA-834): ``ev_raw``
    (DERIVED — populated for debit spreads; ``None`` for naked longs) and
    ``total_ev`` (COMPUTED — populated for naked longs via Black-Scholes;
    absent for spreads). This gate reads ``ev_raw`` when present, else
    ``total_ev``.

    Returns ``False`` (gate fails) ONLY when the resolved EV is below
    ``threshold``. Returns ``True`` (pass) when:
      - both ``ev_raw`` and ``total_ev`` are null — defer to the
        data-completeness gate; a missing EV is not a negative EV, so this
        never halts on ``None`` (a naive ``None >= 0 → False`` would wrongly
        kill every naked candidate before COMPUTED EV is populated), or
      - the resolved EV is at or above ``threshold``.

    Params (from junction; junction is authoritative):
      threshold: float — EV must be >= this value (default 0.0).
    """
    ev = named_values.get("ev_raw")
    if ev is None:
        ev = named_values.get("total_ev")
    if ev is None:
        return True  # both absent → defer to data-completeness gate, never halt

    threshold = float(params.get("threshold", 0.0))
    # bool(): total_ev may be a numpy float (Black-Scholes), whose comparison
    # yields numpy.bool_ — the @gate_formula wrapper requires a strict bool.
    return bool(float(ev) >= threshold)
