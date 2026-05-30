# BUILD-SCHEDULE — Strategy-Structure Routing Enforcement (OTA-646)

**Scope:** Six tickets under OTA-646 plus the two cancelled duplicates (OTA-647, OTA-648) for cross-reference. Sequenced for safe single-terminal execution.

**Why single-terminal:** Three of the W4 stories (649/650/651) all touch `web/src/client.js`, the 867-line monolith flagged in CLAUDE.md as a known shared-file conflict risk. Parallelism here costs more in merge conflicts than it saves in wall-clock time. Serialize them.

---

## Build waves

| Wave | Tickets | Terminal | Gate to next wave |
|---|---|---|---|
| **W1** | OTA-636 | Terminal A | Backend tests green; `eligible_strategies()` and `best_fit()` return correctly for the 4-strategy compatibility matrix; AMZN + MSFT regression suites pass; Foundry SKILL.md compatibility check verified still in place |
| **W2** | OTA-637 | Terminal A | MMM 146/136 Bear Put renders TR pill only; trade detail header reads "Best fit: Trend Rider {score}"; no SP/WG pills surface on Bear Put rows anywhere; verdict pill == narrative verdict word for every spread tested |
| **W3** | OTA-645 | Terminal A | Regression test fixture exists at `tests/regression/test_verdict_narrative_consistency.py`; structural-incompatibility matrix (9 cells) all return None from scorer; verdict-consistency invariant holds across 20+ compatible pairs; MMM Bear Put canary fixture passes; `bugfix.md` updated |
| **W4a** | OTA-649 | Terminal A | `/api/v1/analysis/scorecard` returns per-cell `{score\|null, argmax_spread_ref\|null, reason\|null}`; MMM card shows SP=N/A, WG=N/A, TR=populated, LT per compatibility; populated-cell click lands on the right spread |
| **W4b** | OTA-650 | Terminal A | MMM Bear Put currently grouped under SP now appears in Orphaned group; Re-route button moves it to TR; `POST /api/v1/positions` returns 422 for incompatible strategy_at_entry; strategy-page positions panels show zero structurally-mismatched positions |
| **W4c** | OTA-651 | Terminal A | `/trades?symbol=MMM` renders one expanded `Trend Rider — Recommended` section; footer notes SP/WG have no compatible setups; Path A mode (`/trades?strategy=X&symbol=Y`) unaffected |

The W4 split is for tracking only — they all run sequentially in Terminal A. Each commits independently to keep diffs bounded.

---

## Why this order

**OTA-636 must land first.** Every other ticket reads the new contract — `eligible_strategies()`, `best_fit()`, the null-score convention. Without 636 committed, the downstream UIs have nothing real to wire to.

**OTA-637 follows 636 directly.** The frontend must align to the null contracts before any other UI surface is touched. Without 637, the MMM walkthrough still produces contradictions on the canonical surface (Trades page) regardless of what 649/650/651 do.

**OTA-645 runs after 637.** Its job is regression coverage — the symptom bug is closed by 636+637 landing, but the test fixture lives in this Story. Putting it after 637 means the test author can verify Phase 1's read-only reproducer is already clean before adding the assertions that lock it.

**W4 stories (649/650/651) are conceptually parallel but practically serialized** because of the `client.js` monolith. Order within W4 is by surface complexity:
- 649 first (cleanest scope — new endpoint + cell-rendering swap)
- 650 next (positions API additions + new endpoint + UI orphan group + entry guard — middle complexity)
- 651 last (largest UI restructure — grouping shape change on the page that's seen the most prior changes)

---

## Cross-ticket coordination

**Shared files at risk:**
- `web/src/client.js` — touched by 637, 649, 650, 651. Serialize all four. Each commits its client.js edits before the next starts.
- `app/api/analysis_routes.py` — touched by 636 (response shape additions) and 649 (new scorecard endpoint). Serialize.
- `app/analysis/strategy_routing.py` — created in 636. Read-only thereafter. No conflict.
- `business-rules.md` — should already carry the canonical Strategy-Structure Compatibility section per OTA-635. None of these stories edit it. Confirm before W1 starts; if missing, OTA-635 is a blocker.

**Backend-frontend handoff between W1 and W2:**
- Best to deploy OTA-636 to dev before starting OTA-637 — gives the frontend a real backend to verify against.
- If 637 must start before 636 deploys, mock the new response fields client-side and replace the mocks during W2 verification.

**Foundry prompt audit (W1):**
- 636's Phase 2f reads the active strategy-scoring SKILL.md and reports whether any prompt-side logic presumes "try to find a fit across all four strategies." If yes, file a follow-up subtask under OTA-507 — do not edit the prompt in 636.

---

## Estimated terminal time

Approximate session-time per Story, single-terminal, with the read-only Phase 1 diagnostic and commit cycle:

| Ticket | Est. terminal time | Notes |
|---|---|---|
| OTA-636 | 90–120 min | New module + scorer gate + scanner inversion + 4 test categories |
| OTA-637 | 60–90 min | Three UI surfaces audited; mostly null-state handling and source-unification |
| OTA-645 | 30–45 min | Regression test fixture; minimal production code edits expected |
| OTA-649 | 60–75 min | Backend scorecard endpoint + frontend cell rendering + click-through |
| OTA-650 | 75–90 min | Validation + new reroute endpoint + orphan group UI + entry guard |
| OTA-651 | 60–75 min | Branching logic + grouped rendering + footer + edge cases |
| **Total** | **~6–8h** | Single terminal, sequential, with Don's review/commit gates in between |

Don can split across multiple sessions on different days. Each Story commits independently and the chain resumes from any landed commit.

---

## Verification points across the wave

After **W1 (OTA-636)**:
- `curl` (or Invoke-RestMethod) the verticals endpoint with strategy=trend-rider for MMM — response carries only debit structures.
- Pytest the new test file under `tests/analysis/test_strategy_routing.py`.

After **W2 (OTA-637)**:
- Manual click-through of Path A and Path B on both a credit-spread symbol and a debit-spread symbol.
- Browser hard refresh; confirm no cached bundle is masking issues.

After **W3 (OTA-645)**:
- Pytest the full regression suite. Pre-existing AMZN/MSFT regressions plus the new verdict-consistency suite all green.

After **W4a (OTA-649)**:
- Security Strategies page reflects N/A on MMM SP/WG cells with tooltips.
- Click-through from a populated cell expands the right spread on Trades.

After **W4b (OTA-650)**:
- `/positions` shows the MMM Bear Put in the Orphaned group.
- Re-route moves it to TR.
- The malformed `POST /api/v1/positions` (Bear Put + SP) returns 422.

After **W4c (OTA-651)**:
- `/trades?symbol=MMM` renders one expanded `Trend Rider — Recommended` section.
- The original MMM walkthrough (six surfaces) now agrees end-to-end. No surface contradicts any other.

---

## Closing the Epic (OTA-646)

OTA-646 closes when:
- All six Stories (636, 637, 645, 649, 650, 651) are Production Deployed.
- The MMM walkthrough re-runs cleanly: card shows SP=N/A, WG=N/A, TR populated; drill-in shows Bear Put rows with TR pill only and "Best fit: Trend Rider" in the header; verdict and narrative agree; same trade on Positions surfaces under Trend Rider (after re-route) or in the Orphaned group; `/trades?symbol=MMM` renders the Trend Rider section as Recommended.
- The parked data-integrity stack (Greeks ~0, IV Rank 0%, decimal display, max P&L inconsistencies, spread type UNKNOWN at export) is queued as the next workstream — those bugs now have a clean routing signal to validate against.

---

## Out of scope for this Epic

Reaffirmed boundaries (also stated in OTA-646's description):

- Data-integrity bugs. Affect scoring inputs to the routing predicate. Validate them against the clean routing signal AFTER this Epic lands.
- Strategy taxonomy redesign (cute → mechanics-based names). The compatibility map is keyed on `trade_structure` enums, so this Epic is robust to the rename.
- Position lifecycle state machine (separate concern pending under OTA-507).
- Pill-rendering utility consolidation (TODO from OTA-637; future cleanup).
- Splitting `web/src/client.js` monolith (backlog Story #12).

---

## Change Log

| Date | Note |
|---|---|
| 2026-05-14 | Initial draft. Reflects cleanup that closed OTA-647 and OTA-648 as duplicates of pre-existing OTA-636 and OTA-637. Re-parented 636/637/645 from OTA-507 to OTA-646 to give this finite Epic complete ownership of the routing-fix work. |
