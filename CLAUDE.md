# CLAUDE.md — Root Pointer

**This file is a pointer. The canonical CLAUDE.md lives at `claude_context/CLAUDE.md`.**

This root file exists because Claude Code auto-loads `CLAUDE.md` from the project root at session start, but the project's actual source-of-truth documents (CLAUDE.md, architecture-plan.md, business-rules.md, UI-GUIDANCE.md, auth-process.md, bugfix.md, SCHWAB-LOGIN-PROCESS.md, azure-naming-conventions.md, product-roadmap.md, development-environment.md, deployment-workflow.md, jira-structure.md) are versioned under `claude_context/` so they accumulate proper git history.

This file does almost nothing. It only exists to bootstrap the session.

---

## First action of every Claude Code session

Before any other work — before answering, before reading, before planning — run:

```
cat claude_context/CLAUDE.md
```

That file is the workflow source of truth. Everything you need to know about how to operate in this repo (Jira workflow, house style rules, Source of Truth Documents inventory, per-domain required reading) lives there.

If the user's first message includes a Claude Code prompt file, that prompt should ALSO begin with `cat claude_context/CLAUDE.md`. If it doesn't, request the canonical CLAUDE.md before proceeding.

---

## Why this is a pointer

The canonical `CLAUDE.md` is intentionally NOT at the repo root. Reasons:

1. **Versioning.** SoT docs live in `claude_context/` so they appear in commits and PR diffs alongside the code changes they govern.
2. **Cohesion.** All twelve SoT docs sit together: `CLAUDE.md`, `architecture-plan.md`, `business-rules.md`, `UI-GUIDANCE.md`, `auth-process.md`, `bugfix.md`, `SCHWAB-LOGIN-PROCESS.md`, `azure-naming-conventions.md`, `product-roadmap.md`, `development-environment.md`, `deployment-workflow.md`, `jira-structure.md`.
3. **No drift.** This pointer file is tiny and rarely changes. It exists only to direct Claude Code to the real source.

If this pointer is ever out of sync with `claude_context/CLAUDE.md`, the `claude_context/` version wins. Always.

---

## Standing reminder

Never make architectural, business-rule, or domain-specific decisions in this repo from session-start memory alone. The Prompt Writing Convention (documented in profile-level `prompt-style.md`) requires every Claude Code prompt to (A) explicitly cat the relevant SoT files and (B) embed the specific governing rules. If a prompt arrives without both, pause and request the missing context.

---

## Schwab account-activity sync — operational note (read before debugging "stale fills")

Quick reference recorded here because Claude Code auto-loads this file. Fold the durable
parts into `claude_context/auth-process.md` / `SCHWAB-LOGIN-PROCESS.md` under the edit gate.

- **The data path.** `app/agents/account_activity_sync.py` (the poller) runs in-process via
  APScheduler every 15 min, Mon–Fri 09:00–16:45 ET (`app/main.py`), gated by
  `settings.broker_activity_poll_enabled`. It pulls Schwab Trader API transactions/orders into
  the `broker_transactions` / `broker_orders` tables. The dashboard (a claude.ai artifact in
  the separate **Short DTE Trade Lab** repo) reads them live via the `get_trade_fills` MCP tool
  on the **OTA/Schwab - Market Data** connector. The old thinkorswim CSV import is retired.
- **The weekly cliff.** Schwab's **refresh token expires 7 days after the interactive browser
  login**, is pinned to that login, and **cannot be renewed programmatically** — every silent
  refresh preserves the original expiry (`app/providers/schwab_token_manager.py`, see
  `_store_tokens` / `_refresh_access_token`). When it lapses, `get_access_token()` raises and the
  poller records `status="error"` and writes **zero** fills. It fails **silently**: there is no
  user-facing signal by default.
- **The symptom.** `get_trade_fills` keeps returning everything already stored, so the dashboard
  shows fills up to the expiry date and nothing newer — looks like "no recent trades," is really
  "feed dead since the token expired." (First seen: feed stalled ~11-03-2026.)
- **The fix (interactive, only Don can do it).** Re-login in the browser at the analyzer:
  prod `https://oa.tmtctech.ai/api/v1/auth/schwab/login` (redirects to Schwab). Commit `48ac013`
  resets the 7-day clock on re-login. Then the next scheduled poll (or `POST /api/v1/account-activity/run`,
  Tier 2) backfills the gap. The Schwab login is **separate** from the claude.ai↔OTA connector
  OAuth (Entra) — reconnecting the connector does NOT refresh the Schwab token.
- **Status surface.** The `get_schwab_status` MCP tool (`app/api/mcp_routes.py`) reports
  `connected`, `refresh_token_expires_in_seconds` / `_at`, `expiry_warning` (true inside the warn
  window), `last_sync` (started_at, status ok|auth_error|error, fills_written, message), `poller`
  (running, interval_minutes), `app_url`, `as_of` — all timestamps ISO 8601 with offset in the
  display tz. It powers the dashboard header pill and returns an `{error, error_code, message}`
  shape on failure instead of raising.
- **Expiry alerting (OTA-857).** `app/agents/schwab_expiry_alert.py` is the early warning, both
  paths best-effort. Proactive: a daily pre-open scheduler job (08:30 ET every day, `app/main.py`,
  job id `schwab_expiry_check`) calls `check_expiry_and_alert()` — when the refresh token is valid
  but within `settings.schwab_expiry_warn_seconds` (default 2 days) of the cliff it emits a loud
  `logger.error` (prefix `SCHWAB_TOKEN_EXPIRY_WARNING`) plus an App Insights span
  (`schwab.expiry_warning`). Reactive: `AccountActivitySync._finish` calls `notify_auth_error()`
  the first time a poll fails on the expired refresh token (prefix `SCHWAB_AUTH_ERROR`, span
  `schwab.auth_error`), deduped via `_auth_error_alerted` so the 15-min cadence does not spam; a
  later clean run re-arms it. `get_schwab_status` also returns `expiry_warning: true` for the pill.
  Push is an Azure Monitor alert rule on either log prefix or span name — the app owns no mail
  channel.

## Change Log

| Date | Story | Change |
|------|-------|--------|
| 2026-05-10 | OTA-595 | Refresh root pointer to list all 12 SoT docs; add Change Log table |
| 2026-11-05 | OTA-857 | Add Schwab account-activity sync operational note (7-day refresh-token cliff, silent-failure symptom, re-login path, `get_schwab_status` tool, alerting pointer) |
