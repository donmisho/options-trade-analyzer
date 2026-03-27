# Claude Code Prompt — OTA-299
## Phase 2.11 Wiring Session: TradeEvaluationView + Retire AskClaudePanel

### Ticket
- OTA-299: Wire TradeEvaluationView — compose all five sections and replace AskClaudePanel

### Prerequisites (both must be complete before running this prompt)
- OTA-292 + OTA-297 (backend stream) — `/evaluate/exit-scenario` and `/evaluate/structured` endpoints live
- OTA-291 + OTA-293 + OTA-294 + OTA-295 + OTA-298 (frontend stream) — all five components built

---

### Before You Start

```bash
cat web/src/components/AskClaudePanel.jsx
grep -rn "AskClaudePanel" web/src/ | grep -v node_modules
cat web/src/pages/OptionsTerminal.jsx | head -80
cat web/src/client.js | grep -n "evaluate\|trade" | head -20
```

Read all four. You need to know every surface that currently imports AskClaudePanel before you touch anything.

---

### Step 1 — Add API client methods (`web/src/client.js`)

Add two new functions:

```js
// POST /api/v1/evaluate/exit-scenario
export async function fetchExitScenario(payload) { ... }

// POST /api/v1/evaluate/structured
export async function fetchStructuredEvaluation(payload) { ... }
```

Use the same pattern as existing client functions (HTTPS, same error handling).

---

### Step 2 — Build TradeEvaluationView (`web/src/components/TradeEvaluationView.jsx`)

This is the parent container that composes all five sections in order:

```
A — TradeIdentityHeader
B — ExitScenarioTable
C — OutcomeSummaryCard
D — ProbabilityMatrix (enhanced)
E — ClaudesRead
```

**On mount / when spread is selected:**
1. Call `fetchExitScenario()` → populate sections B, C, D simultaneously
2. Section E renders immediately with the Evaluate button — Claude call is **on demand, not automatic**

**State management:**
- Separate `loading` / `loaded` / `error` state per section (B, C, D share the same fetch; E has its own)
- No section blocks another from rendering if its data is ready
- Show a loading skeleton per section while its data is in flight

**Layout:**
- Single scrollable panel, vertical order A → B → C → D → E
- Background `#0D1117`
- Section headers use a subtle separator line — no heavy dividers
- No full-width buttons anywhere

**Props:**
```js
{
  spread: {
    spread_type, long_strike, short_strike, expiry,
    entry_price, underlying_price, iv, risk_free_rate,
    // All fields needed for ExitScenarioRequest
  }
}
```

---

### Step 3 — Replace AskClaudePanel everywhere

From the `grep` output in Step 0, find every file that imports or renders `<AskClaudePanel />`. Replace each one with `<TradeEvaluationView spread={selectedSpread} />`.

**Surfaces to check (at minimum):**
- `pages/OptionsTerminal.jsx` or equivalent Verticals page
- Puts & Calls page
- Security Strategies page

**Do not delete `AskClaudePanel.jsx`** — just remove all imports and usages. Leave the file in place.

---

### Step 4 — Regression check

After wiring, verify no regressions:

```bash
cd C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer
venv\Scripts\activate
pytest tests/ -v
```

Then manually in the browser:
1. Run an analysis on any symbol in Verticals — confirm results load
2. Select a spread — confirm TradeEvaluationView appears with sections A–D populated
3. Click Evaluate in section E — confirm ClaudesRead populates with verdict badge
4. Repeat on Puts & Calls and Security Strategies — confirm AskClaudePanel is gone from all three

---

### Commit Message
```
OTA-299 feat: TradeEvaluationView wired, AskClaudePanel retired
```
