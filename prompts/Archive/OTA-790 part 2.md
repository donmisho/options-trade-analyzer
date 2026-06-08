# OTA-790 — Apply / Reset and reload semantics

## Terminal context
- This terminal: Terminal A (solo)
- Concurrent terminals: none
- Cross-terminal dependencies: none — but this Story edits `web/src/api/client.js` and `web/src/pages/StrategyAdminPage.jsx`, both project-critical shared frontend files. Run on a clean tree with NO other terminal touching `client.js` (per CLAUDE.md shared-file rule). If another terminal is mid-edit on `client.js`, STOP and sequence after it.

## Required reading
Before any code changes:

    cat claude_context/CLAUDE.md
    cat claude_context/architecture-plan.md
    cat claude_context/insight_engine.md          # §6.2 tables-as-source, §6.5 restart-only, §6.6 startup validation
    cat claude_context/insight_engine-schema-ddl.md
    cat claude_context/UI-GUIDANCE.md              # Part 3a — var(--bg2) callout/banner restriction
    cat claude_context/strategy-rules-prototype-v2.html

Then read the as-built draft/preview surface this Story builds on:

    git show 3484759 --stat
    git show 3484759 -- app/api/engine_config_store.py app/api/engine_config_preview.py app/insight_engine/loader.py app/insight_engine/validation.py app/ota_adapters/engine_runtime.py web/src/api/client.js web/src/pages/StrategyAdminPage.jsx

The embedded context below is a snapshot of that commit. If anything you read in `git show 3484759` or the live files contradicts it, STOP and escalate — do not reconcile silently.

## Relevant Context — Do Not Deviate Without Escalation

Source: insight_engine.md §6.5 (Reload behavior)
Rule: The engine is **restart-only**. Table changes take effect at the next engine start. There is NO hot-reload path. OTA-790 MUST NOT introduce one and MUST NOT call `set_engine_runtime` from any Apply/Reset path. Apply changes *what the engine loads at next start*, nothing about the currently running config.

Source: insight_engine.md §6.2 (Build-time seed vs runtime source of truth)
Rule: The three tables (Rules / Strategies / Junction) are the runtime source of truth. The seed workbook is historical. There is **no per-strategy seed-default source** at runtime — the only seed path is `scripts/seed_engine_config.py` (whole-workbook, build-time). This is why Reset is defined against *live*, not against *seeded defaults* (see Decision 1).

Source: OTA-791 as-built (commit 3484759) — `app/api/engine_config_store.py`
Surface:
- Reserved draft key = `<live_key>__draft`, `status='draft'` ⇒ `enabled=0`. The runtime loader skips `enabled=0`, so a draft NEVER enters the running config.
- `DRAFT_SUFFIX`, `draft_key_for(live_key)`, `is_draft_key(key)`.
- `create_or_resume_draft(session, live_key)` — clones header + junctions if absent, RESUMES if present (no overwrite).
- `refresh_draft_from_live(...)` — discard draft edits + re-clone from live. **This is the Reset primitive (Decision 1, option a).**
- `delete_draft(...)` — 404 if absent.
- Internals: `_clone_junctions`, `_stage_draft_deletion`, `_get_strategy_optional`.
- Every write goes through `_commit_with_validation()` (OTA-783 save-time §6.6 validation).
- Existing routes: `POST /config/strategies/{key}/draft`, `POST …/draft/refresh`, `DELETE …/draft`, `POST …/preview`.

Source: OTA-791 as-built (commit 3484759) — `app/insight_engine/loader.py`
Surface:
- `load_config(source, *, include_draft_key=None)` admits exactly one named disabled key into a LOCAL config; it is NEVER passed to `set_engine_runtime`.
- `config_version` is a SHA-256 content hash (`_compute_config_version`, 16 hex) over the scoped rows, stamped at startup by `init_engine_runtime` → `EngineRuntime.config_version`. **THERE IS NO COUNTER AND NO COLUMN.** Promoting draft→live changes the live rows, so the next-start hash differs automatically (Decision 2).

Source: OTA-791 as-built (commit 3484759) — `app/insight_engine/validation.py`
Rule: `_check_junction_fks` checks the strategy FK by **EXISTENCE, not enablement** — a junction binding a disabled/draft strategy is a valid FK. This is load-bearing: it lets a draft (and any leftover draft) coexist without 422-ing other config writes. **Do not regress it.**

Source: OTA-791 as-built (commit 3484759) — `app/ota_adapters/engine_runtime.py`
Surface: `get_engine_runtime`, `set_engine_runtime`, `init_engine_runtime`. Restart-only; no hot-reload path exists today — keep it that way.

Source: OTA-791 as-built (commit 3484759) — frontend
Surface: `web/src/pages/StrategyAdminPage.jsx` (Live Preview panel already wired); `web/src/api/client.js` (`createOrResumeDraft`, `refreshDraftFromLive`, `discardDraft`, `previewDraft`). The status `<select>` intentionally excludes `'draft'`.

Source: UI-GUIDANCE.md Part 3a + §"Risk/callout boxes"
Rule: `var(--bg2)` is ALLOWED for callout boxes (this is the only permitted use class for the banner). NEVER on table rows/headers/expansion panels/full-width bands. Banner spec: `var(--bg2)` background, 2px amber (`var(--amber)`) left border, 1px `var(--border)` elsewhere, border-radius 4px. House rules: no `$` prefix; scores `##.00`; buttons content-sized with fixed padding, never full-width, visible border/background in default state; dark-theme CSS variables only, never inline hex.

## Decisions locked (Don ruled — supersede any contrary text in a stale OTA-790 AC)

1. **Reset semantics = option (a): discard draft edits back to live via `refresh_draft_from_live`.** The draft is re-cloned from the live row; edits are thrown away; the draft stays alive for continued editing. This is NOT "revert to seeded defaults." The original ticket AC language ("seeded defaults") is superseded; factory-reset-to-seeded is carved out as a separate future Story (not this one).
2. **config_version: confirmed implicit.** Apply writes the live rows; the next engine start re-derives the SHA-256 hash, which differs automatically. No counter, no column, no explicit version field is added. The change is surfaced to the operator via the pending-restart banner (Decision 4), not a version primitive.
3. **Apply mechanics = single-transaction promote.** In one DB transaction: overwrite the live strategy's header from the draft's header; REPLACE the live strategy's junction rows with the draft's (repointed to the live `strategy_id`); delete the draft. The whole transaction is gated on full §6.6 validation of the **resulting live config** — if validation fails, the transaction rolls back and the live row is left untouched. No `set_engine_runtime`, no hot-reload.
4. **Pending-restart banner = server-derived signal (preferred).** A status endpoint recomputes `_compute_config_version` over the current live rows and compares it to the running `EngineRuntime.config_version`; if they differ, `restart_pending=true`. No new column, no client-session flag, fully derived. **Phase 0 must confirm `_compute_config_version` can be invoked against live DB rows on demand using the loader's row-scoping.** If Phase 0 finds that impractical without a restart-path refactor, fall back to a client-session flag set after a successful Apply (cleared on next app load) and report the fallback in the STOP.

## Phase 0 — Read-only discovery (HARD STOP, go/no-go)

Make NO edits in Phase 0. Read and report:

1. **Reset primitive:** confirm `refresh_draft_from_live`'s exact signature and that calling it for Reset re-clones the draft from live and discards edits (option a). Confirm `discardDraft`/`DELETE …/draft` is NOT what Reset should call (that deletes the draft entirely — wrong for option a).
2. **Apply target shape:** locate exactly where the live header columns and junction rows live and how `create_or_resume_draft` clones them, so the promote path mirrors the clone in reverse (draft→live, repointed to live `strategy_id`). Report the precise column/junction-field set being copied.
3. **Validation entrypoint:** confirm `_commit_with_validation()` runs the full §6.6 set and that wrapping the promote in it validates the RESULTING live config (not the draft in isolation). Report how to invoke validation against the post-promote live state inside one transaction.
4. **config_version recompute feasibility (Decision 4):** confirm whether `_compute_config_version` + the loader's row-scoping can be run against current live rows on demand without a restart. Report YES (server-derived banner) or NO (use the session-flag fallback) with the reason.
5. **No-regress checks:** confirm (a) no hot-reload path exists, (b) `_check_junction_fks` is existence-based, (c) the status `<select>` excludes `'draft'`. Report the file:line for each.
6. **Frontend surface:** confirm `client.js` has `refreshDraftFromLive` (Reset) and report what new functions are needed (`applyDraft`, config-status fetch). Confirm the Live Preview panel location in `StrategyAdminPage.jsx` where Apply/Reset controls and the banner attach.

Paste the STOP report back to Claude Web. Wait for explicit go before Phase 1.

## Scope (Phase 1, after go)

Backend:
- New route `POST /config/strategies/{key}/apply` — single-transaction promote per Decision 3, gated on §6.6 validation of the resulting live config; deletes the draft on success; 422 with the structured validation report on failure (live row untouched); 404 if no draft exists.
- New route `GET /config/status` (or the as-built-consistent path Phase 0 identifies) — returns `{ running_config_version, persisted_config_version, restart_pending }` per Decision 4 (server-derived) or the session-flag fallback if Phase 0 ruled NO.

Frontend (`StrategyAdminPage.jsx`, `client.js`):
- `applyDraft(key)` and a config-status fetch in `client.js`; Reset reuses existing `refreshDraftFromLive`.
- Apply button — content-sized, enabled only when the current preview validated clean (no §6.6 errors surfaced); on success, reload the live view and refresh the banner.
- Reset button — content-sized; calls `refreshDraftFromLive`; on success, reload the draft editing view.
- Pending-restart banner — `var(--bg2)` callout, 2px `var(--amber)` left border, shown when `restart_pending` is true; copy: "Config changed — restart the engine to apply. The running analysis is unchanged until then."

## Acceptance criteria
- Editing a draft then calling Apply makes the live row equal the draft; the draft is deleted; the RUNNING engine config is unchanged (no `set_engine_runtime` call on the Apply path).
- A fresh `_compute_config_version` over live rows differs from the pre-Apply value; the banner shows `restart_pending=true`.
- Apply of an invalid draft is blocked by §6.6 validation; the transaction rolls back; the live row is untouched; the structured validation report is returned.
- Reset re-clones the draft from live (edits discarded) and the draft remains editable.
- No hot-reload path introduced; `_check_junction_fks` remains existence-based; status `<select>` still excludes `'draft'`.
- All UI follows Part 3a + house rules (banner uses `var(--bg2)` callout only; buttons content-sized; no inline hex; no `$`).

## Out of scope
- Config-change audit trail (OTA-792).
- Section editors — Parameters / Scoring Weights / Hard Gates / Adjustments (OTA-785 / 786 / 787 / 788).
- Adding hot-reload.
- Migrating legacy `/analyze/scorecard` to the engine.
- Factory-reset-to-seeded (separate future Story).

## Verification steps (PowerShell)
    cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
    .\venv\Scripts\Activate.ps1

    # Backend up; create+edit a draft, then Apply (manual via the UI or curl), then:
    # 1) confirm live row == former draft, draft gone
    # 2) confirm GET /config/status returns restart_pending=true
    # 3) negative: stage an invalid draft, Apply, expect 422 + live untouched

    # No-regress greps:
    Select-String -Path app\insight_engine\*.py,app\api\*.py,app\ota_adapters\*.py -Pattern "set_engine_runtime" 
    #   -> Apply/Reset paths must NOT appear in results
    Select-String -Path app\insight_engine\validation.py -Pattern "exists|enabled" 
    #   -> confirm _check_junction_fks still keys on existence, not enablement

    # Frontend build:
    cd web; npm run build; cd ..

## Commit instruction
"I have been instructed to commit. Do you approve? (yes / no)"

## Coordination footer
Independent — no downstream dependency in this terminal. (OTA-792 audit trail and OTA-793 UI tests follow as separately-authored prompts; Don sequences them.)

## Commit message template (if committing)
OTA-790 feat: Apply/Reset draft promotion and pending-restart banner
