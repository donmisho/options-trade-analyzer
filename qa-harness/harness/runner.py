"""
QA Harness runner — orchestrates capture + assertions across symbol universe.

Usage (from project root):
    python qa-harness/harness/runner.py --symbol VOO --runs 1
    python qa-harness/harness/runner.py --symbols all --runs 5
    python qa-harness/harness/runner.py --symbols VOO,AAPL --runs 3 --allow-market-hours
"""

import argparse
import json
import sys
import time
import yaml
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

# Add qa-harness/ to sys.path so `from harness.xxx` imports work
_QA_HARNESS_ROOT = Path(__file__).resolve().parent.parent
if str(_QA_HARNESS_ROOT) not in sys.path:
    sys.path.insert(0, str(_QA_HARNESS_ROOT))

# Add project root so app.analysis.strategy_routing is importable
_PROJECT_ROOT = _QA_HARNESS_ROOT.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from harness.config import DEV_API_BASE, MIN_DELAY_BETWEEN_RUNS_SEC
from harness.capture import stage_1_card, stage_2_trades, stage_3_detail, stage_4_evaluate, stage_5_order
from harness.assertions import within_run, cross_run
from harness.report import json_report, markdown_summary

HARNESS_ROOT = Path(__file__).resolve().parent.parent
CAPTURES_DIR = HARNESS_ROOT / "captures"
REPORTS_DIR = HARNESS_ROOT / "reports"
SYMBOLS_FILE = HARNESS_ROOT / "regression-symbols.yaml"


def load_symbols() -> list[str]:
    """Load symbols from regression-symbols.yaml, excluding ROTATING."""
    with open(SYMBOLS_FILE) as f:
        data = yaml.safe_load(f)
    return [
        s["ticker"] for s in data.get("symbols", [])
        if not s.get("manual_selection_required")
    ]


def is_market_open() -> bool:
    """Simple market hours check: M-F 9:30-16:00 ET. No holiday calendar."""
    et = ZoneInfo("America/New_York")
    now = datetime.now(et)
    if now.weekday() >= 5:
        return False
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_open <= now <= market_close


def run_capture(symbol: str, run_index: int, total_runs: int) -> dict:
    """Execute one full capture run for a symbol."""
    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ") + f"_run{run_index}"
    print(f"\n--- Run {run_index}/{total_runs} for {symbol} (id: {run_id}) ---")

    print("  Stage 1 (card)...", end=" ", flush=True)
    s1 = stage_1_card.capture(symbol)
    s1_ok = len(s1.get("errors", [])) == 0 and s1.get("outputs", {}).get("strategies")
    underlying_price = s1.get("inputs", {}).get("underlying_price") or 0
    print(f"{'OK' if s1_ok else 'FAIL'} (price={underlying_price})")

    print("  Stage 2 (trades)...", end=" ", flush=True)
    s2 = stage_2_trades.capture(symbol, underlying_price)
    candidates = s2.get("candidates", [])
    counts = s2.get("counts", {})
    print(f"OK ({counts.get('total_after_bounds', 0)} candidates after bounds)")

    print("  Stage 3 (detail)...", end=" ", flush=True)
    s3 = stage_3_detail.capture(candidates)
    print(f"OK ({s3.get('count', 0)} details extracted)")

    print("  Stage 4 (evaluation)...", end=" ", flush=True)
    s4 = stage_4_evaluate.capture(symbol, candidates, s1)
    s4_counts = s4.get("counts", {})
    print(f"OK ({s4_counts.get('total_evaluated', 0)} evaluated, {s4_counts.get('errors', 0)} errors)")

    s5 = stage_5_order.capture()

    all_warnings = (
        s1.get("warnings", []) + s2.get("warnings", []) +
        s3.get("warnings", []) + s4.get("warnings", []) + s5.get("warnings", [])
    )
    all_errors = (
        s1.get("errors", []) + s2.get("errors", []) +
        s3.get("errors", []) + s4.get("errors", []) + s5.get("errors", [])
    )

    return {
        "symbol": symbol,
        "run_id": run_id,
        "run_index": run_index,
        "of_runs": total_runs,
        "market_status": "open" if is_market_open() else "closed",
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_env": DEV_API_BASE,
        "stages": {
            "stage_1_card": s1,
            "stage_2_trades": s2,
            "stage_3_detail": s3,
            "stage_4_evaluation": s4,
            "stage_5_order": s5,
        },
        "warnings": all_warnings,
        "errors": all_errors,
    }


def save_capture(capture_doc: dict) -> Path:
    """Write capture JSON to disk."""
    symbol = capture_doc["symbol"]
    run_id = capture_doc["run_id"]
    out_dir = CAPTURES_DIR / symbol
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"run-{run_id}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(capture_doc, f, indent=2, default=str)
    return out_path


def run_assertions_for_symbol(symbol: str, captures: list) -> dict:
    """Run within-run and cross-run assertions for one symbol."""
    within_findings = {}
    for cap in captures:
        idx = cap["run_index"]
        print(f"  Within-run assertions for {symbol} run {idx}...", end=" ", flush=True)
        findings = within_run.run_all(cap)
        within_findings[idx] = findings
        fails = sum(1 for f in findings if f["status"] == "FAIL")
        warns = sum(1 for f in findings if f["status"] == "WARN")
        print(f"{fails} failures, {warns} warnings")

    print(f"  Cross-run assertions for {symbol}...", end=" ", flush=True)
    cross_findings = cross_run.run_all(captures)
    fails = sum(1 for f in cross_findings if f["status"] == "FAIL")
    warns = sum(1 for f in cross_findings if f["status"] == "WARN")
    print(f"{fails} failures, {warns} warnings")

    return {"within_run": within_findings, "cross_run": cross_findings}


def count_findings(assertion_data: dict) -> tuple[int, int]:
    """Count total failures and warnings from assertion data."""
    total_fail = sum(
        1 for findings in assertion_data["within_run"].values()
        for f in findings if f["status"] == "FAIL"
    ) + sum(1 for f in assertion_data["cross_run"] if f["status"] == "FAIL")

    total_warn = sum(
        1 for findings in assertion_data["within_run"].values()
        for f in findings if f["status"] == "WARN"
    ) + sum(1 for f in assertion_data["cross_run"] if f["status"] == "WARN")

    return total_fail, total_warn


def print_universe_summary(
    symbol_results: dict,
    run_ts: str,
    report_dir: Path,
    num_runs: int,
):
    """Print consolidated summary across all symbols."""
    total_fail = 0
    total_warn = 0
    symbol_statuses = {}

    for symbol, data in symbol_results.items():
        sf, sw = count_findings(data["assertions"])
        total_fail += sf
        total_warn += sw
        symbol_statuses[symbol] = "FAIL" if sf > 0 else "PASS"

    failed_symbols = [s for s, st in symbol_statuses.items() if st == "FAIL"]
    passed_symbols = [s for s, st in symbol_statuses.items() if st == "PASS"]
    overall = "RED (FAIL)" if total_fail > 0 else "GREEN (PASS)"

    print(f"""
============================================================
QA Harness Universe Run Complete — {run_ts}
Symbols: {len(symbol_results)} | Runs per symbol: {num_runs} | Status: {overall}
============================================================""")

    for symbol in sorted(symbol_results.keys()):
        data = symbol_results[symbol]
        sf, sw = count_findings(data["assertions"])
        status = symbol_statuses[symbol]

        # Collect assertion-level breakdown
        assertion_counts = {}
        for findings in data["assertions"]["within_run"].values():
            for f in findings:
                key = f["assertion"]
                assertion_counts.setdefault(key, {"fail": 0, "warn": 0, "pass": 0})
                assertion_counts[key][f["status"].lower()] += 1
        for f in data["assertions"]["cross_run"]:
            key = f["assertion"]
            assertion_counts.setdefault(key, {"fail": 0, "warn": 0, "pass": 0})
            assertion_counts[key][f["status"].lower()] += 1

        failed_assertions = [k for k, v in assertion_counts.items() if v["fail"] > 0]

        print(f"\n  {symbol:6s}  {status:4s}  ({sf} fail, {sw} warn)")
        if failed_assertions:
            for a in sorted(failed_assertions):
                c = assertion_counts[a]
                print(f"           {a}: {c['fail']} fail")

    print(f"""
Report: {report_dir}
  - assertions.json  (machine-readable)
  - summary.md       (human-readable)

Universe total: {total_fail} failures, {total_warn} warnings
Failed: {', '.join(failed_symbols) if failed_symbols else 'none'}
Passed: {', '.join(passed_symbols) if passed_symbols else 'none'}
============================================================""")


def main():
    parser = argparse.ArgumentParser(description="QA Harness — capture + assertions")
    parser.add_argument("--symbol", type=str, default=None, help="Single symbol to capture")
    parser.add_argument("--symbols", type=str, default=None, help="Comma-separated symbols or 'all'")
    parser.add_argument("--runs", type=int, default=1, help="Number of sequential runs per symbol")
    parser.add_argument("--allow-market-hours", action="store_true", help="Allow running during market hours")
    parser.add_argument("--capture-only", action="store_true", help="Skip assertions")
    args = parser.parse_args()

    # Resolve symbol list
    if args.symbols:
        if args.symbols.lower() == "all":
            symbols = load_symbols()
        else:
            symbols = [s.strip().upper() for s in args.symbols.split(",")]
    elif args.symbol:
        symbols = [args.symbol.upper()]
    else:
        symbols = ["VOO"]

    # Market hours check
    if is_market_open() and not args.allow_market_hours:
        print("""
WARNING: Market is currently OPEN.
This harness is designed for market-closed conditions.
Running during market hours produces invalid determinism assertions.

To override, use --allow-market-hours flag.
Aborting.""")
        sys.exit(1)

    if is_market_open():
        print("\nWARNING: Running during market hours. Determinism assertions will be invalid.\n")

    print(f"QA Harness - targeting {DEV_API_BASE}")
    print(f"Symbols: {', '.join(symbols)} | Runs: {args.runs}")
    print(f"Market status: {'OPEN' if is_market_open() else 'CLOSED'}")
    print(f"Mode: {'capture-only' if args.capture_only else 'capture + assertions'}")

    run_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    report_dir = REPORTS_DIR / run_ts

    # Per-symbol results
    symbol_results = {}
    universe_fail = 0

    for symbol in symbols:
        print(f"\n{'='*60}")
        print(f"  SYMBOL: {symbol}")
        print(f"{'='*60}")

        captures = []
        for i in range(1, args.runs + 1):
            cap = run_capture(symbol, i, args.runs)
            save_capture(cap)
            captures.append(cap)
            if i < args.runs:
                print(f"  (delay {MIN_DELAY_BETWEEN_RUNS_SEC}s)")
                time.sleep(MIN_DELAY_BETWEEN_RUNS_SEC)

        if args.capture_only:
            symbol_results[symbol] = {"captures": captures, "assertions": {"within_run": {}, "cross_run": []}}
            continue

        print(f"\n--- Assertions for {symbol} ---")
        assertion_data = run_assertions_for_symbol(symbol, captures)
        symbol_results[symbol] = {"captures": captures, "assertions": assertion_data}

        sf, _ = count_findings(assertion_data)
        universe_fail += sf

        # Generate per-symbol report
        json_report.generate(
            symbol,
            assertion_data["within_run"],
            assertion_data["cross_run"],
            captures,
            report_dir / symbol,
        )
        markdown_summary.generate(
            symbol,
            assertion_data["within_run"],
            assertion_data["cross_run"],
            captures,
            report_dir / symbol,
        )

    if args.capture_only:
        print(f"\nCapture complete. {len(symbols)} symbols, {args.runs} run(s) each. Assertions skipped.")
        return

    # Generate consolidated universe report
    _generate_universe_report(symbol_results, run_ts, report_dir, args.runs)

    print_universe_summary(symbol_results, run_ts, report_dir, args.runs)

    sys.exit(1 if universe_fail > 0 else 0)


def _generate_universe_report(symbol_results: dict, run_ts: str, report_dir: Path, num_runs: int):
    """Write consolidated universe summary.md and assertions.json."""
    report_dir.mkdir(parents=True, exist_ok=True)

    # Consolidated assertions.json
    consolidated = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "run_timestamp": run_ts,
        "runs_per_symbol": num_runs,
        "symbols": {},
    }

    total_fail = 0
    total_warn = 0

    for symbol, data in symbol_results.items():
        sf, sw = count_findings(data["assertions"])
        total_fail += sf
        total_warn += sw
        consolidated["symbols"][symbol] = {
            "status": "FAIL" if sf > 0 else "PASS",
            "failures": sf,
            "warnings": sw,
            "within_run": {
                str(k): v for k, v in data["assertions"]["within_run"].items()
            },
            "cross_run": data["assertions"]["cross_run"],
        }

    consolidated["overall_status"] = "FAIL" if total_fail > 0 else "PASS"
    consolidated["summary"] = {"failures": total_fail, "warnings": total_warn}

    with open(report_dir / "assertions.json", "w", encoding="utf-8") as f:
        json.dump(consolidated, f, indent=2, default=str)

    # Consolidated summary.md
    lines = []
    lines.append(f"# QA Harness Universe Run - {run_ts}")
    lines.append("")
    lines.append(f"## Status: {'FAIL' if total_fail > 0 else 'PASS'}")
    lines.append("")
    lines.append(f"- **Symbols:** {', '.join(sorted(symbol_results.keys()))}")
    lines.append(f"- **Runs per symbol:** {num_runs}")
    lines.append(f"- **Total failures:** {total_fail}")
    lines.append(f"- **Total warnings:** {total_warn}")
    lines.append("")

    failed_symbols = [s for s, d in symbol_results.items() if count_findings(d["assertions"])[0] > 0]
    passed_symbols = [s for s, d in symbol_results.items() if count_findings(d["assertions"])[0] == 0]

    if failed_symbols:
        lines.append("## Failed Symbols")
        lines.append("")
        for symbol in sorted(failed_symbols):
            data = symbol_results[symbol]
            sf, sw = count_findings(data["assertions"])
            lines.append(f"### {symbol} - {sf} failures, {sw} warnings")
            lines.append("")

            # List failed assertions with sample messages
            for findings in data["assertions"]["within_run"].values():
                for f in findings:
                    if f["status"] == "FAIL":
                        lines.append(f"- [{f['assertion']}] {f['message']}")
            for f in data["assertions"]["cross_run"]:
                if f["status"] == "FAIL":
                    lines.append(f"- [{f['assertion']}] {f['message']}")
            lines.append("")

    if passed_symbols:
        lines.append("## Passed Symbols")
        lines.append("")
        for s in sorted(passed_symbols):
            lines.append(f"- {s}")
        lines.append("")

    with open(report_dir / "summary.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    main()
