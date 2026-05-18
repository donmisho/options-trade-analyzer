"""
Machine-readable assertion report — assertions.json
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List


def generate(
    symbol: str,
    within_run_findings: Dict[int, List[Dict[str, Any]]],
    cross_run_findings: List[Dict[str, Any]],
    captures: List[Dict[str, Any]],
    report_dir: Path,
) -> Path:
    """Write assertions.json to report_dir. Returns path to file."""
    report_dir.mkdir(parents=True, exist_ok=True)

    total_fail = 0
    total_warn = 0
    total_pass = 0

    for run_idx, findings in within_run_findings.items():
        for f in findings:
            if f["status"] == "FAIL":
                total_fail += 1
            elif f["status"] == "WARN":
                total_warn += 1
            else:
                total_pass += 1

    for f in cross_run_findings:
        if f["status"] == "FAIL":
            total_fail += 1
        elif f["status"] == "WARN":
            total_warn += 1
        else:
            total_pass += 1

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "runs": len(captures),
        "overall_status": "FAIL" if total_fail > 0 else "PASS",
        "summary": {
            "failures": total_fail,
            "warnings": total_warn,
            "passes": total_pass,
        },
        "within_run": {
            str(run_idx): findings
            for run_idx, findings in within_run_findings.items()
        },
        "cross_run": cross_run_findings,
    }

    out_path = report_dir / "assertions.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    return out_path
