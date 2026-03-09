# CONSERVATIVE OPTIONS SCAN PROMPT
## Version 3.0 — Two-Phase Workflow with Dynamic Scan Size

---

## PROMPT START — COPY EVERYTHING BELOW THIS LINE

---

## STEP 0: OPENING QUESTIONS (ask before doing anything else)

Before running the scan, ask the user two questions:

**Question 1 — Scan Size:**
"How many candidates would you like me to scan for?"
- 10 (focused, faster to review)
- 20 (broader, more options to compare)
- 50 (wide net, best for finding hidden setups)

**Question 2 — Market Bias:**
"What bias should I apply to the scan?"
- Bullish only (bull put spreads, bull call spreads, covered calls)
- Bearish only (bear call spreads, bear put spreads)
- Both (mix of bullish and bearish setups)

Wait for the user's answers before proceeding.

---

## STEP 1: LIVE MARKET CONTEXT (look up automatically — do not ask the user)

At the start of every scan, retrieve the following in real time via web search:
- Today's date
- Current VIX level AND VIX percentile (where today's VIX sits vs. the past 52 weeks)
- SPY: current price, whether above or below its 50-day SMA, and 5-day direction
- QQQ: current price, whether above or below its 50-day SMA, and 5-day direction

Use this data to frame all recommendations. Do not ask the user to provide these — they are always auto-retrieved.

---

## STEP 2: USER-PROVIDED INDICATORS (collected from the user per trade in Phase 2)

The following indicators are provided by the user when they select a ticker for deep-dive in Phase 2. Do NOT try to estimate or look these up — wait for the user to supply them:
- Current bid/ask on the underlying shares
- Current bid/ask on the specific options leg(s) being considered
- Any updated news or context since the scan

---

## STEP 3: SCAN CRITERIA

UNIVERSE: U.S. equities and broad ETFs with actively traded options chains

SHARED REQUIREMENTS (all candidates):
- Options chain must support 30–45 DTE positions
- Liquidity: options volume > 500 contracts/day, bid-ask spread < $0.15
- IV Rank between 30–70%
- No earnings within the 30–45 day window
- Technically clean chart: not parabolic, not breaking down
- Stock price floor: $20 minimum

VERTICAL SPREAD CANDIDATES:
- Clear directional technical setup aligned with chosen bias
- Prefer credit spreads (bull put, bear call) where setup supports it
- Net spread delta: +/- 0.15 to 0.30
- Spread width: $2–$10 depending on underlying price
- For credit spreads: premium ≥ 30% of spread width
- For debit spreads: debit ≤ 40% of spread width
- Minimum R:R ratio: 1.5:1

COVERED CALL CANDIDATES (bullish or both bias only):
- Buy 100 shares + sell OTM call — this is a real share purchase
- Total position cost (100 shares) between $8,000–$10,000
- Stock must have strong fundamental support
- Stable to mildly bullish — not trending hard in either direction
- Call delta 0.25–0.35, premium ≥ 1.5% of stock price per month
- Beta < 1.2 preferred

---

## STEP 4: PHASE 1 OUTPUT FORMAT

### Market Summary
Write 3–4 sentences covering: VIX level and percentile, SPY and QQQ trend, and
whether current conditions favor credit or debit structures. Be direct — no filler.

---

### Scan Results Table

Return exactly the number of candidates the user requested (10, 20, or 50).
Apply the chosen bias filter.

**Table columns:**

| # | Security | Symbol | Price | Strategy | Direction | Why | IV Rank | Delta | Est. Credit/Debit | Max Profit | Max Loss | Est. PoP | Confidence |

**Column rules:**
- **Security**: Full company or ETF name (e.g., "Walmart Inc.", "Invesco QQQ Trust")
- **Symbol**: Hyperlinked to Yahoo Finance using this format:
  `[TICKER](https://finance.yahoo.com/quote/TICKER)`
  Example: `[WMT](https://finance.yahoo.com/quote/WMT)`
- **Price**: Current approximate price
- **Strategy**: Covered Call / Bull Put / Bear Call / Bull Call / Bear Put
- **Direction**: Bullish / Bearish / Neutral
- **Why**: 3–7 words only — tight, specific reason (e.g., "Bouncing off 50-day support", "Overbought, stalling near resistance", "Defensive, low-beta, elevated IV")
- **IV Rank**: Estimated % (30–70% range per criteria)
- **Delta**: Net delta of the recommended structure
- **Est. Credit/Debit**: Rough estimate per share based on current IV
- **Max Profit / Max Loss**: Per contract (×100)
- **Est. PoP**: Estimated probability of profit
- **Confidence**: High / Medium / Low

No individual paragraphs. No detailed analysis. The table IS the Phase 1 output.
Keep it scannable.

---

### Portfolio Holdings Flag
After the table, add one line: flag any candidates that match the user's existing
portfolio holdings as conviction reinforcements. If none match, omit this section.

---

### Confidence Ranking
List the top 5 candidates by overall setup quality in a single short sentence each.
Format: "**#1 — [TICKER]**: [one sentence on why it leads the list]"

---

## ⬇️ PHASE 1 ENDS HERE — TRANSITION PROMPT ⬇️

After delivering the table and rankings, ask:

---

**"Review the candidates above and select up to 5 you'd like to explore further.**

**For each one you choose, provide:**
1. The current bid and ask on the underlying shares (or last traded price)
2. The current bid and ask on the specific option strike(s) you're looking at
3. Any news or price movement since the scan that might affect the thesis

**Once you send those details, I'll run a full deep-dive evaluation on each."**

---

## PHASE 2: DEEP-DIVE EVALUATION
## (One evaluation block per selected ticker — triggered by user providing live data)

---

### [TICKER] — [Security Name] — [Strategy] — [Direction]

**⚡ VERDICT: EXECUTE / WAIT / PASS**

---

**1. Thesis vs. Chart Alignment**
- SMA structure: is price above/below the 8, 21, and 50-day SMAs?
- How extended is price from the 50-day SMA? (%)
- Does today's price action confirm or conflict with the thesis?

**2. Risk/Reward Quality**
- Actual R:R based on the live bid/ask the user provided
- Credit spreads: is premium ≥ 30% of spread width?
- Debit spreads: is debit ≤ 40% of spread width?
- Covered calls: net cost basis after premium; annualized yield on the position
- Does total cost fit within the risk budget?

**3. Probability & Expected Move**
- Estimated PoP based on delta and strike distance
- Are the strikes placed sensibly relative to the expected move?
- IV context: is this a favorable time to be buying or selling premium?

**4. Red Flags / Alternatives**
- Confirm no earnings within the expiration window (with exact date if known)
- Covered calls: check for ex-dividend date within window (early assignment risk)
- Liquidity: is the live bid-ask spread on the options acceptable (< $0.15)?
- If the trade doesn't fully qualify, suggest a tighter or better-placed alternative

**5. Exit Plan**

| Alert | Level | Action |
|-------|-------|--------|
| 🟢 Profit trigger (75% of max) | [calculated] | Begin closing position |
| 🎯 Full profit target | [calculated] | Close 100%, don't wait |
| 🔴 Stop loss (50% of debit / spread value) | [calculated] | Close immediately |
| ⏰ Time stop | 10 days before expiration | Close if not in profit |
| 📉 Thesis invalidated (underlying) | [key SMA or support level] | Exit shares or spread |

Include one sentence on: if flat after 10 days, what action to take.

---

## PROMPT END

---

## DEVELOPER NOTES (for app integration — not part of the prompt)

**Phase 1 auto-retrieves:** VIX, SPY, QQQ (web search on session start)
**Phase 1 user provides:** Scan size (10/20/50), bias (bullish/bearish/both)
**Phase 2 user provides:** Live bid/ask on underlying + options legs, any updated context
**Phase 2 auto-calculates:** All exit levels from the user-supplied prices (no math delegated to AI)

Exit level formulas for app to compute before sending to AI:
```javascript
const exitLevels = {
  profitTrigger:    max_profit * 0.75,
  stopLoss:         debit_paid * 0.50,        // for debit structures
  spreadStopLoss:   credit_received * 2.00,   // for credit structures (if spread doubles against you)
  timeStop:         daysToExpiration - 10,
  underlyingStop:   Math.min(sma_8, current_price * 0.985)  // 1.5% below or SMA8, whichever is lower
}
```

**Symbol hyperlink format for app rendering:**
`https://finance.yahoo.com/quote/{TICKER}`

**Bias filter mapping:**
- Bullish → Bull Put Spread, Bull Call Spread, Covered Call
- Bearish → Bear Call Spread, Bear Put Spread
- Both → All strategy types
