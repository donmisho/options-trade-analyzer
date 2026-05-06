# Product Roadmap (OTAR)

**Last Updated:** 2026-05-06 UTC
**Governing Story:** OTA-581 (Documentation Governance — Project)
**Initial creation Subtask:** OTA-586

---

Strategic prioritization for the OTA project lives in a separate **Jira Product Discovery (JPD)** project: **OTA Roadmap (key: OTAR)**. The OTAR project holds Roadmap Categories — high-level groupings that capture business context, target outcomes, and scope before any work becomes a delivery Idea in the OTA project.

## Project relationship

- **OTAR** (Product Discovery) — *what and why*. Holds Categories (Idea issue type) representing strategic themes. Each Category has business context, target outcome, scope, and named Umbrella Epics.
- **OTA** (Software Project) — *how and when*. Holds Epics, Stories, and Subtasks representing actual delivery work.
- **Polaris work item links** connect OTA Epics to their umbrella OTAR Category. **Every OTA Epic should link to exactly one OTAR Category.** The link is bidirectional and visible from both sides.

This structure exists because earlier phase-based grouping (Phase 2.x, 3.3.x, Sprint N) created friction — those numbers mapped to neither Jira hierarchy nor a meaningful business unit, and they bred cross-talk every time work was prioritized.

## Active OTAR Categories

| Key | Category | Scope summary |
|---|---|---|
| OTAR-7 | Trade Evaluation Quality | Hard gates, scoring weights, narrative grounding, validation reviews. Highest-impact category. |
| OTAR-8 | Trade-to-Strategy Journey (Path B) | From a found trade, identify best-fit strategy lens. Trade detail Sections A–E, Follow / Take Position. |
| OTAR-9 | Strategy-to-Trade Journey (Path A) | From a chosen strategy, find conforming trades. Strategy page, config drawer, parameter wiring. |
| OTAR-10 | Position Management & Monitoring | Position lifecycle, daily monitoring, health grades, Schwab portfolio integration. |
| OTAR-11 | Trade Discovery & Scanning | Multi-symbol scan, named watchlists, smart symbol search. |
| OTAR-12 | Live Trade Execution | Schwab order entry, OCO brackets, conditional stops, post-fill reconciliation. |
| OTAR-15 | Identity & Access | BFF OIDC, multi-IdP registry, External Services connection screen, future Identity Agent. |
| OTAR-16 | Insights & Agentic Platform | Insight Engine, multi-agent orchestration, Agent 365 governance, A2A protocol. |
| OTAR-19 | Data Sources & Market Intelligence | Earnings calendar, OpenBB, social sentiment, fundamentals, catalyst calendars. |
| OTAR-21 | Backtesting & Strategy Validation | Polygon.io historical data, backtest engine, 12-security validation set. |
| OTAR-23 | UX Foundation & Design System | Experience Framework v3 contract, shared components, formatting rules, mockup-driven design. |
| OTAR-24 | Platform Architecture, Operations, and Observability | OTel + Log Analytics, App Service ops, deployment discipline, documentation governance. |

OTAR-1 is the seed template and OTAR-13 is a duplicate of OTAR-16; both are scheduled for archive.

OTAR-27 (TMTC Application Framework) is a cross-project Category holding work that's intended to be portable across all of Don's projects, not OTA-specific. The Architecture Optimization (Framework v1) Epic (OTA-535) links to both OTAR-24 and OTAR-27.

## Creating a new OTA Epic

1. Identify which OTAR Category best fits the work
2. Create the OTA Epic
3. Create a Polaris work item link from the new Epic to the chosen OTAR Category
4. If no existing OTAR Category fits, talk to Don before creating a new Category — Categories are deliberate strategic groupings, not catch-alls

## OTAR URL

`https://tmtctech-team.atlassian.net/jira/polaris/projects/OTAR`

---

## Change Log

| Date | Subtask | Change |
|---|---|---|
| 2026-05-06 UTC | OTA-586 | Initial creation. Content ported from `CLAUDE.md` (Product Roadmap section) as part of the Documentation Governance restructure. After this file lands, the corresponding section in CLAUDE.md becomes a one-paragraph pointer. |
