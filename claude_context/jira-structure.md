# Jira Structure (Profile)

**Scope:** Profile level — applies to all of Don's projects under this profile (currently OTA, future TMTC projects).
**Last Updated:** 2026-05-19 UTC
**Governing Story:** OTA-569 (Documentation Governance — Profile)
**Creation Subtask:** OTA-589

---

This document defines the Jira hierarchy, issue types, parenting rules, and API conventions used across all projects on this profile. Project-specific facts (status IDs, transition IDs, common Epic parents) live in each project's `CLAUDE.md`, not here.

---

## Why this exists

Without a profile-level reference, every project's `CLAUDE.md` would re-derive the hierarchy and parenting rules from scratch. That pattern produced drift — projects ended up with subtly different rules, and ticket creation across projects required re-learning each time. This doc fixes the universal layer; each project layers its own status IDs and transition IDs on top.

It also captures one specific license-driven decision: **this profile does not use the Feature issue type.** That decision is restated explicitly here so any reader of this doc understands it without needing to chase a footnote.

---

## Active hierarchy

The active hierarchy across all projects on this profile is:

**Epic → Story → Subtask**

- **Epic** is the top of the tree
- **Story** parents directly to an Epic (no intermediate Feature level)
- **Subtask** parents to a Story
- **Bug** is an issue type that may sit at Story level (parented to an Epic, sibling to Stories) or at Subtask level (parented to a Story)

This profile does not use the Feature issue type. If Feature is referenced anywhere in older content, in another profile's docs, or in a project's CLAUDE.md, it is wrong — ignore it and parent Stories directly to Epics. If the license tier ever changes, this document will be updated; until then, treat Feature as forbidden.

---

## Issue types and their roles

| Type | Role | Parents to |
|---|---|---|
| Epic | Top-level container; perpetual or time-bounded depending on the work | (none — Epics are roots) |
| Story | Unit of delivery work; one Story = one Claude Code prompt or one cohesive change set | An Epic |
| Subtask | Sub-unit of a Story; used when the work spans multiple commits or sessions | A Story (or a Story-level Bug) |
| Bug (Story level) | Defect tracked as a sibling to Stories under the same Epic | An Epic |
| Bug (Subtask level) | Sub-defect inside a larger Story's scope | A Story |

Notes:
- Subtasks have no children — they are leaf nodes
- Bugs at Story level may have Subtasks under them (mirrors Story behavior)
- Stories are not closed when used as Documentation Governance containers — they stay open as Subtasks accumulate over time

---

## Parenting rules

- **Stories** parent directly to an **Epic**
- **Bugs at Story level** parent directly to an **Epic** (sibling of Stories)
- **Subtasks** parent to a **Story** (or to a Story-level Bug)
- **Subtasks at Bug level** parent to a **Story**
- **Subtasks have no children** — they are leaf nodes
- **Stories cannot have Stories under them** — there is no nested Story hierarchy
- **Subtasks cannot have Subtasks** — there is no nested Subtask hierarchy

If a planned hierarchy violates any of these (e.g., a Subtask under another Subtask), restructure before creating tickets. Do not work around with arbitrary parent fields.

---

## Issue numbering discipline

- Never invent or pre-assign issue keys (e.g., never write `XXX-549` in a prompt or branch name before the ticket is created)
- Jira assigns the key at creation; use the Jira-returned key in all references, commit messages, branch names, prompt files, and change-log entries
- If a ticket reference is needed before creation, create the ticket first and then use the assigned key
- `XXX-###` is permitted only as a placeholder in template documents that demonstrate format

This rule prevents the "we thought it would be 549 but Jira gave it 551" cleanup cycle.

---

## Title conventions

Titles describe the **work**, not the **execution order**. Phase numbers, sprint numbers, "Step N — " prefixes, and similar sequencing metadata belong in descriptions, commit messages, or prompt files — never in titles. Execution order is a property of the queue, not the work item; a Subtask's parent and the prompts/artifacts that drove it carry the sequencing context. Titles that survive across reorderings and audit revisions are titles that don't embed sequencing.

Examples:

- ❌ `Phase 3b.1 — ORM model alignment` → ✅ `ORM model alignment`
- ❌ `Sprint 7 — User onboarding flow` → ✅ `User onboarding flow`
- ❌ `Step 2 of cutover — symbol normalization` → ✅ `Symbol normalization`

This rule is universal across all projects on this profile. Project-level `CLAUDE.md` files may restate it for visibility but cannot override it.

---

## Workflow phases (universal pattern)

Each project on this profile uses a phase-based workflow with the following pattern (specific status IDs and transition IDs are per-project — see each project's `CLAUDE.md` for the lookup table):

| # | Phase | Category | Who Acts |
|---|---|---|---|
| 0 | Idea | To Do | Don |
| 1 | Schedule | To Do | Don |
| 2 | Write Story | In Progress | Claude Web |
| 3 | Write Prompt | In Progress | Claude Web |
| 4 | Code & Test Complete | In Progress | Claude Code |
| 5 | Production Deployed | Done | Automation / manual override |
| C | Cancelled | Done | Don / Automation |

The terminology is *phases*, not sprints. Sprint-based planning is not used on this profile.

### Quirk worth knowing

The transition named **"To Do"** in the workflow editor moves an issue to **Schedule** status (not "To Do" — there is no "To Do" status in this workflow). New work entering the Schedule phase uses this transition. The naming mismatch is a Jira workflow-editor artifact and is not worth fixing in the editor.

---

## API conventions

When creating, transitioning, or modifying issues via the Atlassian MCP or the Jira REST API, follow these conventions. They reflect lessons learned from prior failures.

### Parent field placement

- The `parent` parameter is **always a direct named parameter** at the top level of the create request
- **Never** nest `parent` inside `additional_fields` — that path silently fails (no error, but parenting doesn't apply)

### Content format

- Prefer `contentFormat: "markdown"` when the MCP tool supports it — descriptions render correctly and authoring is simple
- Fall back to ADF (Atlassian Document Format) only when `markdown` is not available (typically the REST API path)
- ADF requires a structured JSON shape; mistakes in ADF result in unrendered or garbled descriptions

### Transition selection

- Use transition IDs, not transition names — names can be ambiguous (see the "To Do" quirk above)
- Each project's `CLAUDE.md` carries the canonical transition ID table for that project
- Do not guess transition IDs from name alone

### Bulk operations

- Before creating multiple tickets in one batch, restate the parent and the count, and wait for explicit go from Don
- Search Jira before creating any ticket that might already exist — duplicate cleanup is more expensive than the search
- Verify hierarchy before creating Subtasks — confirm the parent Story exists and is the right one

### Authentication

- Each project supplies its own credentials. Tokens come from Azure Key Vault or equivalent secrets manager — never assume the env var is populated
- Don's email plus an API token forms Basic auth; never share or log the token

---

## What does NOT live here

- Project-specific status IDs, transition IDs, issue type IDs → each project's `CLAUDE.md`
- Project-specific Common Epic parents → not documented; Don supplies at runtime
- Bug-fix session protocol → project-level `bugfix.md`
- Documentation Governance Epic structure → each project's `CLAUDE.md` references its own Documentation Governance Epics
- Prompt-writing convention (Mechanism A + B) → `prompt-style.md`
- Build execution and parallel session protocol → `build-execution.md`
- Claude.ai interaction patterns → `claude-web.md`

---

## Change Log

| Date | Subtask | Change |
|---|---|---|
| 2026-05-19 UTC | OTA-674 | Added "Title conventions" section. Codifies the universal rule: titles describe the work, not the execution order. Phase numbers, sprint numbers, and step prefixes belong in descriptions, commit messages, or prompt files — never in titles. Applies to all projects on this profile; project-level overrides are not permitted. |
| 2026-05-06 UTC | OTA-589 | Initial creation. Replaces a workaround where Jira hierarchy and parenting rules were duplicated inside each project's `CLAUDE.md`. Codifies the no-Feature decision driven by license tier — explicit "if you see Feature anywhere, it's wrong, ignore it" guidance included. Documents the transition-name quirk ("To Do" transition → Schedule status). Captures API lessons learned: parent must be direct named param, prefer markdown contentFormat, use transition IDs not names. |
