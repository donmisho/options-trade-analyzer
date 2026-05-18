"""
Within-run assertions (A1–A10) — intra-snapshot coherence.

Each assertion function takes a capture_doc and returns a list of findings.
A finding is a dict: {assertion, status, message, evidence}.
status: "FAIL", "WARN", or "PASS".
"""

import sys
import yaml
from pathlib import Path
from typing import Dict, Any, List

# Add project root to path so we can import the backend compatibility map
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.analysis.strategy_routing import (
    get_compatible_strategies,
    normalize_to_structure,
    SPREAD_TYPE_TO_STRUCTURE,
    OPTION_TYPE_TO_STRUCTURE,
)

from harness.config import STRATEGY_KEYS, ENGINE_TO_STRUCTURE

_HARNESS_ROOT = Path(__file__).resolve().parent.parent.parent
_NARRATIVE_KEYWORDS_PATH = _HARNESS_ROOT / "narrative-keywords.yaml"


def _load_narrative_keywords() -> List[str]:
    if _NARRATIVE_KEYWORDS_PATH.exists():
        with open(_NARRATIVE_KEYWORDS_PATH) as f:
            data = yaml.safe_load(f)
        return data.get("reject_keywords", [])
    return []


def _get_structure(candidate: Dict[str, Any]) -> str:
    """Get the normalized structure for a candidate."""
    return candidate.get("structure") or ENGINE_TO_STRUCTURE.get(
        candidate.get("spread_type") or candidate.get("option_type"), "unknown"
    )


def _get_trade_direction(candidate: Dict[str, Any]) -> str:
    """Derive trade direction from structure. Returns 'bullish', 'bearish', or 'neutral'."""
    structure = _get_structure(candidate)
    spread_type = candidate.get("spread_type", "")
    option_type = candidate.get("option_type", "")

    if structure in ("bull_call_debit", "bull_put_credit") or spread_type in ("bull_call", "bull_put"):
        return "bullish"
    if structure in ("bear_put_debit", "bear_call_credit") or spread_type in ("bear_put", "bear_call"):
        return "bearish"
    if structure == "long_call" or option_type == "call":
        return "bullish"
    if structure == "long_put" or option_type == "put":
        return "bearish"
    return "neutral"


def _get_stack_direction(sma_alignment: str) -> str:
    """Derive stack direction from SMA alignment string."""
    if not sma_alignment:
        return "neutral"
    alignment_lower = sma_alignment.lower()
    if "bullish" in alignment_lower:
        return "bullish"
    if "bearish" in alignment_lower:
        return "bearish"
    return "neutral"


def _group_candidates_by_strategy(candidates: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Group candidates by their fitting_strategies."""
    groups: Dict[str, List[Dict[str, Any]]] = {k: [] for k in STRATEGY_KEYS}
    for c in candidates:
        for s in (c.get("fitting_strategies") or []):
            if s in groups:
                groups[s].append(c)
    return groups


# ─── A1: Card score ↔ Trades page reality ────────────────────────────────────

def a1_card_vs_trades(capture: Dict[str, Any]) -> List[Dict[str, Any]]:
    """If card scores non-null for strategy S, trades must have candidates for S."""
    findings = []
    s1 = capture.get("stages", {}).get("stage_1_card", {})
    s2 = capture.get("stages", {}).get("stage_2_trades", {})

    strategies = s1.get("outputs", {}).get("strategies", {})
    candidates = s2.get("candidates", [])
    no_setups = s1.get("outputs", {}).get("no_compatible_setups", [])

    grouped = _group_candidates_by_strategy(candidates)

    for key in STRATEGY_KEYS:
        strat = strategies.get(key, {})
        score = strat.get("score")
        has_candidates = len(grouped.get(key, [])) > 0

        if score is not None and score > 0 and not has_candidates:
            findings.append({
                "assertion": "A1",
                "status": "FAIL",
                "message": f"{key}: card score={score} but no candidates in trades scan",
                "evidence": {"strategy": key, "card_score": score, "candidate_count": 0},
            })
        elif (score is None or score == 0) and has_candidates:
            findings.append({
                "assertion": "A1",
                "status": "FAIL",
                "message": f"{key}: card score={score} (N/A) but {len(grouped[key])} candidates found in trades",
                "evidence": {"strategy": key, "card_score": score, "candidate_count": len(grouped[key])},
            })
        elif score is not None and score > 0 and key in no_setups:
            findings.append({
                "assertion": "A1",
                "status": "FAIL",
                "message": f"{key}: card score={score} but listed in no-compatible-setups",
                "evidence": {"strategy": key, "card_score": score},
            })

    if not findings:
        findings.append({"assertion": "A1", "status": "PASS", "message": "Card scores consistent with trades"})
    return findings


# ─── A2: Section grouping ↔ best_fit ─────────────────────────────────────────

def a2_section_vs_bestfit(capture: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Each candidate's section (fitting_strategies) should match structurally compatible strategies only."""
    findings = []
    s2 = capture.get("stages", {}).get("stage_2_trades", {})
    candidates = s2.get("candidates", [])

    for c in candidates:
        structure = _get_structure(c)
        compatible = set(get_compatible_strategies(structure))
        fitting = set(c.get("fitting_strategies") or [])

        # Any fitting strategy that isn't structurally compatible is a mixed-grid error
        invalid_fits = fitting - compatible
        if invalid_fits:
            findings.append({
                "assertion": "A2",
                "status": "FAIL",
                "message": f"Mixed grid: {c.get('natural_key')} structure={structure} has fitting_strategies={list(fitting)} but compatible={list(compatible)}. Invalid: {list(invalid_fits)}",
                "evidence": {
                    "natural_key": c.get("natural_key"),
                    "structure": structure,
                    "fitting_strategies": list(fitting),
                    "compatible_strategies": list(compatible),
                    "invalid": list(invalid_fits),
                },
            })

    if not findings:
        findings.append({"assertion": "A2", "status": "PASS", "message": "Section grouping matches compatibility"})
    return findings


# ─── A3: Strategy pills ↔ compatibility ──────────────────────────────────────

def a3_pills_vs_compatibility(capture: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Every pill (fitting_strategy) must be compatible with the candidate's structure."""
    findings = []
    s2 = capture.get("stages", {}).get("stage_2_trades", {})
    candidates = s2.get("candidates", [])

    for c in candidates:
        structure = _get_structure(c)
        compatible = set(get_compatible_strategies(structure))
        pills = c.get("fitting_strategies") or []

        for pill in pills:
            if pill not in compatible:
                findings.append({
                    "assertion": "A3",
                    "status": "FAIL",
                    "message": f"Incompatible pill: {pill} on {c.get('natural_key')} (structure={structure}, compatible={list(compatible)})",
                    "evidence": {
                        "natural_key": c.get("natural_key"),
                        "structure": structure,
                        "pill": pill,
                        "compatible": list(compatible),
                    },
                })

    if not findings:
        findings.append({"assertion": "A3", "status": "PASS", "message": "All pills match compatibility map"})
    return findings


# ─── A4: best_fit null state ──────────────────────────────────────────────────

def a4_bestfit_null_state(capture: Dict[str, Any]) -> List[Dict[str, Any]]:
    """If best_fit_score is 0.00 or best_fit is null, it should not show a strategy name."""
    findings = []
    s3 = capture.get("stages", {}).get("stage_3_detail", {})
    details = s3.get("per_candidate", {})

    for nk, detail in details.items():
        score = detail.get("composite_score")
        fitting = detail.get("fitting_strategies") or []

        # If score is exactly 0 and yet fitting strategies are assigned, flag it
        if score is not None and score == 0.0 and len(fitting) > 0:
            findings.append({
                "assertion": "A4",
                "status": "FAIL",
                "message": f"best_fit null state violation: {nk} score=0.00 but has fitting_strategies={fitting}",
                "evidence": {"natural_key": nk, "score": score, "fitting_strategies": fitting},
            })

    if not findings:
        findings.append({"assertion": "A4", "status": "PASS", "message": "best_fit null states correct"})
    return findings


# ─── A5: Hard-gate enforcement ────────────────────────────────────────────────

def a5_hard_gate_enforcement(capture: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Check debit % cap, negative EV gates on surfaced candidates."""
    findings = []
    s3 = capture.get("stages", {}).get("stage_3_detail", {})
    s4 = capture.get("stages", {}).get("stage_4_evaluation", {})
    details = s3.get("per_candidate", {})
    evals = s4.get("per_evaluation", {})

    # Build a lookup of verdicts by natural_key
    verdict_by_nk: Dict[str, str] = {}
    for ek, ev in evals.items():
        nk = ev.get("natural_key")
        resp = ev.get("response") or {}
        for e in resp.get("evaluations", []):
            verdict = e.get("verdict")
            if nk and verdict:
                verdict_by_nk[nk] = verdict

    for nk, detail in details.items():
        entry_price = detail.get("entry_price")
        spread_width = detail.get("spread_width")
        ev_raw = detail.get("ev_raw")

        # Debit % cap: entry_price / spread_width > 0.40
        if entry_price is not None and spread_width and spread_width > 0:
            # For debit spreads, entry_price is positive (cost paid)
            # For credit spreads, entry_price is negative (premium received)
            debit_pct = abs(entry_price) / spread_width if entry_price > 0 else 0
            if debit_pct > 0.40:
                verdict = verdict_by_nk.get(nk)
                if verdict and verdict != "PASS":
                    findings.append({
                        "assertion": "A5",
                        "status": "FAIL",
                        "message": f"Debit % gate violation: {nk} debit_pct={debit_pct:.2%} > 40%, verdict={verdict} (should be PASS)",
                        "evidence": {"natural_key": nk, "debit_pct": debit_pct, "verdict": verdict},
                    })

        # Negative EV gate
        if ev_raw is not None and ev_raw < 0:
            verdict = verdict_by_nk.get(nk)
            if verdict and verdict != "PASS":
                findings.append({
                    "assertion": "A5",
                    "status": "FAIL",
                    "message": f"Negative EV gate violation: {nk} ev_raw={ev_raw:.2f}, verdict={verdict} (should be PASS)",
                    "evidence": {"natural_key": nk, "ev_raw": ev_raw, "verdict": verdict},
                })

    if not findings:
        findings.append({"assertion": "A5", "status": "PASS", "message": "Hard gates enforced correctly"})
    return findings


# ─── A6: Verdict ↔ narrative consistency ──────────────────────────────────────

def a6_verdict_narrative_consistency(capture: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Check narrative keywords against verdict for structural mismatches."""
    findings = []
    reject_keywords = _load_narrative_keywords()
    s4 = capture.get("stages", {}).get("stage_4_evaluation", {})
    evals = s4.get("per_evaluation", {})

    for ek, ev in evals.items():
        resp = ev.get("response") or {}
        for e in resp.get("evaluations", []):
            verdict = e.get("verdict", "")
            narrative = (e.get("claude_read") or "").lower()

            # Pattern 1: explicit "PASS" keywords in narrative but verdict isn't PASS
            if "structural mismatch" in narrative and verdict != "PASS":
                findings.append({
                    "assertion": "A6",
                    "status": "FAIL",
                    "message": f"Pattern 1: narrative contains 'structural mismatch' but verdict={verdict} ({ek})",
                    "evidence": {"eval_key": ek, "verdict": verdict, "narrative_excerpt": narrative[:200]},
                })

            # Pattern 2: reject keywords + EXECUTE verdict
            if verdict == "EXECUTE":
                for kw in reject_keywords:
                    if kw.lower() in narrative:
                        findings.append({
                            "assertion": "A6",
                            "status": "FAIL",
                            "message": f"Pattern 2: narrative contains '{kw}' but verdict=EXECUTE ({ek})",
                            "evidence": {"eval_key": ek, "verdict": verdict, "keyword": kw},
                        })
                        break  # one finding per eval is enough

    if not findings:
        findings.append({"assertion": "A6", "status": "PASS", "message": "Verdict/narrative consistency OK"})
    return findings


# ─── A7: Spread type classification ──────────────────────────────────────────

def a7_spread_type_classification(capture: Dict[str, Any]) -> List[Dict[str, Any]]:
    """No spread_type should be UNKNOWN for well-formed candidates."""
    findings = []
    s2 = capture.get("stages", {}).get("stage_2_trades", {})
    candidates = s2.get("candidates", [])

    known_types = set(ENGINE_TO_STRUCTURE.keys())

    for c in candidates:
        st = c.get("spread_type") or c.get("option_type") or "unknown"
        if st.lower() == "unknown":
            findings.append({
                "assertion": "A7",
                "status": "FAIL",
                "message": f"UNKNOWN spread_type on {c.get('natural_key')}",
                "evidence": {"natural_key": c.get("natural_key"), "spread_type": st},
            })

    if not findings:
        findings.append({"assertion": "A7", "status": "PASS", "message": "No UNKNOWN spread types"})
    return findings


# ─── A8: Technical alignment directional sign ────────────────────────────────

def a8_technical_alignment_direction(capture: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Opposing stack + trade direction should drag technical alignment score, not lift it."""
    findings = []
    s1 = capture.get("stages", {}).get("stage_1_card", {})
    s4 = capture.get("stages", {}).get("stage_4_evaluation", {})
    s2 = capture.get("stages", {}).get("stage_2_trades", {})

    sma_alignment = s1.get("inputs", {}).get("sma_alignment", "")
    stack_direction = _get_stack_direction(sma_alignment)

    if stack_direction == "neutral":
        return [{"assertion": "A8", "status": "PASS", "message": "SMA stack neutral — directional sign check N/A"}]

    evals = s4.get("per_evaluation", {})
    candidates_by_nk = {c.get("natural_key"): c for c in s2.get("candidates", [])}

    for ek, ev in evals.items():
        nk = ev.get("natural_key")
        candidate = candidates_by_nk.get(nk, {})
        trade_direction = _get_trade_direction(candidate)

        if trade_direction == "neutral":
            continue

        if trade_direction != stack_direction:
            # Opposing — check if technical alignment component is too high
            resp = ev.get("response") or {}
            for e in resp.get("evaluations", []):
                # Look for sma_alignment_score in the evaluation response
                # This might be in score breakdown or metric_scores
                score_breakdown = e.get("score_breakdown") or {}
                sma_score = None
                for comp_key in ("sma_alignment_score", "technical_alignment", "sma_alignment"):
                    if comp_key in score_breakdown:
                        val = score_breakdown[comp_key]
                        if isinstance(val, dict):
                            sma_score = val.get("normalized") or val.get("score")
                        else:
                            sma_score = val
                        break

                if sma_score is not None and sma_score > 0.3:
                    findings.append({
                        "assertion": "A8",
                        "status": "FAIL",
                        "message": f"Opposing direction: stack={stack_direction}, trade={trade_direction}, but sma_alignment_score={sma_score} > 0.3 ({ek})",
                        "evidence": {
                            "eval_key": ek,
                            "stack_direction": stack_direction,
                            "trade_direction": trade_direction,
                            "sma_alignment_score": sma_score,
                        },
                    })

    if not findings:
        findings.append({"assertion": "A8", "status": "PASS", "message": "Technical alignment directional sign OK"})
    return findings


# ─── A9: Net delta sign vs trade direction ────────────────────────────────────

def a9_net_delta_sign(capture: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Net delta sign must match trade direction."""
    findings = []
    s3 = capture.get("stages", {}).get("stage_3_detail", {})
    details = s3.get("per_candidate", {})

    for nk, detail in details.items():
        net_delta = detail.get("net_delta")
        if net_delta is None:
            # Long options may use "delta" instead
            net_delta = detail.get("delta")
        if net_delta is None:
            continue

        trade_direction = _get_trade_direction(detail)
        if trade_direction == "neutral":
            continue

        # Bullish trades should have positive delta, bearish negative
        if trade_direction == "bullish" and net_delta < -0.01:
            findings.append({
                "assertion": "A9",
                "status": "FAIL",
                "message": f"Delta sign mismatch: {nk} direction=bullish but net_delta={net_delta:.4f}",
                "evidence": {"natural_key": nk, "direction": trade_direction, "net_delta": net_delta},
            })
        elif trade_direction == "bearish" and net_delta > 0.01:
            findings.append({
                "assertion": "A9",
                "status": "FAIL",
                "message": f"Delta sign mismatch: {nk} direction=bearish but net_delta={net_delta:.4f}",
                "evidence": {"natural_key": nk, "direction": trade_direction, "net_delta": net_delta},
            })
        elif abs(net_delta) < 0.01:
            findings.append({
                "assertion": "A9",
                "status": "WARN",
                "message": f"Near-zero delta: {nk} direction={trade_direction} but net_delta={net_delta:.4f}",
                "evidence": {"natural_key": nk, "direction": trade_direction, "net_delta": net_delta},
            })

    if not findings:
        findings.append({"assertion": "A9", "status": "PASS", "message": "Net delta signs match trade directions"})
    return findings


# ─── A10: Score arithmetic reconciliation ────────────────────────────────────

def a10_score_arithmetic(capture: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Verify component_score * weight sums to displayed total within tolerance."""
    findings = []
    s4 = capture.get("stages", {}).get("stage_4_evaluation", {})
    evals = s4.get("per_evaluation", {})

    for ek, ev in evals.items():
        resp = ev.get("response") or {}
        for e in resp.get("evaluations", []):
            score = e.get("score")
            breakdown = e.get("score_breakdown") or {}
            if not breakdown or score is None:
                continue

            # Try to reconcile if breakdown has weighted components
            computed_total = 0
            has_weights = False
            for comp_key, comp_val in breakdown.items():
                if isinstance(comp_val, dict) and "contribution" in comp_val:
                    computed_total += comp_val["contribution"]
                    has_weights = True
                elif isinstance(comp_val, dict) and "normalized" in comp_val and "weight" in comp_val:
                    computed_total += comp_val["normalized"] * comp_val["weight"]
                    has_weights = True

            if has_weights:
                # Score is 0-100, computed_total might be 0-1 scale
                if computed_total <= 1.0:
                    computed_total *= 100

                diff = abs(score - computed_total)
                if diff > 1.0:  # tolerance of 1 point on 0-100 scale
                    findings.append({
                        "assertion": "A10",
                        "status": "FAIL",
                        "message": f"Score arithmetic mismatch: {ek} displayed={score}, computed={computed_total:.2f}, diff={diff:.2f}",
                        "evidence": {"eval_key": ek, "displayed_score": score, "computed_total": computed_total},
                    })

    if not findings:
        findings.append({"assertion": "A10", "status": "PASS", "message": "Score arithmetic reconciles"})
    return findings


# ─── Run all within-run assertions ────────────────────────────────────────────

ALL_ASSERTIONS = [
    ("A1", a1_card_vs_trades),
    ("A2", a2_section_vs_bestfit),
    ("A3", a3_pills_vs_compatibility),
    ("A4", a4_bestfit_null_state),
    ("A5", a5_hard_gate_enforcement),
    ("A6", a6_verdict_narrative_consistency),
    ("A7", a7_spread_type_classification),
    ("A8", a8_technical_alignment_direction),
    ("A9", a9_net_delta_sign),
    ("A10", a10_score_arithmetic),
]


def run_all(capture: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Run all within-run assertions on a capture document. Returns list of findings."""
    all_findings = []
    for name, fn in ALL_ASSERTIONS:
        try:
            findings = fn(capture)
            all_findings.extend(findings)
        except Exception as e:
            all_findings.append({
                "assertion": name,
                "status": "FAIL",
                "message": f"Assertion {name} raised exception: {e}",
                "evidence": {"exception": str(e)},
            })
    return all_findings
