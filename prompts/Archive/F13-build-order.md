# F13 — Strategy Administration UI · Claude Code prompt set

Feature **OTA-781** · Epic **OTA-679** · grouping label `strategy-admin-ui`
All 12 stories are at **Write Prompt** in Jira. Prompts authored per `prompt-style.md` (Mechanism A + B) and `build-execution.md` (Phase 0 STOP, explicit commit gate, coordination footers). Don commits manually; Claude Code never runs `git commit`.

## Run order (single Terminal A, sequential default)

| # | Prompt | Story | Commit | Footer |
|---|--------|-------|--------|--------|
| 1 | `OTA-782.md` | Config CRUD API | yes | → OTA-783 |
| 2 | `OTA-783.md` | Save-time validation (reuses OTA-699) | yes | → OTA-784 |
| 3 | `OTA-784.md` | Editor shell + selector | yes | → OTA-789 |
| 4 | `OTA-789.md` | Rule catalog browser | yes | → OTA-791 |
| 5 | `OTA-791.md` | Draft substrate + live preview | yes | → OTA-785 |
| 6 | `OTA-785.md` | Hard Gates tab | yes | → OTA-786 * |
| 7 | `OTA-786.md` | Scoring tab + weight-sum indicator | yes | → OTA-787 * |
| 8 | `OTA-787.md` | Adjustments tab | yes | → OTA-788 * |
| 9 | `OTA-788.md` | Verdict Bands editor | yes | → OTA-790 |
| 10 | `OTA-790.md` | Apply / Reset + reload semantics | yes | → OTA-792 |
| 11 | `OTA-792.md` | Config-change audit trail | yes | → OTA-793 |
| 12 | `OTA-793.md` | UI tests + UI-GUIDANCE compliance | yes | Independent |

\* Steps 6–9 are parallelizable across terminals — see the note in `OTA-791.md`. Fan out **only** on a confirmed-green Phase 0 (disjoint component files; shared junction/param editor + `client.js` config methods already in place; additive tab registration). Otherwise run sequentially.

## Two flags carried into Phase 0 (and to Don)

1. **OTA-762 (read API) is a hard prerequisite, not marked shipped.** `OTA-782.md` and `OTA-789.md` hard-stop in Phase 0 if the `GET /api/v1/config/...` read endpoint isn't in the tree.
2. **Draft substrate reordered ahead of the tabs.** OTA-781's "all editing is save-to-draft" means the draft row must be the write target before the tabs can save correctly, so `OTA-791.md` is sequenced at step 5 (not last). `OTA-782/784/791` carry reconcile-and-STOP notes. If the tabs should instead write live and retrofit drafts, OTA-782 / 784 / 791 need re-cutting.

## Shared-file caution (from CLAUDE.md)
`app/main.py`, `app/database.py`, `web/src/api/client.js` must never be edited by two parallel terminals at once. Wave-2 (`OTA-784`) makes the `client.js` config-method additions the later UI stories reuse.

## Status note
The F13–F15 amendment to `insight_engine-migration-plan.md` remains an un-ticketed docs task (per the OTA-781 description). Not part of this prompt set.
