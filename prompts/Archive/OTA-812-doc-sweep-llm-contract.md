# OTA-812 — Cross-doc reference sweep + document LLM-orchestration contract

## Terminal context
- This terminal: Terminal A
- Concurrent terminals: none
- Cross-terminal dependencies: **runs last in Feature 9.** Requires OTA-811 (Communicator rename) and OTA-808 (architecture-plan.md restructure) committed to main first. Do not run until both are landed.

## Required reading
Before any file changes (PowerShell, from repo root with venv active):

```powershell
cat claude_context/CLAUDE.md
cat claude_context/architecture-plan.md
cat claude_context/business-rules.md
cat claude_context/insight_engine.md          # §2.6 LLM precedence, §8 boundaries, §9 — generic-engine definition
```

## Relevant Context — Do Not Deviate Without Escalation

**The distinction the entire sweep turns on (insight_engine.md §1, §8; architecture-plan.md).**
- **Generic Insight Engine** = the OTA-679/OTA-695 evaluation framework under `app/insight_engine/`. Deterministic detect → score over the `engine_*` tables, emits `ResultRecord` verdicts, is **LLM-agnostic and never calls an LLM** (§2.6). Keep references to this as "Insight Engine."
- **Insight Communicator** = the Claude-based observation→insight component, formerly `app/agents/insight_engine.py`, renamed to `app/agents/insight_communicator.py` by OTA-811 (class `InsightEngine` → `InsightCommunicator`; SKILL.md path `app/skills/insight-engine/` → `app/skills/insight-communicator/`; writes the `insights` table). **Rename references to this** from "Insight Engine" → "Insight Communicator."

Not every "Insight Engine" string is wrong. Each occurrence must be classified before it is touched.

**Source: OTA-812 / migration-plan S9.7 (both entries).**
1. **Sweep.** Across `architecture-plan.md`, `CLAUDE.md`, `business-rules.md`, and any `SKILL.md`: every reference to the Communicator as "Insight Engine" becomes "Insight Communicator" (and the corresponding `insight_engine.py` / `app/skills/insight-engine/` paths become the renamed paths). Generic-engine references are preserved.
2. **Split.** The `architecture-plan.md` "## The Insight Engine" section (currently describing the Communicator) splits into two sections — one for the generic Insight Engine, one for the Insight Communicator — and documents the relationship: **the Communicator may consume engine `ResultRecord` verdicts as one of its trigger signals.** Reconcile "Pattern 5" too (it is currently labelled "Generic Insight Engine" but describes Communicator behaviour).
3. **LLM-orchestration contract** — place in the section OTA-808 reserves in `architecture-plan.md`. Consumer-side principle governing OTA's use of Claude, **explicitly not an engine concern** (engine is LLM-agnostic, §2.6):
   - The engine runs to completion before any LLM call; the LLM never discovers a rule violation.
   - LLM calls are minimised in *number* while individual calls may be detailed and precise (spend tokens per call, save tokens by making fewer calls).
   - Model selection is deliberate — Opus for complex analysis, Haiku for simple text responses.

**Source: CLAUDE.md → Document Governance.**
- Documents state what IS — no deliberation, alternatives-considered, or historical framing.
- On each edited doc, set the header `Last Updated` (`yyyy-mm-dd hh:mm UTC`, actual UTC at edit time) and add a change-log entry referencing **OTA-812**.

---

## Phase 0 — Discovery (READ-ONLY). STOP for approval before editing.

Do not edit any file in this phase.

1. **Prerequisite gates (hard STOP if either fails):**
   - **OTA-811 landed?** Confirm `app/agents/insight_communicator.py` exists, `app/skills/insight-communicator/` exists, and `grep -r "insight_engine" app/agents/` returns only legitimate references to the generic engine package. If the rename is not present → STOP and report; this story cannot sweep references to names that do not yet exist.
   - **OTA-808 landed?** Confirm `architecture-plan.md` carries the new package boundaries (`app/insight_engine/`, `app/ota_adapters/*`, `app/options_rules/*`) and a reserved LLM-orchestration contract section/heading. If absent → STOP and report (either OTA-808 runs first, or scope must expand to create the section — Don's call).

2. **Build the occurrence inventory.** Grep every in-scope doc and all `app/skills/**/SKILL.md` for `Insight Engine`, `insight_engine`, `insight-engine`. For each hit, record: file, line, the surrounding phrase, the classification (**Communicator** → rename / **generic engine** → keep), and the proposed replacement.

3. **Propose the architecture-plan.md changes:** an outline of the two split sections (generic Insight Engine vs Insight Communicator) plus the relationship sentence, the Pattern 5 reconciliation, and the exact LLM-orchestration contract text to insert into OTA-808's reserved section.

4. **Report** the inventory table + the architecture-plan.md outline + the contract text, and **STOP**. Await approval before editing.

---

## Scope (Phase 1 — after approval)

Apply the approved sweep, the architecture-plan.md section split + Pattern 5 reconciliation, and the LLM-orchestration contract insertion. Update `Last Updated` and add a change-log entry citing OTA-812 on every edited doc.

## Acceptance criteria

- No doc refers to the Communicator as "Insight Engine"; the generic engine and the Communicator are clearly distinguished everywhere.
- Generic-engine references (`app/insight_engine/`, the OTA-679 framework) are preserved and not mis-renamed.
- `architecture-plan.md`'s "Insight Engine" section is split into generic-engine vs Communicator, with the `ResultRecord`-trigger relationship documented; Pattern 5 is reconciled to the same distinction.
- The LLM-orchestration contract is present in OTA-808's reserved section, captured as a consumer-side principle and marked **not an engine concern**.
- Every edited doc has an updated `Last Updated` and a change-log entry referencing OTA-812.

## Out of scope

- No code changes — the module/class/path rename is OTA-811; this story is documentation only.
- No `architecture-plan.md` package-boundary / persistence / sink restructure — that is OTA-808; this story only fills the LLM-orchestration section and does the split/sweep.
- No new rule content in `business-rules.md` — that is OTA-807.
- `insight_engine.md` is the canonical generic-engine spec; do not rename anything in it. If Phase 0 finds a stray Communicator-as-"Insight Engine" reference there, flag it — do not edit without approval.

## Verification steps

1. Re-grep all swept docs and `SKILL.md` files for `Insight Engine` / `insight_engine` / `insight-engine`: every remaining hit refers to the generic engine, none to the Communicator.
2. Confirm `architecture-plan.md` has two distinct sections (generic engine, Communicator) with the relationship sentence, and Pattern 5 matches.
3. Confirm the LLM-orchestration contract is present, with all three principles and the "not an engine concern" marking.
4. Confirm `Last Updated` + change-log entry (citing OTA-812) on each edited doc.

## Commit instruction

I have been instructed to commit. Stage all edited docs, present the exact commit message below, and STOP. Don executes the commit manually. Do not run `git commit`.

## Coordination footer

STOP — do not run until OTA-811 (rename) and OTA-808 (architecture-plan.md restructure) are committed to main. This story runs last in Feature 9.

## Commit message template

```
OTA-812 docs: Insight Communicator sweep + LLM-orchestration contract
```
