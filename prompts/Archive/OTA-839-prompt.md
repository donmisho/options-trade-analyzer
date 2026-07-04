# OTA-839 — chart_state_valid_alignment gate IN-list value-domain mismatch (Trend Rider / Lottery Ticket screening go-live blocker)

## Terminal context
- **This terminal:** single terminal — screening seed/config (`scripts/seed_engine_config.py`) + screening rule config.
- **Concurrent terminals:** none. Do **not** parallelize with any seed-touching work; this prompt edits `scripts/seed_engine_config.py`.
- **Cross-terminal dependencies:** runs **after OTA-836 lands**. OTA-836 makes hydration testable and builds the `chart_state_matches_direction` / `extension_matches_trade_direction` formulas — path (b) below repoints to one of them, so 836 must be in before this runs.

---

## Required reading
Before any code changes:

```
cat claude_context/CLAUDE.md
cat claude_context/architecture-plan.md
cat claude_context/business-rules.md
cat claude_context/insight_engine.md                    # §3.6 gate mechanics, §6.3 expression library, §6.6 startup validation
cat claude_context/insight_engine-migration-plan.md     # S3.9 chart_state enum producer
```

If the migration-plan filename differs in the repo, locate the doc whose S3.9 section defines the `chart_state` enum producer and read that instead — do not proceed without the canonical domain in front of you.

---

## Relevant Context — Do Not Deviate Without Escalation

**Source: `insight_engine-migration-plan.md` S3.9 (chart_state enum producer)**
The adapter publishes `chart_state` over the enum domain **`{Bullish, Bearish, Mixed, Neutral}`**. The seeded gate `chart_state_valid_alignment` accepts `chart_state IN ['Bullish Alignment','Bearish Alignment']`. Those two literals are **not members** of the published domain, so the predicate can never match — every candidate evaluates this gate as **FAIL**. (S3.9 also notes the adapter has SMA alignment but historically no enum mapping — confirm the mapping is in place.)

**Source: OTA-839 body / `business-rules.md` (chart-state direction gate)**
`chart_state_valid_alignment` is `stop_if_fail=true` for **Trend Rider** (`BULL_CALL_DEBIT` / `BEAR_PUT_DEBIT`) and **Lottery Ticket** (`SINGLE_LONG_CALL` / `SINGLE_LONG_PUT`). A FAIL halts the candidate terminally — so the first live TR/LT screening run returns **zero candidates, silently**, until this lands.

**Source: `insight_engine.md` §6.3 (expression library)**
The generic predicate path evaluates `named_values[ref] OP <single bound literal>`. It **cannot** compare two named values and has **no arithmetic**. "Chart state confirms the trade direction" (`chart_state` vs candidate direction) therefore cannot be a generic two-value predicate — it must be expressed either as an IN-list against the correct single-value domain (path a) or via the `chart_state_matches_direction` formula OTA-836 made live (path b).

**Source: `CLAUDE.md` house style + `insight_engine.md` §2**
- No `if strategy_key ==` / structure branching. Per-strategy `Mixed` / `Neutral` behavior (skip / record-only / fail) is expressed entirely via junction `stop_if_fail` / `score_penalty` — never in code.
- Tables are the source of truth. The fix flows through `scripts/seed_engine_config.py` + a reseed, **not** a code patch to make validation pass.

**Adjacent, distinct — do not re-solve here**
`null_semantics` SKIP/FAIL_OPEN handling is OTA-838 (already landed). This bug is a **value-domain** mismatch, not a null-handling issue.

---

## Scope — Phase 0 (read-only discovery, hard STOP)

No edits, no reseed, no commit. Produce a findings report and STOP for GO.

1. **Confirm the defect.** Read the seeded `chart_state_valid_alignment` gate row: exact operator + literal set; every strategy that binds it; `stop_if_fail` per binding. Inspect via the seed dry-run and/or a read-only query against the seeded `engine_rules` config.
2. **Confirm the domain.** Read the adapter `_CATALOG` and confirm the published `chart_state` domain is exactly `{Bullish, Bearish, Mixed, Neutral}` (and that the SMA→enum mapping from S3.9 is implemented).
3. **Sibling audit.** Scan all screening gate enum / IN-list literals against their LHS named value's adapter-published catalog domain. Call out **`extension_matches_trade_direction`** specifically (the other OTA-836 Stage-2 formula) and enumerate any other gate-literal-vs-catalog-domain mismatches found.
4. **Path (b) feasibility.** Confirm whether `chart_state_matches_direction` is now live post-836; capture its signature and semantics (what it reads, what it returns) so its fitness as a repoint target can be judged.
5. **Recommend a path:**
   - **(a) Correct the seeded IN-list** to the adapter domain `{Bullish, Bearish, Mixed, Neutral}` with explicit per-direction semantics, deciding for each strategy whether `Mixed` / `Neutral` skips / records-only / fails via junction `stop_if_fail` / `score_penalty`; or
   - **(b) Repoint the gate** to the `chart_state_matches_direction` formula, retiring the IN-list predicate row.
6. **Parity + registry deltas.** State whether a live-verdict parity check is needed (TR + LT before/after) and the net `engine-formula-registry.md` change, if any (path b may already be balanced by 836).

**HARD STOP.** Output the findings + recommended path and wait for Don's GO before any implementation.

---

## Scope — Implementation (only after Don's GO on the chosen path)

**If path (a):** correct the seeded IN-list literals to the adapter domain; set `Mixed` / `Neutral` handling per strategy via junction `stop_if_fail` / `score_penalty`; update `scripts/seed_engine_config.py`; reseed.

**If path (b):** change the `chart_state_valid_alignment` gate row to `formula_ref: chart_state_matches_direction`; remove the IN-list predicate; confirm the formula is registered and present in `engine-formula-registry.md` (update if 836 left a delta); update `scripts/seed_engine_config.py`; reseed.

Then prove the fix against live candidates (verification below).

---

## Acceptance criteria
- No screening gate's enum / IN-list literal references a value outside its LHS named value's adapter-published catalog domain.
- `chart_state_valid_alignment` (or its replacement) **passes** a TR candidate whose chart state confirms its direction, and an LT candidate likewise; `Mixed` / `Neutral` behavior is explicit per strategy (skip / record-only / fail) via junction config, not in-code branching.
- A live TR and a live LT candidate are no longer auto-halted by the chart-state gate.
- No `if strategy_key ==` / structure branching introduced.
- Clean reseed; startup hydration still succeeds (`validate_and_raise` clean; `get_engine_runtime()` live).

---

## Out of scope
- The directional surface (OTA-833/835 strategies) — disabled per OTA-836. This bug is the **screening** surface only.
- `null_semantics` handling (OTA-838).
- The broader golden-fixture parity net (OTA-796).
- Any rule tuning or verdict-band recalibration.

---

## Verification steps

```powershell
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
.\venv\Scripts\Activate.ps1
```

1. Reseed from the corrected seed; confirm a clean load (`load_config` passes, `validate_and_raise` clean, app boots, `/evaluate/structured` up).
2. Score a TR candidate that **confirms** its direction (e.g. `BULL_CALL_DEBIT` with `chart_state = Bullish`) → chart-state gate **passes**, candidate not halted.
3. Score an LT candidate likewise (`SINGLE_LONG_CALL`, `chart_state = Bullish`) → passes.
4. Score a **counter** case (`chart_state = Bearish` on a bullish candidate) → behaves per the chosen per-strategy semantics (fail / skip / record), as decided in Phase 0.
5. `grep`/query confirms no remaining screening gate IN-list literal outside its catalog domain.

---

## Commit instruction
I have been instructed to commit on Don's approval. After a clean reseed + the verification steps pass, present the diff and ask: **"Commit? (yes / no)"**. Do not commit before Don approves.

---

## Coordination footer
Independent — no downstream dependency. (Upstream: must run after OTA-836.)

---

## Commit message template (if committing)
`OTA-839 fix: correct chart_state_valid_alignment value-domain so TR/LT screening candidates are no longer auto-halted`
