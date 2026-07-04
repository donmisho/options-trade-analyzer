# OTA-835 — Defer verdict-band threshold authority to per-strategy `verdict_band_set` (screening + directional)

> **Two-step prompt.** Step 0 is read-only verification with a hard GO/NO-GO STOP. Step 1 edits `scripts/seed_engine_config.py` only after Don gives GO. No commit — stage and present the diff for manual commit.

## Terminal context
- This terminal: Terminal A (single terminal — engine-core / seed).
- Concurrent terminals: none. This edits `scripts/seed_engine_config.py`; it must NOT run concurrently with any other seed-touching work (OTA-832, OTA-833, OTA-836).
- Cross-terminal dependencies: runs AFTER OTA-833 is committed — OTA-833 seeds the directional `*_verdicts` lookup set(s) this story strips. Rides the OTA-832/OTA-833 reseed. OTA-836 (fatal-hydration keystone) follows this story; do not begin it here.

## Required reading
Before any code changes:

```
cat claude_context/CLAUDE.md
cat claude_context/insight_engine.md
cat claude_context/insight_engine-schema-ddl.md
cat claude_context/insight_engine-migration-plan.md
cat claude_context/business-rules.md
```

## Relevant Context — Do Not Deviate Without Escalation

```
Source: insight_engine.md § 3.8 (Verdict bands)
Rule: Verdict bands are a per-strategy mapping from final score to a categorical
verdict. The authoritative per-strategy band store is engine_strategies.verdict_band_set.
The prior universal EXECUTE/WAIT/PASS thresholds (70/50) were a tables-as-source
VIOLATION, not evidence bands should be universal.

Source: insight_engine.md § 4.1 (Phase 7 — Verdict band lookup)
Rule: The engine maps the final adjusted score to a verdict via THE STRATEGY'S
bands. There is exactly one band-lookup code path; no second path produces a verdict.

Source: insight_engine-schema-ddl.md (engine_strategies)
Fact: verdict_band_set is a NOT NULL per-strategy JSON column on engine_strategies —
the authoritative band store the Phase-7 lookup reads.

Source: Epic OTA-679 acceptance criteria
Rule: All rule content — thresholds, weights, gate behaviour, ordering, verdict
bands — is resolvable from the runtime tables, from exactly one place. No second
code path produces a verdict. No `if strategy_key ==` branches in engine code.

Source: OTA-835 Phase 0 report (screening surface — already discovered)
Finding: The screening_verdicts lookup's threshold payload {min_score, max_score}
is FULLY VESTIGIAL — written by the seed (seed_engine_config.py ~:438-447, sourced
from _CANONICAL_SCREENING_BANDS ~:72-76), read by NO code path. The sole runtime
reader, _get_verdict_domain (validation.py:195-204, set_name =
f"{consumer_surface.lower()}_verdicts"), reads e.lookup_key ONLY — never the payload.
Those keys ARE load-bearing: _check_terminal_verdict_domain (validation.py:293-315)
uses them to validate that each junction's terminal_verdict is a known verdict label.
Phase-7 verdict assignment reads rule_set.strategy.verdict_band_set
(pipeline.py:226-227 → _lookup_verdict_band pipeline.py:515-528; hydrated
loader.py:114-123) — never the lookup. → Path A: strip thresholds, keep keys.

Source: OTA-835 Phase 0 report, note 1 + Don's scope ruling
Finding: The identical vestigial pattern exists in the directional verdict-band
lookup set(s) at seed_engine_config.py ~:2787-2798 (mirror {min_score, max_score},
self-document "the engine reads bands from the verdict_band_set column… not these
rows"). The Phase 0 author scoped these out as "OTA-833 / eventually"; Don has scoped
them INTO OTA-835. Both surfaces are stripped in this one story so threshold authority
lands in verdict_band_set atomically. Don's scope names three directional objectives
(Income / Steady Growth / Big Bet-Longshot); Step 0 confirms the exact set name(s)
and rows.
```

## Scope

### Step 0 — read-only verification (HARD STOP — report and await GO/NO-GO before ANY edit)

```powershell
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
.\venv\Scripts\Activate.ps1
```

Confirm the seed reflects committed OTA-833 before proceeding (the directional rows below must already exist). Then answer, with exact `file:line` evidence:

1. **Screening — re-confirm.** Locate the `screening_verdicts` lookup builder (line numbers may have shifted post-OTA-833 — re-verify, do not trust the embedded numbers). Record the band rows' current key + payload and the `WAIT_FOR_EARNINGS` halt row.
2. **Directional — enumerate.** Locate the directional verdict-band lookup set(s) (~:2787-2798). Record the **exact lookup set name(s)**, every row's `lookup_key`, `sort_order`, and full payload, and any directional **halt-verdict** rows. State whether it is one shared set or one per objective.
3. **Directional keys load-bearing?** Confirm the directional surface resolves its verdict domain through `_get_verdict_domain` / `_check_terminal_verdict_domain`, i.e. directional junction `terminal_verdict` values are validated against these lookup keys (so the keys must be preserved). Cite the resolution path and the directional `consumer_surface` value.
4. **Directional Phase-7 source.** Confirm directional Phase-7 verdict assignment reads each directional strategy's `engine_strategies.verdict_band_set` column — NOT the directional lookup. **If directional Phase-7 reads the lookup thresholds, this is NO-GO for the directional strip** — stop, report, recommend Path B (repoint) for directional only.
5. **Constant consumption.** Determine whether `_CANONICAL_SCREENING_BANDS` (~:72-76) and the directional band constants are consumed ONLY by their lookup-builder loops, or also feed `verdict_band_set` or anything else. (Governs whether the source constants can be slimmed or must be left untouched.)

**STOP.** Present Q1–Q5 with evidence and a per-surface plan. Await Don's GO before Step 1.

### Step 1 — implementation (only after GO)

Edit `scripts/seed_engine_config.py` only:

- **Screening band rows** (EXECUTE / WAIT / PASS): strip `{min_score, max_score}` from the payload. Payload becomes `{}` (valid JSON); `lookup_key` carries the label and `sort_order` is already its own column. Leave the `WAIT_FOR_EARNINGS` halt row's `{label, kind, description}` payload **intact**.
- **Directional band rows** (per Step 0's enumeration): apply the identical strip — payload → `{}`, keys + `sort_order` preserved. Leave any directional halt-verdict rows **intact**.
- Add a one-line self-documenting comment above the screening band-builder mirroring the directional one (threshold authority lives in `engine_strategies.verdict_band_set`; these rows seed the verdict-label domain only).
- Slim a band source constant ONLY if Step 0 proved it lookup-only. Do NOT touch `verdict_band_set`, the Phase-7 lookup, the monotonic-band check, or any constant that feeds `verdict_band_set`.

## Acceptance criteria
- Both surfaces' verdict-band-row payloads carry no `min_score` / `max_score`; `lookup_key` + `sort_order` preserved on every band row.
- Halt-verdict rows (`WAIT_FOR_EARNINGS` and any directional equivalent) unchanged.
- `_get_verdict_domain` returns the identical `lookup_key` set pre- and post-change for screening AND each directional surface (verdict-label domain unchanged; `_check_terminal_verdict_domain` still passes).
- Phase-7 path (`verdict_band_set`) untouched; no second verdict path introduced; no `if strategy_key ==` branches.
- `python -m py_compile scripts/seed_engine_config.py` clean.

## Out of scope
- `engine_strategies.verdict_band_set` values and the Phase-7 lookup — not modified.
- The Verdict Bands UI editor (OTA-788).
- OTA-832 / OTA-833 / OTA-836 work, and the `spread_width_tier_compliance` carve-out (OTA-836).
- Running a live reseed against the DB (this rides the OTA-832/OTA-833 reseed Don performs).

## Verification steps
- `python -m py_compile scripts/seed_engine_config.py` — clean.
- Re-run the searches and confirm `min_score` / `max_score` no longer appear in the verdicts-lookup builders for either surface, and remain ONLY in the `verdict_band_set` sources:
  ```powershell
  rg -n "min_score|max_score" scripts app
  ```
- Construct the lookup rows in-process (or inspect the built lookup lists before upsert) and assert the band rows' payloads are threshold-free while keys/`sort_order` are preserved on both surfaces.
- Targeted check: `_get_verdict_domain` yields the same key set as before for screening and each directional surface.
- **Do NOT gate on a full `load_config` / full hydration dry-run.** `load_config` currently RAISES on the `spread_width_tier_compliance` carve-out (OTA-836's keystone) and will until that story lands — that raise is expected and pre-existing, NOT a regression from this story. Verify at the seed-row + verdict-domain level described above.
- Confirm the Phase-7 `verdict_band_set` path is byte-for-byte unchanged.

## Commit instruction
I have been instructed NOT to commit. Stage all changes and present the full diff plus a per-row **before/after** table covering both surfaces. Don reviews and commits manually.

## Coordination footer
STOP after staging the diff — do not commit and do not begin OTA-836. This story rides the post-OTA-833 reseed; confirm OTA-833 is committed before Step 1.

## Commit message template
```
OTA-835 refactor: defer verdict-band threshold authority to per-strategy verdict_band_set; strip vestigial thresholds from screening + directional verdicts lookups
```
