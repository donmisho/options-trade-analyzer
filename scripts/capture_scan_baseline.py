"""
OTA-759 — before/after scan capture for /analyze/verticals + /analyze/long-calls.

Captures the two scan endpoints for AMZN + MSFT against a running backend and
writes one JSON file per run, plus a compact stdout summary for eyeballing the
before/after delta. NOT committed as a test — a manual verification aid.

Usage (run against a LOCAL backend you control, with the reseeded dev engine):

    # 1. Baseline on the pre-OTA-759 code:
    git stash push -- app/api/analysis_routes.py
    #    (start backend), then:
    python scripts/capture_scan_baseline.py before

    # 2. After (restore the change, restart backend):
    git stash pop
    #    (restart backend), then:
    python scripts/capture_scan_baseline.py after

    # 3. Compare qa-harness/captures/ota759/{before,after}-*.json

Config via env:
    OTA_BASE_URL   default https://127.0.0.1:8000
    OTA_COOKIE     session cookie value if auth is enforced (else SKIP_AUTH on backend)
"""

import json
import os
import sys
from datetime import datetime, timezone

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE = os.getenv("OTA_BASE_URL", "https://127.0.0.1:8000").rstrip("/")
COOKIE = os.getenv("OTA_COOKIE")
SYMBOLS = ["AMZN", "MSFT"]
OUT_DIR = os.path.join("qa-harness", "captures", "ota759")


def _headers():
    h = {"Content-Type": "application/json"}
    if COOKIE:
        h["Cookie"] = COOKIE
    return h


def _post(path: str, payload: dict) -> dict:
    r = requests.post(
        f"{BASE}{path}", json=payload, headers=_headers(), verify=False, timeout=120
    )
    return {"status": r.status_code, "body": _safe(r)}


def _safe(r):
    try:
        return r.json()
    except Exception:
        return {"_text": r.text[:2000]}


def _summary(tag: str, body: dict, list_key: str):
    if not isinstance(body, dict):
        return f"{tag}: non-dict response"
    rows = body.get(list_key) or []
    scores = [x.get("composite_score") for x in rows if x.get("composite_score") is not None]
    verdicts = {}
    for x in rows:
        verdicts[x.get("verdict")] = verdicts.get(x.get("verdict"), 0) + 1
    top = max(scores) if scores else None
    return (
        f"{tag}: {len(rows)} rows | total_valid={body.get('total_valid')} | "
        f"top_score={top} | verdicts={verdicts}"
    )


def main():
    label = sys.argv[1] if len(sys.argv) > 1 else "run"
    os.makedirs(OUT_DIR, exist_ok=True)
    capture = {"label": label, "base_url": BASE, "symbols": {}}
    print(f"=== OTA-759 scan capture [{label}] against {BASE} ===")
    for sym in SYMBOLS:
        v = _post("/api/v1/analyze/verticals", {"symbol": sym})
        lc = _post("/api/v1/analyze/long-calls", {"symbol": sym, "option_types": ["call", "put"]})
        capture["symbols"][sym] = {"verticals": v, "long_calls": lc}
        print(f"\n[{sym}]")
        print(" ", _summary("verticals ", v["body"], "spreads") if v["status"] == 200 else f"verticals  HTTP {v['status']}: {v['body']}")
        print(" ", _summary("long-calls", lc["body"], "calls") if lc["status"] == 200 else f"long-calls HTTP {lc['status']}: {lc['body']}")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = os.path.join(OUT_DIR, f"{label}-{stamp}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(capture, f, indent=2, default=str)
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
