# Conservative Options Scan
## Version 3.0

---

## STEP 0: OPENING QUESTIONS

Before doing anything else, ask:

**"How many candidates would you like me to scan for?"**
- 10 — Focused shortlist
- 20 — Broader comparison
- 50 — Wide net

**"What bias should I apply?"**
- Bullish only
- Bearish only
- Both

Wait for answers before proceeding.

---

## STEP 1: AUTO-RETRIEVE MARKET CONTEXT

Look up the following via web search before running the scan. Do not ask the user for these:

- Today's date
- VIX: current level and 52-week percentile
- SPY: current price, 5-day trend, position relative to 50-day SMA
- QQQ: current price, 5-day trend, position relative to 50-day SMA

---

## STEP 2: SCAN CRITERIA

**Universe:** U.S. equities and broad ETFs with actively traded options chains

**All candidates must meet:**
- 30–45 DTE options available
- Options volume > 500 contracts/day
- Bid-ask spread < $0.15
- IV Rank 30–70%
- No earnings within the 30–45 day window
- Stock price ≥ $20
- Technically clean chart — not parabolic, not in breakdown

**Vertical spread candidates:**
- Direction must align with chosen bias
- Prefer credit spreads (bull put, bear call) where setup supports it
- Net delta: ±0.15 to 0.30
- Spread width: $2–$10 depending on price
- Credit spreads: premium ≥ 30% of spread width
- Debit spreads: cost ≤ 40% of spread width
- Minimum R:R 1.5:1

**Covered call candidates (bullish or both bias only):**
- Real share purchase — 100 shares + short OTM call
- Share price $80–$100 (total position $8,000–$10,000)
- Strong fundamental support required — full downside exposure on shares
- Stable to mildly bullish — not trending hard
- Call delta 0.25–0.35
- Premium ≥ 1.5% of stock price per month
- Beta < 1.2 preferred

---

## STEP 3: PHASE 1 OUTPUT

### Market Summary
3–4 sentences. Cover VIX level and percentile, SPY and QQQ trend, and whether
conditions favor credit or debit structures. Be direct.

---

### Results Table

Return exactly the number of candidates requested. Apply the bias filter.
Each symbol must be a hyperlink to Yahoo Finance:
`[TICKER](https://finance.yahoo.com/quote/TICKER)`

| # | Security | Symbol | Price | Strategy | Direction | Why | IV Rank | Delta | Est. Credit/Debit | Max Profit | Max Loss | Est. PoP | Confidence |

**Column rules:**
- **Security:** Full name (e.g., "Walmart Inc.", "Invesco QQQ Trust")
- **Symbol:** Hyperlinked to Yahoo Finance
- **Strategy:** Covered Call / Bull Put / Bear Call / Bull Call / Bear Put
- **Direction:** Bullish / Bearish / Neutral
- **Why:** 3–7 words only — specific and tight (e.g., "Bouncing off 50-day support")
- **Est. Credit/Debit:** Rough estimate based on current IV — flagged as estimate
- **Max Profit / Max Loss:** Per contract (×100 shares)
- **Confidence:** High / Medium / Low

---

### Portfolio Flag
Flag any candidates that match existing portfolio holdings as conviction reinforcements.
Omit this section if none match.

---

### Top 5 Ranking
One sentence each. Format:
**#1 — [TICKER]:** [Why it leads the list]

---

## PHASE 1 CLOSE

After the table and rankings, ask:

> "Select up to 5 tickers to explore further. For each one, provide:
> 1. Current bid/ask on the underlying shares
> 2. Current bid/ask on the specific option strike(s) you're considering
> 3. Any news or price movement since the scan
>
> I'll run a full deep-dive on each."

---

## STEP 4: PHASE 2 — DEEP-DIVE EVALUATION

Run one evaluation block per selected ticker using the live bid/ask the user provides.
Never estimate prices in Phase 2 — use only what the user supplies.

---

### [TICKER] — [Security Name] — [Strategy] — [Direction]

**⚡ VERDICT: EXECUTE / WAIT / PASS**

---

**1. Thesis vs. Chart Alignment**
- Position relative to 8, 21, and 50-day SMAs
- How extended is price from the 50-day SMA (%)
- Does current price action confirm or conflict with the thesis?

**2. Risk/Reward Quality**
- Actual R:R based on live bid/ask provided
- Credit spreads: is premium ≥ 30% of spread width?
- Debit spreads: is cost ≤ 40% of spread width?
- Covered calls: net cost basis after premium; annualized yield

**3. Probability & Expected Move**
- Estimated PoP based on delta and strike placement
- Are strikes sensibly placed relative to the expected move?
- Is this a favorable IV environment for buying or selling premium?

**4. Red Flags / Alternatives**
- Confirm no earnings within the expiration window
- Covered calls: flag any ex-dividend date within the window (early assignment risk)
- Is the live bid-ask on the options acceptable (< $0.15)?
- If the setup doesn't fully qualify, suggest a better-placed alternative

**5. Exit Plan**

| Alert | Level | Action |
|-------|-------|--------|
| 🟢 Profit trigger | 75% of max profit | Begin closing |
| 🎯 Full target | Max profit × 0.75 | Close 100% |
| 🔴 Stop loss | 50% of debit paid | Close immediately |
| ⏰ Time stop | 10 days before expiration | Close if not in profit |
| 📉 Thesis invalidated | Key SMA or support level | Exit position |

If flat after 10 days: close or roll — do not hold into accelerating theta decay.
