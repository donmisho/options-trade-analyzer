# OTA-653 — Scoring Agent Architecture: Discovery & ADR Draft

## Terminal context

- This terminal: Terminal A (single-stream, read-only inspection)
- Concurrent terminals: none
- Cross-terminal dependencies: none

## Required reading

Before any inspection, read the canonical SoT docs:

```
cat claude_context/CLAUDE.md
cat claude_context/architecture-plan.md
cat claude_context/business-rules.md
```

Then read the QA harness spec so Section 6 (determinism analysis) has the exact assertion set to address:

```
cat qa-harness-spec.md
```

If `qa-harness-spec.md` is not at repo root, search for it:

```
Get-ChildItem -Recurse -Filter "qa-harness-spec.md" | Select-Object -ExpandProperty FullName
```

## Relevant Context — Do Not Deviate Without Escalation

### Source: OTA-653 description — Background

OTA-646's six-ticket fix shipped to dev. Three QA samples reproduced the cross-surface drift disease in distinct forms _after_ the fix. The narrative writer ("Claude's Read") is consistently the most reliable scoring component in every QA sample. It correctly identifies structural mismatches, directional misalignment, and qualitative trade weaknesses while the surrounding code-based score/verdict pipeline disagrees with it. The narrative is, in effect, already doing the work the rest of the scoring code is supposed to do.

### Source: OTA-653 description — Two hypotheses

Both must be addressed in the discovery output. Do not pre-decide.

**Hypothesis 1 (consolidation):** drift between surfaces stems from scoring being implemented multiple times across the code base. Routing all scoring through a single agent with rules defined in a skill could eliminate this class of drift entirely.

**Hypothesis 2 (wiring discipline):** cross-surface drift is primarily a _consumer-wiring_ problem (not every UI surface calls the canonical source), and an agent doesn't fix that — wiring discipline is required regardless of whether the source of truth is a function or an agent.

### Source: OTA-653 description — Categorization rubric

- **Bright-line:** gates, lookups, deterministic computation (debit % cap, EV < 0, `compatible_structures` lookup, R:R thresholds). No judgment required.
- **Judgment:** scoring components that weigh multiple signals (technical alignment, structure fit, EV scoring), verdict bucketing where the cutoff is debatable, narrative authorship.

### Source: OTA-653 description — Default working proposal

Bright-line stays code; judgment moves to agent; consumer-wiring problem remains its own concern. Discovery must challenge or confirm this default with evidence from the codebase mapping — do not adopt by default without explicit argument.

### Source: CLAUDE.md § Document Governance Rules — ADR format

ADRs are prescriptive rulebooks only. Each ADR carries: title, decision (the rule), Decision Date, Change Log. No deliberation artifacts in the ADR — deliberation goes in the discovery document instead. If the ADR contains "we considered X but rejected it for Y," the deliberation is wrong-place; move it to the discovery doc and leave the ADR with just the final rule.

### Source: business-rules.md (cat for current values)

Embed during inspection the current values for: debit % of width cap (per strategy), EV threshold for hard PASS, R:R minimum per strategy, DTE windows per strategy. These are the bright-line gates — the discovery must list each one with its current code location.

## Scope

This is a discovery-only Story. Output is Markdown documents for Don's review. No code changes, no commits, no Jira transitions, no application changes.

Expected duration: 3–5 hours of focused inspection plus writing.

### Phase 1 — Codebase mapping (read-only inspection)

Goal: produce an exhaustive list of every site in the codebase that produces a score, a verdict, a compatibility decision, or a narrative.

Starting points to inspect (this is the seed list, not exhaustive — follow imports and references outward from each):

```
# Backend scoring
app/analysis/strategy_scorer.py
app/analysis/vertical_engine.py
app/analysis/long_call_engine.py
app/analysis/strategy_routing.py
app/analysis/scoring/

# Backend API surface
app/api/analysis_routes.py
app/api/evaluation_routes.py

# Backend models
app/models/schemas.py

# Skill / agent surface
app/skills/

# Frontend score consumers
web/src/strategy-configs/
web/src/components/TradeEvaluationCard.jsx
web/src/components/StrategyScorecard.jsx
web/src/pages/
```

Use `Select-String` (or `grep` if available) to find scoring computation references:

```
Select-String -Path "app\**\*.py" -Pattern "score|verdict|fitting_strategies|is_compatible|compatible_structures|hard_pass|bucket" -List
Select-String -Path "web\src\**\*.jsx","web\src\**\*.js" -Pattern "score|verdict|fittingStrategies|bestFit|narrative" -List
```

For each site found, capture:

- File path and line range
- What it produces (score component, score total, verdict label, compatibility decision, narrative)
- What it consumes (inputs and their source)
- Whether it is called from one place or many (search for call sites)
- Bright-line vs Judgment classification with one-sentence justification

### Phase 2 — Categorization tally

After mapping, summarize:

- Total sites found
- Bright-line count + list with current locations
- Judgment count + list with current locations
- Sites that are unclear (require human review) + the ambiguity

A site is "unclear" when the same function does both bright-line and judgment work (e.g., applies a hard gate AND weighs multiple signals). Flag these — they're the most informative for the agent-vs-code decision.

### Phase 3 — Latency analysis

For each surface that consumes scoring output, estimate the round-trip latency impact of replacing code-based scoring with an agent call:

| Surface | Current call shape | Current latency | Agent call shape | Projected latency | Tolerable? |
|---|---|---|---|---|---|

Surfaces to analyze (at minimum):

- Security Strategies dashboard scan (typical: 20 symbols × 4 strategies = 80 evaluations)
- Trades page initial render (typical: 1 symbol × N candidates per strategy, where N is the candidate count after filtering)
- Trade detail expansion (single trade)
- Evaluate button click (single trade, intentional user action)

For "tolerable," apply this rubric: single-trade user-initiated calls (Evaluate button, trade detail expand) tolerate up to ~3s round trip. Dashboard scans (Security Strategies, Trades grid) tolerate ~500ms total or they break the page-load expectation.

Cite current latency from any timing logs available, or derive from the call shape. Project agent latency from typical Foundry Sonnet response times (assume 1.5–3s per call without batching, 500ms–1s with prompt caching and small responses).

### Phase 4 — Cost projection

Estimate production-scale Foundry call volume and monthly cost.

Assumptions to make explicit:

- Daily active users (start at 1 — Don's personal use)
- Sessions per day per user
- Symbols scanned per session
- Candidates evaluated per session
- Token cost per call (use current Foundry pricing for `claude-sonnet-4-6`)

Output: monthly cost at current single-user load, monthly cost at 10× scale (10 users), break-even point against any consolidation savings (engineering time saved on cross-surface drift fixes).

### Phase 5 — Determinism analysis

The OTA-652 harness includes D-class assertions (D1–D6) that enforce strict cross-run equality or near-equality on identical inputs. Read `qa-harness-spec.md` Section 6b for the exact list.

For each D-class assertion, answer:

1. Does it survive an LLM-based scoring path with `temperature=0`?
2. If not, what softening is required (e.g., relaxed similarity threshold, embedding-based comparison, statistical agreement over N runs)?
3. Does the softening lose diagnostic power on the kind of bugs the harness currently catches (e.g., the VOO lottery-ticket 11-point determinism swing from OTA-652 Phase 2)?

Produce a side-by-side table: assertion → survives at temp=0 (Y/N) → required softening → diagnostic power impact.

### Phase 6 — Reproducibility for backtesting

If scoring becomes agent-driven, a score produced on date X with skill version Y must be reproducible months later. Propose a concrete versioning model:

- How are skill versions identified? (semver tag, content hash, commit SHA, all three?)
- Where is the skill version recorded for each score? (in the agent_run_log table? on the position record?)
- How is "rerun this score against this skill version" implemented? (skill files in git history are sufficient if commits are pinned, or does the system need a skill registry?)
- What happens to historical scores when a skill is edited?

Don't propose "we'd version skills somehow." Pick one concrete model and write it down.

### Phase 7 — Governance model

If scoring becomes agent-driven, skill files become the source of truth for evaluation logic. Today: code is governed by CI, tests, code review, branch protection, and the OTA workflow (Schedule → Write Story → Write Prompt → Code & Test Complete → Production Deployed). What is the equivalent for skill edits?

Address concretely:

- Editorial authority: who can edit a skill file? (Just Don? Don + Claude Web? Don + delegated reviewers?)
- Review process: what gate sits between "skill edit drafted" and "skill edit in production"?
- Test bed: how is a skill change validated before it ships? (Run against the OTA-652 harness corpus? A separate skill-eval suite?)
- Rollback: if a skill edit produces bad scores in production, what is the rollback procedure? (Revert in git? Roll forward with a fix? Pin the prior version?)
- Conflict resolution: if two skill edits land in different sessions with overlapping rules, who arbitrates?

### Phase 8 — Hybrid scope proposal

Combining the mapping (Phase 1–2), latency (Phase 3), cost (Phase 4), determinism (Phase 5), reproducibility (Phase 6), and governance (Phase 7) findings, propose the hybrid scope:

- What stays code (which bright-line sites, by name)
- What moves to agent (which judgment sites, by name)
- What stays a wiring problem regardless (which consumers, by name)
- Migration order if proceeding (which sites first, which last, what gates between phases)

Challenge or confirm the default working proposal (bright-line stays code; judgment moves to agent; consumer-wiring problem remains its own concern). If confirmed, say why. If challenged, propose alternative.

### Phase 9 — Deliverables

Produce three files in the parent directory (outside the project tree initially, per OTA-653 description):

1. **`..\scoring-agent-discovery.md`** — Full discovery document. All eight phases above, in narrative form with the tables and lists from each phase. This is the deliberation document — it can contain "we considered X but rejected it for Y" reasoning, comparison tables, alternative proposals.

2. **`..\scoring-agent-adr-draft.md`** — ADR draft block ready to paste into `architecture-plan.md`. **Prescriptive only.** No deliberation. Format:

   ```markdown
   ### ADR: Scoring Agent Adoption

   **Decision Date:** 2026-05-18 UTC
   **Decision:** [one paragraph stating the rule — proceed with agent / don't proceed / proceed with hybrid at scope X]
   **Scope:** [if hybrid: list of specific scoring sites that move to agent, list that stay code]
   **Constraints:** [latency budget, cost budget, versioning model, governance requirements]
   **Change Log:**
   | Date | Story | Change |
   | 2026-05-18 UTC | OTA-653 | Initial decision recorded. |
   ```

3. **In the body of your final terminal message to Don:** an explicit recommendation in one sentence. One of: "Proceed with agent at scope X (see ADR)," "Do not proceed with agent — consolidation should happen via wiring discipline instead," or "Proceed with explicit hybrid at scope Y (see ADR)." No hedging, no "it depends."

## Acceptance criteria

- [ ] Codebase scoring-site map is exhaustive (no scoring decision left uncategorized) — confirm by running the `Select-String` searches above and verifying every match is either in the map or explicitly excluded with reason
- [ ] Each site is classified Bright-line / Judgment / Unclear with one-sentence justification
- [ ] Latency projection has concrete numbers for all four named surfaces, not adjectives
- [ ] Cost projection has concrete monthly figures at single-user and 10×-user scale, with the assumption set listed
- [ ] Determinism analysis covers every D-class assertion from `qa-harness-spec.md` Section 6b
- [ ] Versioning model is one concrete proposal, not a menu of options
- [ ] Governance model names specific roles, processes, and rollback steps
- [ ] Hybrid scope proposal challenges or confirms the default working proposal with evidence from Phases 1–7
- [ ] ADR draft is prescriptive only — no deliberation content leaks in
- [ ] Final recommendation is unambiguous (one sentence, one of three options)
- [ ] All three deliverables exist at the paths specified (two `.md` files plus one terminal-message paragraph)

## Out of scope

- Any implementation code. This Story produces decision documents only.
- Skill rule authoring — covered downstream if agent is approved.
- Migration path planning beyond Phase 8's ordered proposal — detailed migration plans come downstream.
- Vendor/model selection (Sonnet vs Opus vs alternatives) — covered downstream if agent is approved. Discovery may assume current Foundry deployment (`claude-sonnet-4-6`) for latency and cost projections.
- Jira ticket creation. If discovery identifies follow-up work, list it in the discovery doc; Don creates tickets later.
- File commits. Discovery output files are written outside the project tree (`..\<filename>`) so they don't accidentally get committed.

## Verification steps

Before the final terminal message, run through this checklist:

1. Open `..\scoring-agent-discovery.md`. Confirm all nine phases are present with the required tables.
2. Open `..\scoring-agent-adr-draft.md`. Confirm it has Decision Date, Decision, Scope, Constraints, Change Log — and nothing else (no "we considered" or "trade-offs" or "alternatives" sections).
3. Search the discovery doc for hedge words ("probably," "likely," "it depends," "we could," "might"). Where they appear in the recommendation or the ADR, replace with concrete language or move the hedge to the deliberation sections only.
4. Verify the final recommendation sentence is one of the three explicit options stated above.
5. Confirm no application code was modified and no git commits were made. `git status` shows clean working tree relative to the start of the session.

## Commit instruction

I have been instructed NOT to commit. This Story produces decision documents only — no application code, no Jira transitions, no application changes. The discovery output files are written outside the project tree (`..\scoring-agent-discovery.md` and `..\scoring-agent-adr-draft.md`) and are intentionally not part of the repo.

If Don approves the recommendation, a follow-up Story (or new Epic) will handle implementation; if Don rejects, the ADR draft becomes the documented decision-against and is committed to `claude_context/architecture-plan.md` under a separate prompt.

## Coordination footer

Independent — no downstream dependency until Don decides agent direction.

After this prompt completes and Don reviews the discovery doc, the next prompt depends on the decision:

- If Don decides **proceed with agent** → new Epic spawns with Stories for skill authoring, scorer endpoint, consumer migration, harness assertion updates, governance tooling. New prompts written then.
- If Don decides **don't proceed** → a short prompt to file the ADR draft into `claude_context/architecture-plan.md` with the "against" decision recorded.
- If Don decides **proceed with hybrid** → ADR is committed as written; new Epic spawns for the in-scope sites only.

Until that decision, no follow-up prompt exists.

## Commit message template

Not applicable — this Story does not commit.
