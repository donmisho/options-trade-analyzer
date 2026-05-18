"""
Human-readable summary report — summary.md
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List
from collections import Counter


def generate(
    symbol: str,
    within_run_findings: Dict[int, List[Dict[str, Any]]],
    cross_run_findings: List[Dict[str, Any]],
    captures: List[Dict[str, Any]],
    report_dir: Path,
) -> Path:
    """Write summary.md to report_dir. Returns path to file."""
    report_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")

    # Collect all failures and warnings
    failures: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []

    for run_idx, findings in within_run_findings.items():
        for f in findings:
            f_with_run = {**f, "run": run_idx}
            if f["status"] == "FAIL":
                failures.append(f_with_run)
            elif f["status"] == "WARN":
                warnings.append(f_with_run)

    for f in cross_run_findings:
        f_with_run = {**f, "run": "cross-run"}
        if f["status"] == "FAIL":
            failures.append(f_with_run)
        elif f["status"] == "WARN":
            warnings.append(f_with_run)

    overall = "FAIL" if failures else "PASS"
    n_runs = len(captures)
    market_status = captures[0].get("market_status", "unknown") if captures else "unknown"

    lines = []
    lines.append(f"# QA Harness Run - {ts}")
    lines.append("")
    lines.append(f"## Status: {'FAIL' if failures else 'PASS'}")
    lines.append("")
    lines.append(f"- **Symbol:** {symbol}")
    lines.append(f"- **Runs:** {n_runs}")
    lines.append(f"- **Market status:** {market_status}")
    lines.append(f"- **Failures:** {len(failures)}")
    lines.append(f"- **Warnings:** {len(warnings)}")
    lines.append("")

    if market_status == "open":
        lines.append("> WARNING: This harness ran during market hours. Determinism assertions are invalid.")
        lines.append("")

    # Group failures by assertion
    if failures:
        lines.append("## Failures")
        lines.append("")
        by_assertion: Dict[str, List] = {}
        for f in failures:
            key = f["assertion"]
            by_assertion.setdefault(key, []).append(f)

        for assertion in sorted(by_assertion.keys()):
            items = by_assertion[assertion]
            runs_affected = sorted(set(str(f["run"]) for f in items))
            lines.append(f"### {assertion} ({len(items)} finding{'s' if len(items) > 1 else ''})")
            for item in items[:10]:  # cap at 10 per assertion to keep report readable
                lines.append(f"- {item['message']}")
            if len(items) > 10:
                lines.append(f"- ... and {len(items) - 10} more")
            lines.append("")

    # Passes
    all_assertions = set()
    for findings in within_run_findings.values():
        for f in findings:
            all_assertions.add(f["assertion"])
    for f in cross_run_findings:
        all_assertions.add(f["assertion"])

    failed_assertions = set(f["assertion"] for f in failures)
    passed_assertions = all_assertions - failed_assertions

    if passed_assertions:
        lines.append("## Passes")
        lines.append("")
        for a in sorted(passed_assertions):
            lines.append(f"- {a}")
        lines.append("")

    # Warnings
    if warnings:
        lines.append("## Warnings (non-blocking)")
        lines.append("")
        for w in warnings[:20]:
            lines.append(f"- [{w['assertion']}] {w['message']}")
        if len(warnings) > 20:
            lines.append(f"- ... and {len(warnings) - 20} more")
        lines.append("")

    # Stage 4 infrastructure errors
    infra_errors = []
    for cap in captures:
        for e in cap.get("stages", {}).get("stage_4_evaluation", {}).get("errors", []):
            infra_errors.append(e)
    if infra_errors:
        lines.append("## Infrastructure Errors (Foundry)")
        lines.append("")
        status_counts = Counter(e.get("http_status") for e in infra_errors)
        for status, count in status_counts.items():
            lines.append(f"- HTTP {status}: {count} occurrence{'s' if count > 1 else ''}")
        lines.append("")

    content = "\n".join(lines)
    out_path = report_dir / "summary.md"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
    return out_path
