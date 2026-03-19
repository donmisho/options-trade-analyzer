# Conservative Options Scan
## Version 5.0
### Updated: 2026-03-05 — R:R framework corrected for credit vs. debit spreads

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

**⚠️ STOCK PRICE AWARENESS (added v4.0):**
Before estimating strikes and premiums, verify each candidate's actual current price
via web search. Many large-cap stocks (CAT, XOM, COST, GOOG) trade significantly
higher than intuitive estimates. Mispriced estimates cascade into wrong strike
selection, wrong premium estimates, and wrong spread width recommendations.
Use financhill.com or Yahoo Finance to confirm live price before building
any spread estimates in the table.

**Spread width scaling by stock price (added v4.0):**
| Stock Price | Recommended Spread Width |
|-------------|--------------------------|
| $20–$50 | $2–$5 |
| $50–$150 | $5–$10 |
| $150–$300 | $10–$20 |
| $300–$500 | $15–$25 |
| $500+ | $25–$50 |

Narrow spreads ($5–$10) on high-priced stocks ($300–$700+) almost never
generate enough credit to meet the 30% of width threshold at conservative
OTM strikes. Flag this risk in the table rather than listing unusable candidates.

---

**Vertical spread candidates:**
- Direction must align with chosen bias
- Prefer credit spreads (bull put, bear call) where setup supports it
- Net delta: ±0.15 to 0.30
- Spread width: scaled to stock price (see table above)

**⚠️ R:R STANDARDS — CREDIT vs. DEBIT (updated v5.0):**

Credit spreads (bear call, bull put) and debit spreads (bear put, bull call) have
fundamentally different R:R profiles and must be evaluated by different standards.
Never apply the same R:R minimum to both — doing so incorrectly rejects valid
credit spread setups.

**Credit spreads (bear call, bull put):**
- These are high-probability, lower-reward-per-dollar structures by design
- The edge comes from winning frequently, not from large per-trade payouts
- Minimum credit ≥ 30% of spread width (ensures you're being paid adequately)
- Minimum PoP ≥ 62% (this is what makes the math work over time)
- Positive expected value required: EV = (PoP × max profit) − ((1−PoP) × max loss) > 0
- Realistic R:R range: 0.35:1 to 0.75:1 — this is acceptable and expected
- A credit spread with 0.50:1 R:R and 68% PoP has positive EV and is a valid trade
- Do NOT reject a credit spread solely because R:R is below 1.5:1

**Debit spreads (bear put, bull call):**
- These are lower-probability, higher-reward structures
- The edge comes from being right directionally, not from frequency
- Maximum cost ≤ 40% of spread width
- Minimum R:R ≥ 1.5:1 (you need to win big enough to offset lower win rate)
- PoP typically 40–55% — acceptable if R:R is strong

**Quick EV check (run this in Phase 2 for every spread):**
EV = (PoP × max profit) − ((1 − PoP) × max loss)
Positive EV = viable. Negative EV = pass, regardless of other factors.

**Covered call candidates (bullish or both bias only):**
- Real share purchase — 100 shares + short OTM call
- Share price $80–$100 (total position $8,000–$10,000)
- Strong fundamental support required — full downside exposure on shares
- Stable to mildly bullish — not trending hard
- Call delta 0.25–0.35
- Premium ≥ 1.5% of stock price per month
- Beta < 1.2 preferred

**Valuation red flag check (added v4.0):**
Before including any candidate, run a quick news check for recent analyst
downgrades, valuation warnings, or earnings-day selloffs. A stock dropping
3–5%+ on a valuation downgrade invalidates the bullish thesis regardless of
technical setup. Flag and remove these candidates.

**Earnings timing — same-day check (added v4.0):**
Check whether any candidate reports earnings TODAY (after close). If so,
flag prominently in the table and recommend waiting until the next session
to enter, after IV normalizes post-report. Do not enter positions on
earnings day regardless of direction.

**Extended move flag (added v4.0):**
For bearish candidates, check how far price has already fallen from the
50-day SMA. If price is already >5% below the 50-day, flag as "extended —
consider waiting for dead cat bounce entry." The best bear spread entries
come when price is just rolling over, not after a large move has occurred.
Same logic applies in reverse for bullish candidates extended above their 50-day.

---

## STEP 3: PHASE 1 OUTPUT

### Market Summary
3–4 sentences. Cover VIX level and percentile, SPY and QQQ trend, and whether
conditions favor credit or debit structures. Be direct.

Credit spreads are favored when VIX is elevated (IV Rank > 50%) — you collect
richer premiums. Debit spreads are favored when IV is low (IV Rank < 35%) —
options are cheaper to buy.

---

### Results Table

Return exactly the number of candidates requested. Apply the bias filter.
Each symbol must be a hyperlink to Yahoo Finance:
`[TICKER](https://finance.yahoo.com/quote/TICKER)`

| # | Security | Symbol | Price | Strategy | Direction | Why | IV Rank | Delta | Est. Credit/Debit | Max Profit | Max Loss | Est. PoP | Est. EV | Confidence |

**Column rules:**
- **Security:** Full name (e.g., "Walmart Inc.", "Invesco QQQ Trust")
- **Symbol:** Hyperlinked to Yahoo Finance
- **Price:** Verified current price — not estimated (added v4.0)
- **Strategy:** Covered Call / Bull Put / Bear Call / Bull Call / Bear Put
- **Direction:** Bullish / Bearish / Neutral
- **Why:** 3–7 words only — specific and tight (e.g., "Bouncing off 50-day support")
- **Est. Credit/Debit:** Rough estimate based on current IV — flagged as estimate
- **Max Profit / Max Loss:** Per contract (×100 shares), using price-appropriate spread width
- **Est. PoP:** Estimated probability of profit based on delta and strike placement
- **Est. EV:** Estimated expected value = (PoP × max profit) − ((1−PoP) × max loss).
  Flag negative EV candidates — do not include them in top rankings.
- **Confidence:** High / Medium / Low — downgrade to Low if spread width concern,
  negative EV, or extended move flag applies

---

### Portfolio Flag
Flag any candidates that match existing portfolio holdings as conviction reinforcements.
Omit this section if none match.

---

### Top 5 Ranking
One sentence each. Rank by positive EV first, then PoP, then thesis clarity.
**#1 — [TICKER]:** [Why it leads the list]

---

## PHASE 1 CLOSE

After the table and rankings, ask:

> "Select up to 5 tickers to explore further. For each one, I'll need:
> 1. Current stock price (confirm live)
> 2. Current bid/ask on the specific option strikes you're considering
> 3. 8, 21, and 50-day SMA values (use financhill.com/stock-price-chart/TICKER-technical-analysis)
> 4. Confirmed earnings date (use wallstreethorizon.com or Yahoo Finance earnings calendar)
> 5. Any news or price movement since the scan
>
> I'll run a full deep-dive on each using only live data."

---

## STEP 4: PHASE 2 — DEEP-DIVE EVALUATION

Run one evaluation block per selected ticker using the live bid/ask the user provides.
Never estimate prices in Phase 2 — use only what the user supplies.

**Pre-screen checklist before building Phase 2 (added v4.0):**
Before running the full evaluation, verify:
- [ ] Earnings date confirmed outside expiration window
- [ ] Stock price confirmed (not estimated)
- [ ] SMA values provided (8, 21, 50-day)
- [ ] Spread width appropriate for stock price
- [ ] No same-day earnings or major catalyst (valuation downgrade, gap down, etc.)

If any item fails, flag it and request the missing data before proceeding.

---

### [TICKER] — [Security Name] — [Strategy] — [Direction]

**⚡ VERDICT: EXECUTE / WAIT / PASS**

---

**1. Thesis vs. Chart Alignment**
- Position relative to 8, 21, and 50-day SMAs
- How extended is price from the 50-day SMA (%)
- If >5% extended in trade direction: flag as chasing, recommend WAIT
- Does current price action confirm or conflict with the thesis?

**2. Risk/Reward Quality (updated v5.0)**
- Identify whether this is a credit or debit spread — apply the correct standard
- **Credit spreads:** Is credit ≥ 30% of spread width? Is PoP ≥ 62%?
  R:R of 0.35–0.75:1 is normal and acceptable. Do not penalize for low R:R alone.
- **Debit spreads:** Is cost ≤ 40% of spread width? Is R:R ≥ 1.5:1?
- **Both:** Calculate EV explicitly and show the math:
  EV = (PoP × max profit) − ((1−PoP) × max loss)
  Positive EV = viable. Negative EV = PASS regardless of other factors.
- Covered calls: net cost basis after premium; annualized yield
- Show the math explicitly for each spread option evaluated

**3. Probability & Expected Move**
- Estimated PoP based on delta and strike placement
- Are strikes sensibly placed relative to the expected move?
- Is this a favorable IV environment for buying or selling premium?
- For credit spreads: is PoP ≥ 62%? If not, flag.
- For debit spreads: is directional conviction strong enough to justify lower PoP?

**4. Red Flags / Alternatives**
- Confirm no earnings within the expiration window
- Covered calls: flag any ex-dividend date within the window (early assignment risk)
- Is the live bid-ask on the options acceptable (< $0.15)?
- If the setup doesn't fully qualify, suggest a better-placed alternative
- Flag if stock is extended and a better entry exists after a relief bounce

**5. Exit Plan**

| Alert | Level | Action |
|-------|-------|--------|
| 🟢 Profit trigger | 50% of max profit | Begin closing (credit spreads decay fast near expiry) |
| 🎯 Full target | 75% of max profit | Close 100% — don't wait for last dollar |
| 🔴 Stop loss (credit) | Spread value = 2× credit received | Close immediately |
| 🔴 Stop loss (debit) | 50% of debit paid | Close immediately |
| ⏰ Time stop | 10 days before expiration | Close if not in profit |
| 📉 Thesis invalidated | Price crosses back through short strike | Exit position |

**Credit spread note:** For credit spreads, the stop loss trigger is when the
spread *value* (what it would cost to close) reaches 2× what you collected.
Example: collected $1.50 credit → close if spread costs $3.00 to buy back.
This caps your loss at roughly 2× the original credit, or ~60% of max loss.

If flat after 10 days: close or roll — do not hold into accelerating theta decay.

---

## VERSION HISTORY
- v4.0 (2026-03-05): Stock price awareness, spread width scaling, extended move flag,
  earnings same-day check, valuation red flag check
- v5.0 (2026-03-05): Corrected R:R framework — separate standards for credit vs. debit
  spreads. Added EV calculation as primary quality gate. Added Est. EV column to Phase 1
  table. Updated stop loss logic for credit spreads. Clarified that low R:R on credit
  spreads is expected and acceptable when PoP and EV criteria are met.
