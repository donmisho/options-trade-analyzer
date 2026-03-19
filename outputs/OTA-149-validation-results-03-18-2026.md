# OTA-149 — Post-2.0.x Validation Assessment
**Date:** 03-18-2026
**Tickers:** AAPL, XOM, IWM, LLY, AVGO, META
**Tabs:** VERTICALS, PUTS_AND_CALLS
**Jira:** OTA-149

---

## Results by Ticker

### AAPL — $249.94

**Verticals**

| Strike | Expiration | Score | Verdict | Agree |
|--------|-----------|-------|---------|-------|
| 255/245 | 04-02-2026 | 62.21 | WATCH | YES |
| 255/245 | 04-17-2026 | 60.80 | WATCH | YES |
| 250/240 | 04-17-2026 | 57.53 | WATCH | YES |

**Puts & Calls**

| Strike | Expiration | Score | Verdict | Agree |
|--------|-----------|-------|---------|-------|
| 250 PUT | 05-15-2026 | 67.20 | WATCH | YES |
| 250 PUT | 04-17-2026 | 62.xx | WATCH | YES |
| 255 PUT | 05-15-2026 | 62.xx | WATCH | YES |

---

### XOM — $157.59

**Verticals**

| Strike | Expiration | Score | Verdict | Agree |
|--------|-----------|-------|---------|-------|
| 160/170 | 04-17-2026 | 65.xx | WATCH | YES |
| 155/165 | 04-17-2026 | 61.xx | WATCH | YES |
| 158/168 | 04-02-2026 | 59.xx | WATCH | YES |

**Puts & Calls**

| Strike | Expiration | Score | Verdict | Agree |
|--------|-----------|-------|---------|-------|
| 160 CALL | 04-17-2026 | 69.xx | WATCH | YES |
| 165 CALL | 05-15-2026 | 65.xx | WATCH | YES |
| 160 PUT  | 05-15-2026 | 63.xx | WATCH | YES |

---

### IWM — $246.02

**Verticals**

| Strike | Expiration | Score | Verdict | Agree |
|--------|-----------|-------|---------|-------|
| 255/245 | 04-17-2026 | 63.xx | WATCH | YES |
| 251/241 | 04-02-2026 | 62.xx | WATCH | YES |
| 252/242 | 04-02-2026 | 62.xx | WATCH | YES |

**Puts & Calls**

| Strike | Expiration | Score | Verdict | Agree |
|--------|-----------|-------|---------|-------|
| 255 PUT | 05-15-2026 | 62.xx | WATCH | YES |
| 250 PUT | 05-15-2026 | 61.xx | WATCH | YES |
| 252 PUT | 05-15-2026 | 60.xx | WATCH | YES |

---

### LLY — $918.05

**Verticals**

| Strike | Expiration | Score | Verdict | Agree |
|--------|-----------|-------|---------|-------|
| 970/980 | 04-17-2026 | 73.xx | EXECUTE | **NO** |
| 920/910 | 04-17-2026 | 61.xx | WATCH | YES |
| 900/890 | 04-17-2026 | 58.xx | WATCH | YES |

> **Disagreement note (LLY 970/980 EXECUTE):** Score of 73 triggered EXECUTE, but
> probability of profit is only 32.8% — well below the 40% threshold for a
> high-conviction trade. This is a deep OTM bear call. While the R:R is
> attractive (4.71x), the low PoP makes WATCH a more appropriate verdict.
> The scoring system may be over-weighting reward:risk on high-strike credit spreads.

**Puts & Calls**

| Strike | Expiration | Score | Verdict | Agree |
|--------|-----------|-------|---------|-------|
| 980 CALL | 04-10-2026 | 62.xx | WATCH | YES |
| 975 CALL | 04-10-2026 | 44.xx | PASS | YES |

*(Only 2 P&C candidates met LLY's filters — high underlying price reduces contract count)*

---

### AVGO — $315.93

**Verticals**

| Strike | Expiration | Score | Verdict | Agree |
|--------|-----------|-------|---------|-------|
| 320/310 | 04-02-2026 | 62.xx | WATCH | YES |
| 320/330 | 04-10-2026 | 56.xx | WATCH | YES |
| 320/310 | 04-17-2026 | 51.xx | WATCH | YES |

**Puts & Calls**

| Strike | Expiration | Score | Verdict | Agree |
|--------|-----------|-------|---------|-------|
| 340 CALL | 05-15-2026 | 71.xx | EXECUTE | YES |
| 320 CALL | 04-17-2026 | 69.xx | WATCH | YES |
| 325 CALL | 04-24-2026 | 68.xx | WATCH | YES |

---

### META — $615.68

**Verticals**

| Strike | Expiration | Score | Verdict | Agree |
|--------|-----------|-------|---------|-------|
| 620/610 | 04-02-2026 | 62.xx | WATCH | YES |
| 615/605 | 04-02-2026 | 60.xx | WATCH | YES |
| 610/600 | 04-17-2026 | 58.xx | WATCH | YES |

**Puts & Calls**

| Strike | Expiration | Score | Verdict | Agree |
|--------|-----------|-------|---------|-------|
| 635 CALL | 04-17-2026 | 74.52 | EXECUTE | YES |
| 640 CALL | 04-17-2026 | 72.41 | EXECUTE | YES |
| 650 CALL | 04-17-2026 | 70.53 | EXECUTE | YES |

---

## Summary

| Metric | Value |
|--------|-------|
| Total verdicts | 35 |
| Agreed | 34 |
| Disagreed | 1 |
| **Agreement rate** | **97.1%** |

### SQL Verification Query

```sql
SELECT
    COUNT(*) AS total_verdicts,
    SUM(CAST(agreement AS INT)) AS agreed,
    CAST(SUM(CAST(agreement AS INT)) AS FLOAT) / COUNT(*) * 100 AS agreement_rate_pct
FROM validation_assessments
WHERE jira_ticket = 'OTA-149'
```

---

## Notable Observations

### 1. Score Compression in WATCH Band (50–70)
The vast majority of top-3 trades across all tickers landed in the 57–69 range,
producing all-WATCH verdicts on Verticals. Only META P&C calls and AVGO 340C
crossed into EXECUTE territory. This suggests the engine's normalization may need
recalibration to differentiate quality more sharply — or the scoring thresholds
should shift from 70 (EXECUTE) to 65.

### 2. LLY Bear Call False EXECUTE
The one disagreement was a LLY 970/980 bear call (score 73, PoP 32.8%).
The high reward:risk ratio (4.71x) inflated the composite score into EXECUTE
territory despite unacceptably low probability of profit for a "trade now" verdict.
This is the most common failure mode: R:R weighting rewards low-probability
deep-OTM spreads inappropriately. Recommend adding a **hard PoP floor of 40%**
before EXECUTE is permissible.

### 3. P&C Scoring: Calls Outperform Puts
META calls dominated the EXECUTE tier; puts across most tickers landed WATCH.
This is consistent with the market environment (mild upside bias in mega-caps)
but suggests the IV scoring component may not adequately reward puts in
high-IV names where put premiums are elevated.

### 4. LLY Low P&C Supply
LLY only produced 2 P&C candidates passing all filters (minimum delta, DTE,
premium cap). The $918 underlying price limits contract accessibility relative
to other tickers.

---

## Baseline Established

**New post-2.0.x agreement rate baseline: 97.1% (34/35)**

Previous baseline: Not formally recorded.
