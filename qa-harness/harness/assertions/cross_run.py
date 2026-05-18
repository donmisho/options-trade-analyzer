"""
Cross-run assertions (D1–D6) — determinism validation.

These compare multiple captures of the same symbol across N runs.
Only meaningful when market is closed.
"""

import json
from difflib import SequenceMatcher
from typing import Dict, Any, List


def _serialize(obj: Any) -> str:
    """Deterministic JSON serialization for comparison."""
    return json.dumps(obj, sort_keys=True, default=str)


# ─── D1: Identical inputs ────────────────────────────────────────────────────

def d1_identical_inputs(captures: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Stage 1 input fields must be identical across all runs."""
    findings = []
    if len(captures) < 2:
        return [{"assertion": "D1", "status": "PASS", "message": "Single run — D1 skipped"}]

    # Compare key input fields (not timestamps)
    input_fields = ["underlying_price", "sma_8", "sma_21", "sma_50", "sma_alignment"]
    baseline = captures[0].get("stages", {}).get("stage_1_card", {}).get("inputs", {})

    for i, cap in enumerate(captures[1:], start=2):
        inputs = cap.get("stages", {}).get("stage_1_card", {}).get("inputs", {})
        for field in input_fields:
            v1 = baseline.get(field)
            v2 = inputs.get(field)
            if _serialize(v1) != _serialize(v2):
                findings.append({
                    "assertion": "D1",
                    "status": "FAIL",
                    "message": f"Input drift: {field} run1={v1} vs run{i}={v2}. Environment not frozen — aborting determinism checks.",
                    "evidence": {"field": field, "run1": v1, f"run{i}": v2},
                    "abort": True,
                })

    if not findings:
        findings.append({"assertion": "D1", "status": "PASS", "message": "Inputs identical across all runs"})
    return findings


# ─── D2: Identical card scores ────────────────────────────────────────────────

def d2_identical_card_scores(captures: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Card scores must be byte-identical across runs."""
    findings = []
    if len(captures) < 2:
        return [{"assertion": "D2", "status": "PASS", "message": "Single run — D2 skipped"}]

    baseline_strats = captures[0].get("stages", {}).get("stage_1_card", {}).get("outputs", {}).get("strategies", {})

    for i, cap in enumerate(captures[1:], start=2):
        strats = cap.get("stages", {}).get("stage_1_card", {}).get("outputs", {}).get("strategies", {})
        for key in baseline_strats:
            s1 = baseline_strats[key].get("score")
            s2 = strats.get(key, {}).get("score")
            if _serialize(s1) != _serialize(s2):
                findings.append({
                    "assertion": "D2",
                    "status": "FAIL",
                    "message": f"Card score drift: {key} run1={s1} vs run{i}={s2}",
                    "evidence": {"strategy": key, "run1": s1, f"run{i}": s2},
                })

    if not findings:
        findings.append({"assertion": "D2", "status": "PASS", "message": "Card scores identical across runs"})
    return findings


# ─── D3: Identical Trades page candidate set ──────────────────────────────────

def d3_identical_candidate_set(captures: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Candidate natural_keys, fitting_strategies, and scores must be identical across runs."""
    findings = []
    if len(captures) < 2:
        return [{"assertion": "D3", "status": "PASS", "message": "Single run — D3 skipped"}]

    def _extract_candidate_fingerprint(cap):
        candidates = cap.get("stages", {}).get("stage_2_trades", {}).get("candidates", [])
        fps = {}
        for c in candidates:
            nk = c.get("natural_key")
            fps[nk] = {
                "score": c.get("composite_score"),
                "fitting_strategies": sorted(c.get("fitting_strategies") or []),
            }
        return fps

    baseline = _extract_candidate_fingerprint(captures[0])
    baseline_keys = set(baseline.keys())

    for i, cap in enumerate(captures[1:], start=2):
        current = _extract_candidate_fingerprint(cap)
        current_keys = set(current.keys())

        # Check set equality
        added = current_keys - baseline_keys
        removed = baseline_keys - current_keys

        if added:
            findings.append({
                "assertion": "D3",
                "status": "FAIL",
                "message": f"Candidate set drift: run{i} has {len(added)} new candidates vs run1",
                "evidence": {"added": list(added)[:5]},
            })
        if removed:
            findings.append({
                "assertion": "D3",
                "status": "FAIL",
                "message": f"Candidate set drift: run{i} missing {len(removed)} candidates from run1",
                "evidence": {"removed": list(removed)[:5]},
            })

        # Check score + pills equality for shared candidates
        for nk in baseline_keys & current_keys:
            if _serialize(baseline[nk]) != _serialize(current[nk]):
                findings.append({
                    "assertion": "D3",
                    "status": "FAIL",
                    "message": f"Candidate fingerprint drift: {nk} run1={baseline[nk]} vs run{i}={current[nk]}",
                    "evidence": {"natural_key": nk, "run1": baseline[nk], f"run{i}": current[nk]},
                })

    if not findings:
        findings.append({"assertion": "D3", "status": "PASS", "message": "Candidate set identical across runs"})
    return findings


# ─── D4: Identical evaluation outputs ─────────────────────────────────────────

def d4_identical_evaluation_outputs(captures: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Structured eval fields (verdict, scores, risks) must be identical. Narrative may differ."""
    findings = []
    if len(captures) < 2:
        return [{"assertion": "D4", "status": "PASS", "message": "Single run — D4 skipped"}]

    def _extract_structured_fields(eval_data):
        """Extract deterministic fields from an evaluation, excluding narrative text."""
        result = {}
        for ek, ev in eval_data.items():
            resp = ev.get("response") or {}
            for e in resp.get("evaluations", []):
                result[ek] = {
                    "verdict": e.get("verdict"),
                    "score": e.get("score"),
                    "key_risks": sorted(e.get("key_risks") or []),
                    "thesis_invalidators": sorted(e.get("thesis_invalidators") or []),
                    "auto_pass_reason": e.get("auto_pass_reason"),
                }
        return result

    baseline_evals = captures[0].get("stages", {}).get("stage_4_evaluation", {}).get("per_evaluation", {})
    baseline = _extract_structured_fields(baseline_evals)

    for i, cap in enumerate(captures[1:], start=2):
        current_evals = cap.get("stages", {}).get("stage_4_evaluation", {}).get("per_evaluation", {})
        current = _extract_structured_fields(current_evals)

        for ek in set(baseline.keys()) & set(current.keys()):
            if _serialize(baseline[ek]) != _serialize(current[ek]):
                findings.append({
                    "assertion": "D4",
                    "status": "FAIL",
                    "message": f"Evaluation output drift: {ek} structured fields differ between run1 and run{i}",
                    "evidence": {"eval_key": ek, "run1": baseline[ek], f"run{i}": current[ek]},
                })

    if not findings:
        findings.append({"assertion": "D4", "status": "PASS", "message": "Evaluation structured fields identical"})
    return findings


# ─── D5: Identical hard-gate outcomes ─────────────────────────────────────────

def d5_identical_hard_gate_outcomes(captures: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Hard-gate auto_pass_reason must be identical across runs for the same candidate."""
    findings = []
    if len(captures) < 2:
        return [{"assertion": "D5", "status": "PASS", "message": "Single run — D5 skipped"}]

    def _extract_gate_outcomes(cap):
        evals = cap.get("stages", {}).get("stage_4_evaluation", {}).get("per_evaluation", {})
        outcomes = {}
        for ek, ev in evals.items():
            resp = ev.get("response") or {}
            for e in resp.get("evaluations", []):
                outcomes[ek] = e.get("auto_pass_reason")
        return outcomes

    baseline = _extract_gate_outcomes(captures[0])

    for i, cap in enumerate(captures[1:], start=2):
        current = _extract_gate_outcomes(cap)
        for ek in set(baseline.keys()) & set(current.keys()):
            if baseline[ek] != current[ek]:
                findings.append({
                    "assertion": "D5",
                    "status": "FAIL",
                    "message": f"Hard-gate outcome drift: {ek} run1={baseline[ek]} vs run{i}={current[ek]}",
                    "evidence": {"eval_key": ek, "run1": baseline[ek], f"run{i}": current[ek]},
                })

    if not findings:
        findings.append({"assertion": "D5", "status": "PASS", "message": "Hard-gate outcomes identical"})
    return findings


# ─── D6: Narrative drift bound (advisory) ────────────────────────────────────

def d6_narrative_drift(captures: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Advisory: flag if narrative text similarity drops below 0.85 across runs."""
    findings = []
    if len(captures) < 2:
        return [{"assertion": "D6", "status": "PASS", "message": "Single run — D6 skipped"}]

    def _extract_narratives(cap):
        evals = cap.get("stages", {}).get("stage_4_evaluation", {}).get("per_evaluation", {})
        narratives = {}
        for ek, ev in evals.items():
            resp = ev.get("response") or {}
            for e in resp.get("evaluations", []):
                narratives[ek] = e.get("claude_read") or ""
        return narratives

    baseline = _extract_narratives(captures[0])

    FALLBACK_MARKER = "Narrative unavailable this cycle"

    for i, cap in enumerate(captures[1:], start=2):
        current = _extract_narratives(cap)
        for ek in set(baseline.keys()) & set(current.keys()):
            if baseline[ek] and current[ek] and baseline[ek] != current[ek]:
                # Skip pairs where either side is a fallback placeholder (OTA-656)
                if FALLBACK_MARKER in baseline[ek]:
                    findings.append({
                        "assertion": "D6",
                        "status": "SKIP",
                        "message": f"D6: skipped pair {ek} — fallback narrative present in run1",
                    })
                    continue
                if FALLBACK_MARKER in current[ek]:
                    findings.append({
                        "assertion": "D6",
                        "status": "SKIP",
                        "message": f"D6: skipped pair {ek} — fallback narrative present in run{i}",
                    })
                    continue

                similarity = SequenceMatcher(None, baseline[ek], current[ek]).ratio()
                if similarity < 0.85:
                    findings.append({
                        "assertion": "D6",
                        "status": "WARN",
                        "message": f"Narrative drift: {ek} similarity={similarity:.2f} < 0.85 between run1 and run{i}",
                        "evidence": {"eval_key": ek, "similarity": similarity},
                    })

    if not findings:
        findings.append({"assertion": "D6", "status": "PASS", "message": "Narrative drift within bounds"})
    return findings


# ─── Run all cross-run assertions ─────────────────────────────────────────────

ALL_ASSERTIONS = [
    ("D1", d1_identical_inputs),
    ("D2", d2_identical_card_scores),
    ("D3", d3_identical_candidate_set),
    ("D4", d4_identical_evaluation_outputs),
    ("D5", d5_identical_hard_gate_outcomes),
    ("D6", d6_narrative_drift),
]


def run_all(captures: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Run all cross-run assertions. Returns list of findings."""
    all_findings = []

    for name, fn in ALL_ASSERTIONS:
        try:
            findings = fn(captures)
            all_findings.extend(findings)

            # D1 abort: if inputs aren't stable, skip remaining determinism checks
            if name == "D1" and any(f.get("abort") for f in findings):
                all_findings.append({
                    "assertion": "D1",
                    "status": "FAIL",
                    "message": "D1 failed — inputs not stable. Remaining determinism assertions skipped.",
                })
                break
        except Exception as e:
            all_findings.append({
                "assertion": name,
                "status": "FAIL",
                "message": f"Assertion {name} raised exception: {e}",
                "evidence": {"exception": str(e)},
            })

    return all_findings
