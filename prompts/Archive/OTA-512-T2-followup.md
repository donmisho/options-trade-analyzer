# T2 follow-up: sanity-check, then commit as-is

Good catch. Before we act on your finding, one quick verification — then commit the wiring as-is and stop.

## Step 1 — Sanity-check the T1 claim that the backend honors user_config

T1's Phase 3 was supposed to prove the backend pathway works with a live curl. Your Phase 1 code reading says the backend can't possibly route a nested payload. One of those is wrong. Before we assume it's T1, confirm it.

Run the two curls from T1's handoff doc (or reconstruct them from `docs/handoff/OTA-512-contract.md` Phase 3 reference section):

```powershell
# Baseline — no user_config
curl.exe -X POST "http://localhost:8000/<endpoint>" `
  -H "Content-Type: application/json" `
  -d '{\"symbol\": \"AAPL\"}' | jq '.'

# Nested override — weekly-grind dte_min 5 → 10
curl.exe -X POST "http://localhost:8000/<endpoint>" `
  -H "Content-Type: application/json" `
  -d '{\"symbol\": \"AAPL\", \"user_config\": {\"weekly-grind\": {\"dte_min\": 10, \"dte_max\": 20}}}' | jq '.'
```

Diff the two responses. Report:

- Are the weekly-grind candidate sets identical between the two calls?
- Are the DTE filter windows (if exposed in the response) identical?

**If identical:** your Phase 1 reading is correct, the backend silently ignores nested payloads, and T1's Phase 3 verification was superficial. Proceed to Step 2.

**If different:** stop and report. There's something in the backend path we both missed and I need to look at it before we ship anything.

## Step 2 — Commit the wiring as-is

Assuming Step 1 confirms the nested payload is silently ignored, commit what you have. Do not run Phase 4. Do not mark acceptance criteria as failing in the commit — that's noise. The wiring is structurally correct and ready for when backend routing lands.

Commit subject (exact):

```
OTA-512 feat: read strategyOverrides at scan time and forward to scorer
```

Commit body:

```
Wires localStorage strategyOverrides into the scorecard API payload as
nested per-strategy dicts. readStrategyOverrides() returns null when
localStorage is empty, causing the API client (shipped in the T1 commit)
to omit user_config entirely — backend defaults apply unchanged.

KNOWN LIMITATION — backend gap, tracked separately:

The backend currently reads user_config as a flat dict applied uniformly
to all strategies. score_all_strategies has no per-strategy routing, so
the nested payload shape this commit produces is silently ignored at
scoring time. End-to-end behavior (user changes DTE slider → scoring
respects it) is blocked until the backend grows per-strategy routing.

This diagnostic gap was discovered during T2 Phase 4 verification. The
original diagnostic (DIAGNOSE-STRATEGY-DTE-SOURCE-OF-TRUTH.md) claimed
the backend pathway was already wired end-to-end; direct reading of
score_all_strategies shows that is only true for a flat dict, not the
per-strategy shape the Strategy screens actually produce.

Frontend shape in this commit is intentionally nested — it matches what
the Strategy screens write to localStorage and what per-strategy routing
will consume when it lands. No rework needed on the frontend side.

Follow-up Story: OTA-516 — backend
per-strategy user_config routing.

Partial progress on OTA-512. Ticket remains open pending the backend
follow-up; will close together when the full chain works end-to-end.
```

Push. Report:

- The commit SHA
- The Step 1 curl diff result (identical or not)
- Confirmation you stopped before Phase 4

## Do not

- Do not run Phase 4 verification. It will fail for the reason you already identified, and logging failures in the commit trail is noise.
- Do not edit the helper to flatten the payload. Flattening would lose the per-strategy intent and paint us into a corner when routing lands.
- Do not modify the API client. Its shape is correct.
- Do not transition OTA-512 to Done. I'll handle the Jira transitions once the follow-up Story is created and linked.

## Why we're shipping a no-op

The wiring is structurally correct. When the backend follow-up Story lands, nothing on the frontend needs to change — the payload shape is already what per-strategy routing will expect. Shipping it now avoids a merge conflict with unrelated frontend work and makes the backend Story a purely backend change.
