# Claude Code Prompt — Journey Map Test Bug Fixes
# Tickets: OTA-447 (whitespace), OTA-448 (score disconnect), OTA-449 (puts & calls)
# Terminal: Can run in any terminal, independent of watchlist work

---

## Step 0 — Read Context

```bash
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
.\venv\Scripts\Activate.ps1
cat claude_context/CLAUDE.md
cat claude_context/UI-GUIDANCE.md
```

---

## Bug 1 — Expansion Panel Whitespace (OTA-447)

**Problem:** When expanding a trade row on the Trades page, there is a massive blank gap (~500px) between Section A (trade structure summary) and Section B (Exit Scenario Analysis). The content exists in the DOM — it's a CSS layout issue.

**Diagnosis steps:**
1. Open `web/src/` and find the trade expansion panel component
2. Look for the component that renders Sections A through E when a trade row is expanded
3. Inspect for: excessive height on a container, large margin/padding, a hidden element with height, or a flex/grid gap issue
4. The same whitespace bug appears on Strategy pages — check if they share a component

**Fix:** Remove the excessive whitespace. Sections A through E should render contiguously with consistent spacing (8-12px gap between sections max).

**Verify:** 
1. Navigate to Trades → enter AAPL → expand top trade row
2. Section A (trade structure) should flow directly into EXIT SCENARIO ANALYSIS
3. All five sections (A: structure, B: exit scenarios, C: outcome summary, D: probability matrix, E: Claude's Read) should be visible by scrolling through the expansion — no blank gaps
4. Check Strategy pages too — same fix should apply if they share the component

---

## Bug 2 — Claude Evaluation Score Disconnect (OTA-448)

**Problem:** Clicking "Evaluate" on a trade row (AAPL 265/255 Bear Put, table score 60.19) produces Claude's Read showing score **0.00** and verdict **PASS**. The table composite score and the evaluation score are completely disconnected.

**Diagnosis steps:**
1. Find the Evaluate button click handler in the trade expansion component
2. Trace the API call it makes — likely `POST /api/v1/evaluate/trade` or similar
3. Check what data is sent to the backend: is the trade data, strategy context, and score being passed?
4. Check the backend evaluation endpoint: is it receiving the score? Is it computing its own score and ignoring the composite?
5. Check the response parsing: is the frontend reading the score from the correct field in the response?

**Likely causes (check in order):**
- The evaluate endpoint returns a default/placeholder response (score: 0, verdict: "PASS") because the structured evaluation isn't fully wired
- The frontend is reading `response.score` but the backend returns it as `response.evaluation_score` or nested differently
- The strategy alignment logic ("Best Fit") is working but the score computation is not

**Fix:** This may be a wiring issue rather than a logic bug. If the evaluation endpoint is returning placeholder data, document what needs to be built. If it's a field mapping issue, fix the mapping.

**Verify:**
1. Expand a trade row → click Evaluate
2. Claude's Read should show a meaningful score (not 0.00)
3. Verdict should reflect the score: 60+ should be EXECUTE or WAIT, not PASS
4. "Best Fit" strategy should match the strategy pill shown in the trade row

---

## Bug 3 — Puts & Calls No Results (OTA-449)

**Problem:** The "Puts & calls" section on the Trades page shows "No long option candidates found for AAPL" despite AAPL being one of the most liquid options underlyings. Same issue for CAR and other symbols.

**Diagnosis steps:**
1. Find the Puts & Calls data fetch — likely in the Trades page component or a service function
2. Check what API endpoint it calls and what parameters it sends
3. Check the backend endpoint: is it filtering by Trend Rider / Lottery Ticket strategy parameters?
4. Check if the SMA alignment requirement (`REQUIRE SMA ALIGNMENT = On`) is filtering everything out — AAPL showed "Mixed — No Signal" which might fail the alignment check

**Likely causes:**
- The Puts & Calls section only shows results for Trend Rider and Lottery Ticket strategies (which require SMA alignment)
- AAPL has "Mixed — No Signal" which fails the SMA alignment gate
- The filter thresholds (MIN LONG DELTA 0.50, MAX IV RANK 60%) are too restrictive for the current market conditions

**Fix:** 
- If SMA alignment is filtering everything: this may be "working as designed" but the empty state message should explain WHY ("No candidates: SMA alignment required but signal is Mixed")
- If it's a data fetch bug: fix the fetch
- At minimum, improve the empty state message from "No long option candidates found for AAPL" to include the reason (e.g., "No candidates matching Trend Rider filters for AAPL — SMA signal is Mixed (requires aligned)")

**Verify:**
1. Trades page → AAPL → expand "Puts & calls" section
2. Either results appear OR a diagnostic message explains why there are no results

---

## Acceptance Criteria (All Three Bugs)

1. **OTA-447:** Trade expansion panel renders Sections A-E contiguously with no blank gaps
2. **OTA-448:** Evaluate produces a meaningful score and consistent verdict (document if evaluation endpoint needs further work)
3. **OTA-449:** Puts & Calls either shows results or explains why none match

## Commit Message
```
OTA-447, OTA-448, OTA-449: Journey map test bug fixes

- Fix expansion panel whitespace gap between sections (OTA-447)
- Diagnose/fix Claude evaluation score disconnect (OTA-448)
- Fix or improve Puts & Calls empty state messaging (OTA-449)
```
