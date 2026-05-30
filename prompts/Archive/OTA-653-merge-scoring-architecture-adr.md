---
allowedTools:
  - Read
  - Edit
  - Write
  - Bash
---

# OTA-653 — Merge Scoring Architecture ADR into architecture-plan.md

## Terminal context
- This terminal: single-terminal work (~30 minutes)
- Concurrent terminals: none
- Cross-terminal dependencies: none

## Required reading

Before any changes:

```powershell
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
cat claude_context/CLAUDE.md
cat claude_context/architecture-plan.md
cat claude_context/prompt-style.md
cat claude_context/auth-process.md          # reference for ADR house style (ADR-1, ADR-2)
```

Also read the source materials produced by OTA-653:

```powershell
cat ..\scoring-agent-discovery.md
cat ..\scoring-agent-adr-draft.md
```

## Relevant Context — Do Not Deviate Without Escalation

**Source:** `prompt-style.md` (Issue numbering discipline)
**Rule:** Use OTA-653 in commit messages, branch names, and change-log entries. Do not invent issue keys.

**Source:** `architecture-plan.md` (Source of Truth Documents)
**Rule:** This document is the source of truth for architecture. Business rules live in `business-rules.md` exclusively. The scoring agent decision is architectural (it concerns which engine performs scoring), so it goes in `architecture-plan.md` — not in `business-rules.md`.

**Source:** `auth-process.md` (ADR-1, ADR-2 sections)
**Convention:** ADRs are scoped to the SoT document they govern. ADR numbering is per-document, not global. Format includes Decision Date, Status, Decision body, Scope, Constraints, Change Log. Title is subject-focused (e.g., "BFF Identity Management"), not direction-focused.

**Source:** `CLAUDE.md` (Document Governance Rules)
**Rule:** Material changes to any SoT doc must update the `Last Updated` header and add a Change Log entry referencing the driving Story.

**Note:** `architecture-plan.md` does not currently use the ADR-N convention (it uses named subsections like "Schema Migration Strategy" and "Resource Shutdown Discipline"). This prompt introduces the ADR convention to `architecture-plan.md` as ADR-1.

## Scope

Merge the finalized ADR from `..\scoring-agent-adr-draft.md` into `claude_context/architecture-plan.md`, archive the discovery doc inside the repo, and delete the now-redundant draft.

### 1. Add ADR-1 to architecture-plan.md

Insert a new top-level section titled **`## ADR-1: Scoring Architecture — Deterministic Code with Agent-Driven Judgment`** directly after the existing `## Roadmap Reference` section and before the `# 1. Background and Patterns` heading.

The section uses this structure (Decision / Scope / Constraints bodies are taken verbatim from `..\scoring-agent-adr-draft.md`):

```markdown
---

## ADR-1: Scoring Architecture — Deterministic Code with Agent-Driven Judgment

**Decision Date:** 2026-05-18 UTC
**Status:** Accepted

**Decision:** [verbatim from draft]

**Scope:** [verbatim from draft]

**Constraints:**
[verbatim from draft]

**Supporting discovery:** The full 19-site catalog, latency analysis, cost projection, determinism analysis, reproducibility model, and governance model that informed this decision are archived at `docs/decisions/OTA-653-scoring-agent-discovery.md`.

**Change Log**

| Date | Story | Change |
|---|---|---|
| 2026-05-18 UTC | OTA-653 | Initial decision recorded. Scoring agent adoption declined: bright-line sites are deterministic and correct, judgment sites are already agent-driven, consolidation would degrade harness determinism assertions and increase cost and latency without quality benefit. |

---
```

### 2. Update architecture-plan.md header and Change Log

- Change `Last Updated:` to `2026-05-18 UTC`.
- Append a new entry to the architecture-plan.md Change Log (preserve all existing entries):

  ```
  | 2026-05-18 UTC | OTA-653 | Introduced ADR convention to this document. Added ADR-1: Scoring Architecture — Deterministic Code with Agent-Driven Judgment. Records the OTA-653 discovery outcome: scoring agent adoption declined; bright-line sites stay code, judgment sites are already agent-driven, consumer-wiring deduplication proceeds as housekeeping under OTA-535. |
  ```

### 3. Archive the discovery document inside the repo

- If `docs/decisions/` does not exist, create it with `New-Item -ItemType Directory -Path docs/decisions -Force`.
- Move `..\scoring-agent-discovery.md` to `docs/decisions/OTA-653-scoring-agent-discovery.md` using `Move-Item`.

### 4. Delete the draft

Its content is now in `architecture-plan.md`. Remove `..\scoring-agent-adr-draft.md` with `Remove-Item`.

## Acceptance criteria

- `claude_context/architecture-plan.md` contains the new ADR-1 section at the location specified, with all fields populated verbatim from the draft.
- `claude_context/architecture-plan.md` `Last Updated` header reads `2026-05-18 UTC`.
- `claude_context/architecture-plan.md` Change Log has the new entry referencing OTA-653.
- `docs/decisions/OTA-653-scoring-agent-discovery.md` exists with the full discovery content.
- `..\scoring-agent-discovery.md` and `..\scoring-agent-adr-draft.md` no longer exist.
- No other SoT docs (`business-rules.md`, `CLAUDE.md`, `UI-GUIDANCE.md`, `auth-process.md`, `SCHWAB-LOGIN-PROCESS.md`, `azure-naming-conventions.md`) were modified.
- No code files were modified.

## Out of scope

- Modifying `business-rules.md` (this is an architectural decision, not a business rule).
- Modifying `CLAUDE.md` or any other SoT doc.
- Creating new Jira tickets (handled in a separate prompt for the OTA-535 cleanup Stories).
- Changing any code (scoring engines, harness, frontend).
- Re-running the QA harness (no code changed).
- Transitioning OTA-653 in Jira (Don will advance status manually after commit).

## Verification steps

1. `cat claude_context/architecture-plan.md` — confirm the ADR-1 section is present and well-formed.
2. `Get-Content claude_context/architecture-plan.md -TotalCount 5` — confirm `Last Updated: 2026-05-18 UTC` header.
3. `Get-Content claude_context/architecture-plan.md -Tail 20` — confirm the new Change Log entry referencing OTA-653.
4. `Get-ChildItem docs/decisions/` — confirm `OTA-653-scoring-agent-discovery.md` is present.
5. `Test-Path ..\scoring-agent-adr-draft.md` should return `False`.
6. `Test-Path ..\scoring-agent-discovery.md` should return `False`.
7. `git status` — confirm only `claude_context/architecture-plan.md` and `docs/decisions/OTA-653-scoring-agent-discovery.md` show changes.

## Commit instruction

I have been instructed to commit. Do you approve? (yes / no)

## Coordination footer

Independent — no downstream dependency.

## Commit message template (if committing)

```
OTA-653 docs: introduce ADR convention to architecture-plan.md; add ADR-1 Scoring Architecture; archive discovery

- Establishes ADR-1: Scoring Architecture — Deterministic Code with Agent-Driven Judgment
- Records the OTA-653 outcome: scoring agent adoption declined; bright-line stays code, judgment stays in existing SKILL.md-mediated agent paths
- Archives full discovery to docs/decisions/OTA-653-scoring-agent-discovery.md
- No code or business-rule changes
```
