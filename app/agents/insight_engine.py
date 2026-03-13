"""
InsightEngine — Phase 3.6 Stream A3.

Generic insight generation engine. Given a detected deviation for any monitored
entity, calls Claude to craft a short actionable insight and writes it to the
insights table.

Domain-agnostic design:
  - domain='options' → uses app/skills/insight-engine/domains/options/SKILL.md
  - domain='manufacturing' → uses app/skills/insight-engine/domains/manufacturing/SKILL.md
  - The generic skill at app/skills/insight-engine/SKILL.md serves as fallback

Deduplication:
  One active insight per (entity_id, deviation_type). If an active insight already
  exists for the same entity and deviation type, it is updated in-place rather than
  creating a new row.

WHY update-in-place: Positions that remain in a warning state will be flagged on
every monitor run. Creating a new insight each time would flood the feed. The
practitioner sees one card per situation, and it stays current.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.telemetry import invoke_with_tracing
from app.models.database import Insight, AgentRunLog
from app.models.schemas import DeviationResult
from app.skills.skill_loader import get_skill

if TYPE_CHECKING:
    from app.ai.foundry_adapter import FoundryEvalAdapter

logger = logging.getLogger(__name__)


class InsightEngine:
    """
    Generic insight generation engine. Domain-agnostic.

    Instantiate with a domain name and skill path. The same engine class
    serves all domains; only the SKILL.md and entity vocabulary change.
    """

    def __init__(
        self,
        ai_provider: "FoundryEvalAdapter",
        domain: str,
        skill_path: str = "insight-engine",
    ):
        self._provider = ai_provider
        self.domain = domain
        # Try domain-specific skill first; fall back to generic
        domain_skill_path = f"insight-engine/domains/{domain}"
        try:
            self._skill = get_skill(domain_skill_path)
            logger.debug(f"InsightEngine: loaded domain skill '{domain_skill_path}'")
        except FileNotFoundError:
            self._skill = get_skill(skill_path)
            logger.debug(f"InsightEngine: no domain skill for '{domain}' — using generic")

    async def generate(
        self,
        db: AsyncSession,
        entity_id: str,
        entity_label: str,
        deviation: DeviationResult,
        context_signals: List[dict],
        agent_run_id: Optional[str] = None,
    ) -> Insight:
        """
        Craft an insight for a detected deviation and persist it.

        1. Check for existing active insight (avoid duplicates)
        2. Build prompt from SKILL.md
        3. Call Claude
        4. Parse JSON response
        5. Write/update insights table
        6. Write agent_run_log
        7. Return the Insight row
        """
        run_id = agent_run_id or str(uuid.uuid4())

        system_prompt = self._skill.get("INSIGHT_SYSTEM")
        user_message = self._skill.render(
            "INSIGHT_USER",
            entity_id=entity_id,
            entity_label=entity_label,
            domain=self.domain,
            deviation_type=deviation.deviation_type or "UNKNOWN",
            deviation_score=deviation.deviation_score,
            observation_json=json.dumps(deviation.observation),
            baseline_json=json.dumps(deviation.baseline),
            description=deviation.description,
            context_signals_json=json.dumps(context_signals, indent=2),
        )

        # Call Claude
        raw_text = ""
        input_tokens = output_tokens = 0
        model_name = ""

        async with invoke_with_tracing(
            "insight-engine", "generate",
            symbol=entity_id,
            session_id=run_id,
            prompt_version=self._skill.prompt_version,
        ) as span_ctx:
            try:
                result = await self._provider.chat(
                    system_prompt, user_message, max_tokens=500
                )
                raw_text = result["text"]
                input_tokens = result["input_tokens"]
                output_tokens = result["output_tokens"]
                model_name = result.get("model", "")
                span_ctx["input_tokens"] = input_tokens
                span_ctx["output_tokens"] = output_tokens
            except Exception as e:
                logger.error(f"InsightEngine: Claude call failed for {entity_id}: {e}")
                raise

        # Parse response
        parsed = self._parse_insight_response(raw_text)
        title = parsed.get("title", f"Deviation detected: {entity_id}")
        body = parsed.get("body", deviation.description)
        severity = parsed.get("severity", "WARNING")
        if severity not in ("INFO", "WARNING", "CRITICAL"):
            severity = "WARNING"
        recommended_actions = parsed.get("recommended_actions", [
            {"label": "Dismiss", "action": "dismiss"}
        ])

        # Check for existing active insight (deduplication)
        now = datetime.now(timezone.utc)
        existing = await self._find_existing_active(db, entity_id, deviation.deviation_type)

        if existing:
            # Update in-place
            existing.title = title
            existing.body = body
            existing.severity = severity
            existing.deviation_score = deviation.deviation_score
            existing.observation = json.dumps(deviation.observation)
            existing.baseline = json.dumps(deviation.baseline)
            existing.recommended_actions = json.dumps(recommended_actions)
            existing.source_signals = json.dumps(context_signals)
            existing.agent_run_id = run_id
            insight = existing
            logger.info(
                f"InsightEngine: updated existing insight {existing.insight_id} "
                f"for {entity_id} ({deviation.deviation_type})"
            )
        else:
            # Create new
            insight = Insight(
                insight_id=str(uuid.uuid4()),
                domain=self.domain,
                entity_id=entity_id,
                entity_label=entity_label,
                observation=json.dumps(deviation.observation),
                baseline=json.dumps(deviation.baseline),
                deviation_score=deviation.deviation_score,
                deviation_type=deviation.deviation_type or "UNKNOWN",
                title=title,
                body=body,
                severity=severity,
                recommended_actions=json.dumps(recommended_actions),
                status="ACTIVE",
                source_signals=json.dumps(context_signals),
                agent_run_id=run_id,
                created_at=now,
            )
            db.add(insight)
            logger.info(
                f"InsightEngine: created insight {insight.insight_id} "
                f"for {entity_id} ({deviation.deviation_type}, severity={severity})"
            )

        # Write agent_run_log
        db.add(AgentRunLog(
            run_id=run_id,
            agent_name="insight-engine",
            stage="generate",
            symbol=entity_id,
            user_id=None,
            prompt_system=system_prompt,
            prompt_user=user_message,
            prompt_version=self._skill.prompt_version,
            market_snapshot={"context_signals": context_signals},
            trade_snapshot={"entity_id": entity_id, "domain": self.domain},
            model_response_raw=raw_text,
            verdict=severity,
            verdict_summary=title,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model_name=model_name,
            created_at=now,
        ))

        await db.commit()
        return insight

    async def get_active(
        self,
        db: AsyncSession,
        entity_id: Optional[str] = None,
    ) -> List[Insight]:
        """Return ACTIVE insights for this domain, optionally filtered by entity."""
        stmt = select(Insight).where(
            and_(Insight.domain == self.domain, Insight.status == "ACTIVE")
        )
        if entity_id:
            stmt = stmt.where(Insight.entity_id == entity_id)
        stmt = stmt.order_by(Insight.created_at.desc())
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def dismiss(self, db: AsyncSession, insight_id: str) -> Optional[Insight]:
        """Mark an insight as DISMISSED."""
        insight = await self._get_by_id(db, insight_id)
        if insight:
            insight.status = "DISMISSED"
            insight.dismissed_at = datetime.now(timezone.utc)
            await db.commit()
        return insight

    async def mark_acted_on(self, db: AsyncSession, insight_id: str) -> Optional[Insight]:
        """Mark an insight as ACTED_ON."""
        insight = await self._get_by_id(db, insight_id)
        if insight:
            insight.status = "ACTED_ON"
            insight.acted_on_at = datetime.now(timezone.utc)
            await db.commit()
        return insight

    # ── Private helpers ────────────────────────────────────────────────────────

    async def _find_existing_active(
        self,
        db: AsyncSession,
        entity_id: str,
        deviation_type: Optional[str],
    ) -> Optional[Insight]:
        """Find an existing ACTIVE insight for the same entity + deviation type."""
        conditions = [
            Insight.domain == self.domain,
            Insight.entity_id == entity_id,
            Insight.status == "ACTIVE",
        ]
        if deviation_type:
            conditions.append(Insight.deviation_type == deviation_type)
        result = await db.execute(select(Insight).where(and_(*conditions)))
        return result.scalar_one_or_none()

    async def _get_by_id(self, db: AsyncSession, insight_id: str) -> Optional[Insight]:
        result = await db.execute(
            select(Insight).where(Insight.insight_id == insight_id)
        )
        return result.scalar_one_or_none()

    def _parse_insight_response(self, raw: str) -> dict:
        """Parse Claude's JSON response."""
        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            inner = "\n".join(lines[1:]).strip()
            if inner.endswith("```"):
                inner = inner[:-3].strip()
            text = inner
        try:
            return json.loads(text)
        except Exception as e:
            logger.error(f"InsightEngine: failed to parse response: {e}\nRaw: {raw[:200]}")
            return {}
