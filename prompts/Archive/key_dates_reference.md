# Options Trading — Key Dates Reference
## Last Updated: 2026-03-05

---

## HOW TO USE THIS FILE

This file tracks earnings dates, ex-dividend dates, and other
key events for active scan candidates. Before entering any trade,
confirm the relevant date has not changed.

**App logic (when built):**
- On first scan of a ticker: fetch and store earnings date
- On subsequent scans: check if stored date has passed → re-fetch if so
- Sources:
  - Earnings: https://www.wallstreethorizon.com/[company]-earnings-calendar
  - SMAs: https://financhill.com/stock-price-chart/TICKER-technical-analysis
  - Dividends: https://finance.yahoo.com/quote/TICKER

---

## EARNINGS DATES

| Ticker | Company | Next Earnings | Time | Confirmed? | Source | Last Checked |
|--------|---------|---------------|------|------------|--------|--------------|
| COST | Costco Wholesale | 2026-03-05 | After Close | ✅ Yes | wallstreethorizon | 2026-03-05 |
| CAT | Caterpillar Inc | 2026-04-23 | Before Open | ✅ Yes | tipranks | 2026-03-05 |
| GOOG | Alphabet Class C | 2026-04-28 | TBD | ✅ Yes | wallstreethorizon | 2026-03-05 |
| XOM | Exxon Mobil | TBD | TBD | ❌ Not checked | — | — |
| WMT | Walmart Inc | TBD | TBD | ❌ Not checked | — | — |
| QQQ | Invesco QQQ Trust | N/A — ETF | — | N/A | — | — |
| SPY | SPDR S&P 500 ETF | N/A — ETF | — | N/A | — | — |

---

## ACTUAL PRICES DISCOVERED (vs scan estimates)

Track these to improve future scan accuracy.

| Ticker | Scan Estimate | Actual Price | Delta | Date |
|--------|--------------|--------------|-------|------|
| XOM | ~$130 | $149.90–$150.21 | +$20 | 2026-03-05 |
| WMT | ~$95 | $123.29 | +$28 | 2026-03-05 |
| GOOG | ~$175 | $300.18–$300.26 | +$125 | 2026-03-05 |
| CAT | ~$385 | $700.00 | +$315 | 2026-03-05 |
| COST | ~$970 | Not confirmed | — | — |

**Note:** Large price discrepancies caused spread width mismatches.
See v4.0 prompt for spread width scaling table by price tier.

---

## TRADE DECISIONS — SESSION LOG

| Date | Ticker | Strategy | Decision | Reason |
|------|--------|----------|----------|--------|
| 2026-03-05 | WMT | Covered Call | ❌ PASS | Analyst downgrade, -4.3% valuation selloff |
| 2026-03-05 | CAT | Bull Put | ❌ PASS | $700 stock, $10 spreads too thin (<30% credit) |
| 2026-03-05 | XOM | Bull Put | ❌ PASS | $150 stock, spreads too thin at conservative OTM strikes |
| 2026-03-05 | COST | Bull Put | ⏳ WAIT | Earnings today after close — revisit 2026-03-06 |
| 2026-03-05 | GOOG | Bear Put 295/285 | ⏳ WAIT | Price extended 6.6% below 50-day, better entry on bounce to ~$306–308 |

---

## SMA REFERENCE — LAST KNOWN VALUES

Fetch fresh values before each session. Sources:
- https://financhill.com/stock-price-chart/TICKER-technical-analysis

| Ticker | 8-day SMA | 20/21-day SMA | 50-day SMA | Price vs 50d | Date |
|--------|-----------|---------------|------------|--------------|------|
| GOOG | $308.35 | $310.78 | $320.41 | -6.3% below | 2026-03-05 |
| QQQ | ~$607 | ~$609 | $615.76 | -0.9% below | 2026-03-05 |
| SPY | ~$687 | ~$688 | $687.78 | ~flat | 2026-03-05 |

---

## USEFUL LINKS

| Purpose | URL Pattern |
|---------|-------------|
| SMA / technicals | `https://financhill.com/stock-price-chart/TICKER-technical-analysis` |
| Earnings dates | `https://www.wallstreethorizon.com/COMPANY-earnings-calendar` |
| Yahoo earnings calendar | `https://finance.yahoo.com/calendar/earnings?symbol=TICKER` |
| Yahoo quote | `https://finance.yahoo.com/quote/TICKER` |
| Options chain | `https://finance.yahoo.com/quote/TICKER/options/` |

---

## PENDING FOR NEXT SESSION (2026-03-06)

- [ ] COST — check post-earnings price and IV. If stock holds/gaps up, evaluate bull put spread
- [ ] GOOG — check if price has bounced toward $306–308. If so, re-evaluate 295/285 bear put
- [ ] XOM — consider wider spread ($10–$15 wide) at strikes further OTM
- [ ] Find 2–3 new candidates in $50–$150 price range where $5–$10 spreads work cleanly
