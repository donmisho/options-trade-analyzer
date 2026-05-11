# OTA-627 — Strategies declare compatible structures, not a single structure

## Deployment context
- Deployment: **D2**
- This terminal: **T1**
- Concurrent terminals: T2 (`OTA-632` Trades drawer dynamic strategies — depends on T1 commit)
- Cross-terminal dependencies: T2 must NOT start its Phase 2 (code change) until this terminal commits. T2 may run Phase 1 (read-only discovery) concurrently.

## Required reading
Before any code changes:

```
cat claude_context/CLAUDE.md
cat claude_context/architecture-plan.md
cat claude_context/business-rules.md
cat claude_context/UI-GUIDANCE.md
```

Plus:

```
cat web/src/strategy-configs/index.js
cat web/src/strategy-configs/steady-paycheck.config.js
cat web/src/strategy-configs/weekly-grind.config.js
cat web/src/strategy-configs/trend-rider.config.js
cat web/src/strategy-configs/lottery-ticket.config.js
cat web/src/pages/TradesPage.jsx                     # lines 41-42 hold VERT_STRATEGY_KEYS / CALLS_STRATEGY_KEYS
grep -rn "trade_structure" web/src/ | head -50       # inventory all consumers
grep -rn "trade_structure" app/                      # backend consumers
```

## Relevant Context — Do Not Deviate Without Escalation

**Source: business-rules.md § Strategy vs trade structure**
A strategy is a thesis lens (when to be in market, what risk profile, what edge to harvest). A trade structure is the mechanical expression. These are orthogonal. Trend Rider can be expressed as long calls OR bull-call debit spreads OR bull-put credit spreads — same thesis, different risk/reward shapes.

**Source: business-rules.md § Spread-type vocabulary**
Per-spread-type identifiers (not category groupings). The canonical identifiers are: `bull_put_credit`, `bear_call_credit`, `bull_call_debit`, `bear_put_debit`, `long_call`, `long_put`, `iron_condor`, `calendar_call`, `diagonal_put`, etc. Coarser groupings like "credit spreads" are derived UI filters only. This vocabulary is shared with OTA-451 (pipeline-layer) and OTA-618 (agent-prompt-layer).

**Source: architecture-plan.md § Pattern — single source of truth for strategy metadata**
The strategy registry at `web/src/strategy-configs/index.js` is the SoT. Every consumer imports from here; no consumer redeclares strategy keys or compatible structures. Backend reads the same shape via API or shared schema.

**Source: CLAUDE.md § House style**
Strategy abbreviations SP/WG/TR/LT remain unchanged in display (strategy taxonomy rename is a future epic). Pills with hover tooltips.

**Source: CLAUDE.md § Cost guardrail**
Any refresh that triggers more than one Claude API call must show a confirmation dialog. Not directly in this prompt's scope; verify no new evaluation calls are introduced.

---

## Scope

### 1. Strategy config files — replace `trade_structure` with `compatible_structures`

In each of:

- `web/src/strategy-configs/steady-paycheck.config.js`
- `web/src/strategy-configs/weekly-grind.config.js`
- `web/src/strategy-configs/trend-rider.config.js`
- `web/src/strategy-configs/lottery-ticket.config.js`

Replace `trade_structure: 'X'` with `compatible_structures: [array]` using these initial values (trader-approved):

```javascript
// steady-paycheck.config.js
compatible_structures: ['bull_put_credit', 'bear_call_credit']

// weekly-grind.config.js
compatible_structures: ['bull_put_credit', 'bear_call_credit']

// trend-rider.config.js
compatible_structures: ['long_call', 'long_put', 'bull_call_debit', 'bear_put_debit']

// lottery-ticket.config.js
compatible_structures: ['long_call', 'long_put']
```

### 2. Strategy registry — derived helpers

At `web/src/strategy-configs/index.js`:

- The registry itself is already dynamic (iterates configs). Confirm and preserve.
- **Add a derived map** computed from `SCORECARD_STRATEGIES` that lets consumers ask "which strategy keys are compatible with structure X?" — e.g., `getStrategiesForStructure(spread_type) → [strategy_keys]`.
- **Add a derived map** for the reverse direction — `getCompatibleStructures(strategy_key) → [spread_types]`. (This is just a passthrough to the config field, exported for convenience.)
- **No hardcoded enumeration** of keys or structures in `index.js`. Everything derives from the configs.

### 3. Replace `VERT_STRATEGY_KEYS` / `CALLS_STRATEGY_KEYS` at TradesPage.jsx:41-42

Currently these are hardcoded:

```javascript
const VERT_STRATEGY_KEYS = ['steady-paycheck', 'weekly-grind'];
const CALLS_STRATEGY_KEYS = ['trend-rider', 'lottery-ticket'];
```

Replace with derivations:

```javascript
const VERT_STRATEGY_KEYS = getStrategiesForStructure('bull_put_credit')
  .concat(getStrategiesForStructure('bear_call_credit'));
const CALLS_STRATEGY_KEYS = getStrategiesForStructure('long_call')
  .concat(getStrategiesForStructure('long_put'));
```

Or a cleaner equivalent using a structure-category helper. Adding a strategy or changing its compatible structures must not require editing `TradesPage.jsx`.

### 4. Backend consumers (Phase 1 discovers all callers)

Inventory backend code that reads `trade_structure` from a strategy. Likely surfaces:

- `app/analysis/` strategy scorers — if they read a single `trade_structure`, change to read `compatible_structures` and treat as a membership check.
- `app/api/evaluation_routes.py` — if the strategy_spec assembly (added in OTA-618) referenced a temporary mapping, **remove the OTA-627 TODO** and read directly from the strategy config (via API or shared schema).
- Any `app/analysis/hard_gates/` or pipeline filter that filters trades by strategy structure.

For each surface, update to use the new array semantics.

### 5. Remove the OTA-618 temporary mapping

In `app/api/evaluation_routes.py`, the `strategy_spec` assembly added by OTA-618 included a temporary mapping (marked `# TODO: remove after OTA-627`). Remove it. The assembly now reads from the strategy config via the API or shared schema established in steps 2-4.

If the OTA-618 commit is not yet in (i.e., D1 hasn't shipped), Phase 1 detects this and the Story falls back to "leave a clean integration seam" — escalate to Don rather than proceeding speculatively.

---

## Acceptance criteria

1. Each of the four `*.config.js` files exports `compatible_structures: [array]` with the trader-approved initial values listed above; `trade_structure` is removed from each.
2. `web/src/strategy-configs/index.js` exposes `getStrategiesForStructure(spread_type)` and `getCompatibleStructures(strategy_key)` helpers. Both derive from `SCORECARD_STRATEGIES` with no hardcoded enumeration.
3. `web/src/pages/TradesPage.jsx:41-42` no longer hardcodes strategy keys; derivations live in `strategy-configs/index.js`.
4. `grep -rn "trade_structure" web/src/` returns no matches outside test fixtures.
5. Backend `strategy_spec.compatible_structures` (the OTA-618 payload field) is populated from the SoT, not a temporary mapping. The `# TODO: remove after OTA-627` comment is gone.
6. Adding a fifth strategy or changing one strategy's `compatible_structures` requires editing ONLY that strategy's `.config.js` — no edits to `TradesPage.jsx`, evaluation routes, or scorers. Verified by attempting one such change in a scratch branch (not committed).
7. Regression: run an evaluation of a `bear_put_debit` trade against `trend-rider`. Verdict path includes the structural fit gate (from OTA-618); since `bear_put_debit` is in trend-rider's `compatible_structures`, the gate passes (no PASS verdict from this gate). Verdict is determined by score and soft gates as usual.
8. Regression: run an evaluation of a `bear_put_debit` trade against `steady-paycheck`. Verdict comes back PASS with reason `"structural mismatch: bear_put_debit not in compatible structures for Steady Paycheck"`.

---

## Out of scope

- The Configuration drawer "show all strategies dynamically" change (that's OTA-632, in T2 after this commits).
- Strategy taxonomy rename (cute names → mechanics-based names is a future epic).
- Auto-routing of trades to compatible strategies (mismatches are rejected, not re-routed).
- `short_code` field addition on configs (that's OTA-632's scope).
- New scoring weights or signal definitions.

---

## Verification steps (run before commit)

1. **Phase 1 inventory:** `grep -rn "trade_structure" web/src/ app/` produces a complete list. Confirm nothing outside test fixtures remains after the change.
2. **Manual smoke (dev frontend):**
   - Navigate Trades page → verticals view → cards still render with SP and WG pills (no functional change for current default routes).
   - Navigate Trades page → calls view → cards render with TR and LT pills.
   - No console errors.
3. **Pytest:** any tests that referenced `trade_structure` on a strategy config get updated to `compatible_structures` (membership check, not equality). All existing strategy tests pass.
4. **Architectural confirmation:** the OTA-618 strategy_spec assembly sources `compatible_structures` directly from the strategy config (Phase 1 verifies by inspecting `app/api/evaluation_routes.py`).
5. **Adding-strategy thought experiment** (do not commit): pretend you're adding a fifth strategy `'covered-call': ['covered_call']`. Trace where you'd need to edit — answer should be exactly one new file (`covered-call.config.js`) and one line in the registry's strategy list. If you'd need to edit `TradesPage.jsx` or evaluation routes, the abstraction failed; stop and report.

If any verification fails, stop and report.

---

## Commit instruction

**I have been instructed to commit. Do you approve? (yes / no)**

One commit covers OTA-627.

## Push instruction

**DO NOT push. Single push for Deployment 2 will be coordinated by Don after T2 (OTA-632) also commits.**

## Coordination footer

**STOP until Terminal 2 completes OTA-632.** After this commit, **report to Don** so T2 can begin its Phase 2 (code change). T2's prompt explicitly gates on T1 having committed.

## Commit message template

```
OTA-627 feat: strategies declare compatible_structures array; consumers derive from registry
```
