---
allowedTools: ["Bash", "Read", "Write", "Edit"]
---

# OTA-451 Phase 2 — Credit Spread Pipeline Fix

**Wave:** 3 (T3)
**Parent:** OTA-14 (Ongoing: Strategy Validation Reviews)
**Sequence label:** `05012026-7`
**Tier:** bug · pipeline-fix
**Predecessor:** OTA-451 Phase 1 diagnostic (Wave 1 T2 — completed)

Three findings from the Phase 1 diagnostic, all in `web/src/TradesPage.jsx`. No backend changes.

---

## Required reading

```bash
cat claude_context/CLAUDE.md
cat claude_context/business-rules.md
cat claude_context/UI-GUIDANCE.md
```

Then targeted source reads:

```bash
cat web/src/TradesPage.jsx | sed -n '70,90p'      # Layer 3 site (~line 78)
cat web/src/TradesPage.jsx | sed -n '830,860p'    # Layer 2 site (~line 841)
```

---

## Phase 1 Diagnostic Findings (verbatim)

> **Primary root cause — Layer 2 (TradesPage.jsx:841):** `fetchVerticals` hardcodes `spread_types: ['bull_call', 'bear_put']` — both debit types. `'bull_put'` and `'bear_call'` are never requested. The backend engine never generates credit spreads for this page. Zero SP/WG candidates is the guaranteed result.
>
> **Secondary bug — Layer 3 (TradesPage.jsx:78):** `inferStrategies` checks `type.includes('credit')` for pill assignment. The engine's actual spread type strings are `'bull_put'` and `'bear_call'` — neither contains `'credit'`. So SP/WG pills would still not appear even if Layer 2 were fixed alone.
>
> **Tertiary issue:** No `min_dte` is sent, so the backend default of 14 applies. WG's primary window is DTE 5–13 — fully below the cutoff. WG would need `min_dte: 3` to have a meaningful candidate pool.
>
> Layers 1 and 4 are not factors. The engine correctly builds credit spreads when asked. The display layer correctly renders whatever pills are provided.

---

## Relevant Context — Do Not Deviate Without Escalation

**Source: business-rules.md (strategy windows)**
- SP (Steady Paycheck) — DTE 25–50, credit spreads, short delta 0.20–0.30
- WG (Weekly Grind) — DTE 5–16, credit spreads, short delta 0.20–0.30
- TR (Trend Rider) — debit spreads
- LT (Lottery Ticket) — debit spreads

**Source: business-rules.md (credit spread P0 gates)**
- Credit-as-%-of-width ≥ 30% (already enforced backend-side per Phase 1 diag — do not duplicate frontend)

**Source: Phase 1 diagnostic (Layer 1 / Layer 4 verified clean)**
The backend engine produces correct credit spreads when `spread_types` includes credit types. The display layer renders whatever strategy pills are passed in. So this fix is purely about (a) asking for the right thing and (b) labeling the response correctly.

**Source: claude_context/UI-GUIDANCE.md (strategy pills)**
- SP pill: green; WG pill: green
- TR pill, LT pill: existing colors
- Pills displayed in title-case ("Steady Paycheck" not "STEADY_PAYCHECK"), but the inference logic operates on the raw spread-type string

**Source: OTA-526 retro / OTA-527 (in flight)**
Rule: Claude Code commits + pushes + verifies build. Don owns deploy.

**Forward-pointing TODOs:**
- OTA-512 (frontend wires localStorage overrides to scorer call) — when shipped, the `min_dte` interim override added in this Story should be removed because per-strategy config will flow end-to-end from the user's Strategy screen
- OTA-516 / OTA-517 (backend per-strategy `user_config` routing) — companion changes for OTA-512

---

## Scope (4 phases — STOP gates between each)

### Phase 1 — Read the two sites and confirm the diagnostic mapping

Open `web/src/TradesPage.jsx` at the two flagged sites. Read:
- ~line 78: the `inferStrategies` function with the `type.includes('credit')` check
- ~line 841: the `fetchVerticals` call with `spread_types: ['bull_call', 'bear_put']`

Confirm both still match the Phase 1 diagnostic (line numbers may have drifted slightly if any commits landed in between). Report exact current line numbers and full snippet of each function/call.

**STOP. Wait for Don's "proceed."**

---

### Phase 2 — Fix Layer 2 (request credit types)

Update `fetchVerticals` to include all four spread types:

```javascript
// BEFORE
spread_types: ['bull_call', 'bear_put'],

// AFTER
spread_types: ['bull_call', 'bear_put', 'bull_put', 'bear_call'],
```

While you're in this call, add the conditional `min_dte: 3` for WG visibility:

```javascript
// Interim override: backend default min_dte=14 excludes WG's 5-13 DTE window.
// Remove this when OTA-512/516/517 wire per-strategy config end-to-end.
// TODO(OTA-512): remove min_dte override once per-strategy DTE windows are
// honored by the backend per-strategy user_config routing.
min_dte: 3,
```

Important:
- Do NOT change the `max_dte` default — leave it alone unless the existing call already sets one
- Do NOT add any other new fields — keep the diff minimal
- The `TODO(OTA-512)` comment is required so the cleanup is discoverable when OTA-512 lands

**Show the diff. STOP.**

---

### Phase 3 — Fix Layer 3 (recognize credit types in inferStrategies)

Update the strategy-pill inference to recognize the actual spread type strings:

```javascript
// BEFORE — hypothetical, confirm against actual file content
function inferStrategies(type, dte, ivRank /* etc */) {
  const isCredit = type.includes('credit');
  // ... pill assignment logic that depends on isCredit
}

// AFTER
function inferStrategies(type, dte, ivRank /* etc */) {
  const isCredit = type === 'bull_put' || type === 'bear_call';
  const isDebit  = type === 'bull_call' || type === 'bear_put';
  // ... existing pill assignment logic, now using the corrected isCredit
}
```

Important:
- Match the actual function signature and structure — the BEFORE block above is illustrative
- If `inferStrategies` derives `isDebit` separately, fix that too with the corresponding explicit type list
- If `inferStrategies` is called from elsewhere with the same flawed `includes('credit')` pattern, fix every site (`grep -n "includes('credit')\|includes(\"credit\")" web/src/`)
- Do NOT change the SP/WG/TR/LT mapping logic — only the type-detection step is wrong

**Show the diff. STOP.**

---

### Phase 4 — Verify, commit

**Manual smoke (Don will validate after deploy, but verify the build first):**

1. Run the frontend dev server, hit the Trades page for AXP (the original failure case)
2. Confirm:
   - Trade rows include `bull_put_credit` and `bear_call_credit` types alongside the existing debit types
   - At least one row has the SP pill (DTE 28, 35, 42, 49 ranges)
   - At least one row has the WG pill (DTE 5–13 range — this is the `min_dte: 3` payoff)
   - Existing TR / LT pills still appear unchanged on debit trades

If the dev server isn't easy to spin up here, capture this as the manual handoff for Don to verify post-deploy.

Then commit:

```bash
git add web/src/TradesPage.jsx
git commit -m "OTA-451 fix: surface credit spread candidates with SP/WG strategy pills

Phase 2 fix following Phase 1 diagnostic findings (Wave 1 T2):

- Layer 2 (fetchVerticals): add 'bull_put' and 'bear_call' to spread_types so
  the backend engine generates credit candidates. Previously only debit types
  were requested; SP and WG were fundamentally unable to populate.
- Layer 3 (inferStrategies): replace type.includes('credit') with explicit
  type list. The engine returns 'bull_put' / 'bear_call' literals — neither
  contains 'credit', so the prior check could never assign SP/WG pills.
- Tertiary: add interim min_dte=3 override so WG's 5-13 DTE window is reachable.
  TODO(OTA-512): remove when per-strategy config flows end-to-end through
  the scorer call.

Closes OTA-451 (validation-failure-reopened state). Diagnostic findings
preserved in /tmp/OTA-451-phase1-report.md from Wave 1."

git push origin main
```

Verify the build run.

---

## Final handback

```
Branch: main
Commit: <sha> "OTA-451 fix: surface credit spread candidates..."
Push: confirmed pushed to origin/main at <time>
Build: GitHub Actions run <run-id> — <status>
Build artifact: <artifact-name> (<size>)

Files changed: web/src/TradesPage.jsx (one file, ~5 line diff per Phase 1 diag)

Manual smoke (Don, post-deploy):
1. Open Trades page for AXP
2. Confirm credit candidates appear (bull_put_credit, bear_call_credit types)
3. Confirm SP pill appears on at least one row in 25-50 DTE range
4. Confirm WG pill appears on at least one row in 5-13 DTE range
5. Confirm existing TR/LT pills still appear on debit trades

Validation gate: this Story has been Production Deployed → reopened once.
Recommend Don adds a single end-to-end click ("see at least one SP pill")
to the OTA-511 deploy checklist so this class of regression is caught
before the second 24-hour validation cycle.

Ready for user to deploy via deploy-to-dev.yml.
```

**STOP. Do NOT trigger any deploy workflow.**

---

## Acceptance criteria (from original OTA-451 ticket)

- [ ] AC #1 — Trades page shows credit spread candidates (Bull Put Credit, Bear Call Credit) when SP/WG strategies have matching parameters
- [ ] AC #2 — Credit spreads appear in the "Vertical spreads" section alongside existing debit spreads
- [ ] AC #3 — Strategy pills show SP and/or WG for credit spread results
- [ ] AC #4 — AXP with Steady Paycheck score 85 produces visible SP credit spread trades
- [ ] AC #5 — Credit-specific scoring (theta margin ratio, credit %) applied correctly (verified backend-side per Phase 1 diag — engine does this when asked)
- [ ] AC #6 — P0 gates enforced: credit as % of width ≥ 30% (verified backend-side per Phase 1 diag — already enforced)

## Out of scope (explicitly do NOT do)

- Backend changes — Phase 1 diag confirmed engine and gates are correct
- Permanent per-strategy DTE config — that's OTA-512 / OTA-516 / OTA-517
- Deploy checklist update for OTA-511 — file separately if you decide to
- Trigger any deploy workflow → Don's job
