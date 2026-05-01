# CLAUDE.md — Root Pointer

**This file is a pointer. The canonical CLAUDE.md lives at `claude_context/CLAUDE.md`.**

This root file exists because Claude Code auto-loads `CLAUDE.md` from the project root at session start, but the project's actual source-of-truth documents (CLAUDE.md, architecture-plan.md, business-rules.md, UI-GUIDANCE.md, auth-process.md, SCHWAB-LOGIN-PROCESS.md, azure-naming-conventions.md) are versioned under `claude_context/` so they accumulate proper git history.

This file does almost nothing. It only exists to bootstrap the session.

---

## First action of every Claude Code session

Before any other work — before answering, before reading, before planning — run:

```
cat claude_context/CLAUDE.md
```

That file is the workflow source of truth. Everything you need to know about how to operate in this repo (Jira workflow, dev environment, deploy procedures, house style rules, Source of Truth Documents inventory, Prompt Writing Convention) lives there.

If the user's first message includes a Claude Code prompt file, that prompt should ALSO begin with `cat claude_context/CLAUDE.md`. If it doesn't, request the canonical CLAUDE.md before proceeding.

---

## Why this is a pointer

The canonical `CLAUDE.md` is intentionally NOT at the repo root. Reasons:

1. **Versioning.** SoT docs live in `claude_context/` so they appear in commits and PR diffs alongside the code changes they govern.
2. **Cohesion.** All seven SoT docs sit together (`CLAUDE.md`, `architecture-plan.md`, `business-rules.md`, `UI-GUIDANCE.md`, `auth-process.md`, `SCHWAB-LOGIN-PROCESS.md`, `azure-naming-conventions.md`).
3. **No drift.** This pointer file is tiny and rarely changes. It exists only to direct Claude Code to the real source.

If this pointer is ever out of sync with `claude_context/CLAUDE.md`, the `claude_context/` version wins. Always.

---

## Standing reminder

Never make architectural, business-rule, or domain-specific decisions in this repo from session-start memory alone. The Prompt Writing Convention (documented in `claude_context/CLAUDE.md`) requires every Claude Code prompt to (A) explicitly cat the relevant SoT files and (B) embed the specific governing rules. If a prompt arrives without both, pause and request the missing context.
