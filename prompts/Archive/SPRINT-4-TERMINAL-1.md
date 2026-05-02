# Sprint 4 — Terminal 1: Section E Full Wiring + Cleanup

## Session Context

You are executing Sprint 4 of the Experience Framework v3 overhaul for the Options Trade Analyzer.

**Read these files first (in this order):**
1. `UI-GUIDANCE.md` — the visual contract, wins over all other sources
2. `architecture-plan.md` — backend endpoint specs and data flow
3. `CLAUDE.md` — project conventions and house style rules

**Key backend endpoints (all confirmed DONE and live):**
- `POST /api/v1/evaluate/structured` — Claude structured evaluation
- `POST /api/v1/evaluate/follow-up` — follow-up questions
- `POST /api/v1/positions/follow` — create paper position
- `POST /api/v1/positions/take` — create live position
- `POST /api/v1/analyze/probability-matrix` — Black-Scholes matrix

**House style rules (enforce in every change):**
- No `$` prefix on any monetary value
- Monetary display: `##.00` via `.toFixed(2)`
- Dates: `mm-dd-yyyy` via `formatDate()` — never locale strings
- Scores: 0-100, `##.00`, green 70+ / amber 40-69 / red 0-39
- Probabilities: `##.00%` always
- Dark theme CSS variables only — never inline hex
- `var(--bg2)` restricted to filter bars, QuoteBar, pill badge backgrounds only
- Buttons: auto-width with padding, never full-width stretch
- Claude advice badge: WHITE outlined (rgba(255,255,255,0.06) bg, rgba(255,255,255,0.35) border)
- Strategy pills: SP/WG/TR/LT abbreviations with tooltip

---

## Subtask Sequence (execute in order)

### Step 1 — OTA-380: Wire Section E Evaluate button to /evaluate/structured

In `web/src/api/client.js`, confirm `evaluateStructured(payload)` exists (POST /api/v1/evaluate/structured). If missing, add it. Payload: `{ symbol, trade_structure, strategy_keys[], trade_data }`.

In `web/src/components/TradeDetail/SectionE.jsx`, wire the Evaluate button:
- Set loading state (animated dots + context text: "{strategy} · {spread} · Evaluating...")
- Call `evaluateStructured()` with the expanded trade's data and active symbol
- On response, render post-evaluation state:
  - Verdict badge: EXECUTE (green `.vb-exec`), WAIT (amber `.vb-wait`), PASS (red `.vb-pass`)
  - White outlined Claude advice badge: "Best fit: {strategy}" with strategy name in strategy color (SP=amber, WG=green, TR=blue, LT=purple)
  - Trade reference: "{symbol} · {type} · {strikes} · {expiry}" in 9px muted, right-aligned
  - Analysis text: `claude_read` field, 10px #c9d1d9, line-height 1.65
  - Key level callout: var(--bg2) bg, 2px solid amber left border, key price in amber bold + explanation
  - Score: ##.00 format with threshold coloring
- Toggle via local state `evaluationResult`. Pre-eval = Evaluate button only.
- Discard button (neutral outlined) clears back to pre-eval state.

**Commit prefix:** `OTA-380`

### Step 2 — OTA-381: Wire Follow (Paper) and Take Position (Live)

In `client.js`, confirm `followPosition()` and `takePosition()` exist. If missing, add:
- `followPosition(payload)` → POST /api/v1/positions/follow
- `takePosition(payload)` → POST /api/v1/positions/take

In SectionE.jsx, wire both buttons (visible only in post-eval state):
- Follow (Paper): teal outlined (btn-t), calls followPosition with source=PAPER
- Take Position (Live): green outlined (btn-g), calls takePosition with source=LIVE
- Success Toast: "Position followed (Paper) — {symbol} {strikes}" with "View Positions" link to /positions, auto-dismiss 4s
- Error Toast on failure. Buttons remain visible after action.

**Commit prefix:** `OTA-381`

### Step 3 — OTA-382: Wire follow-up input to /evaluate/follow-up

In `client.js`, confirm `evaluateFollowUp(payload)` exists. Payload: `{ symbol, trade_data, original_evaluation, question }`.

In SectionE.jsx:
- Follow-up input (placeholder "Ask a follow-up about this trade...") — visible only in post-eval state
- On Enter, call evaluateFollowUp with evaluation context + question
- Inline loading indicator (dots next to input)
- Response appends below analysis with left border indent (2px var(--border)), question in 9px muted italic above answer
- Multiple follow-ups append sequentially (local array `followUps[]`)
- Input clears after submission

**Commit prefix:** `OTA-382`

### Step 4 — OTA-383: Wire Section D to real ProbabilityMatrix

In `client.js`, confirm `getProbabilityMatrix(payload)` exists. Payload: `{ symbol, current_price, iv, dte, strike_price, spread_width }`.

In `SectionD.jsx`:
- Replace placeholder with `<ProbabilityMatrix data={matrixData} />` (component already exists)
- On trade expansion, call getProbabilityMatrix with trade data
- Loading state: show existing placeholder text while API call in flight
- Fallback: if API fails, show placeholder with error note
- Probabilities display as ##.00%

**Commit prefix:** `OTA-383`

### Step 5 — OTA-388: Delete deprecated files

- Delete `web/src/pages/VerticalsPage.jsx`
- Delete `web/src/pages/LongCallsPage.jsx`
- Remove all imports from App.jsx and routing config
- Keep redirects to /trades if they exist
- Run dev server to confirm no build errors

**Commit prefix:** `OTA-388`

---

## Final Commit

After all steps pass, create a single commit or series of commits:
```
OTA-380 OTA-381 OTA-382 OTA-383 OTA-388 feat: wire Section E evaluation end-to-end, probability matrix, cleanup deprecated pages
```

**Recommended QA level:** Level 2 (touches multiple components across evaluation, positions, and routing)
