"""
Agent run logger for QA agent system.

Writes to the existing agent_run_log table via SQLAlchemy.
Falls back to JSONL file at agents/qa-context/agent-run-log.jsonl
if DATABASE_URL is not set.
"""

import os
import sys
import json
import uuid
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

JSONL_FALLBACK_PATH = Path(__file__).parent.parent / "qa-context" / "agent-run-log.jsonl"

VALID_AGENT_TYPES = {"qa_ux", "qa_data", "fe_dev", "be_dev"}
VALID_RUN_TYPES = {"compliance_check", "data_validation", "fix_implementation"}
VALID_STATUSES = {"COMPLETE", "FAILED", "ESCALATED"}


def log_run(
    agent_type: str,
    run_type: str,
    input_context: dict,
    output_summary: dict,
    status: str,
    tokens_used: int = 0,
    model: str = "",
    prompt_version: str = "1.0",
) -> str:
    """
    Log an agent run. Returns the run_id (UUID string).

    Args:
        agent_type:     One of qa_ux, qa_data, fe_dev, be_dev
        run_type:       One of compliance_check, data_validation, fix_implementation
        input_context:  Dict describing what the agent was given
        output_summary: Dict describing what the agent produced
        status:         COMPLETE, FAILED, or ESCALATED
        tokens_used:    Token count for the run (0 if unknown)
        model:          Model identifier string
        prompt_version: Version of the SKILL.md prompts used
    """
    run_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()

    record = {
        "run_id": run_id,
        "agent_type": agent_type,
        "run_type": run_type,
        "input_context": input_context,
        "output_summary": output_summary,
        "tokens_used": tokens_used,
        "model": model,
        "prompt_version": prompt_version,
        "status": status,
        "created_at": created_at,
    }

    db_url = os.getenv("DATABASE_URL")
    if db_url:
        try:
            _write_to_db(record, db_url)
            logger.info(f"agent_run_log: wrote run {run_id} ({agent_type}/{status})")
            print(f"[agent-run-logger] Logged run {run_id} to database ({agent_type} / {status})")
            return run_id
        except Exception as e:
            logger.warning(f"DB write failed ({e}), falling back to JSONL")

    _write_to_jsonl(record)
    print(f"[agent-run-logger] Logged run {run_id} to {JSONL_FALLBACK_PATH} ({agent_type} / {status})")
    return run_id


def _write_to_db(record: dict, db_url: str):
    """Write record to agent_run_log table via SQLAlchemy (sync)."""
    # Import here to avoid hard dependency when DB not configured
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    from sqlalchemy import create_engine, text

    # Transform aioodbc URL to sync pyodbc for this standalone script
    sync_url = db_url.replace("mssql+aioodbc://", "mssql+pyodbc://").replace("mssql+pyodbc+aioodbc://", "mssql+pyodbc://")

    engine = create_engine(sync_url)
    with engine.connect() as conn:
        conn.execute(
            text("""
                INSERT INTO agent_run_log
                    (run_id, agent_type, run_type, input_context, output_summary,
                     tokens_used, model, prompt_version, status, created_at)
                VALUES
                    (:run_id, :agent_type, :run_type, :input_context, :output_summary,
                     :tokens_used, :model, :prompt_version, :status, :created_at)
            """),
            {
                **record,
                "input_context": json.dumps(record["input_context"]),
                "output_summary": json.dumps(record["output_summary"]),
            },
        )
        conn.commit()


def _write_to_jsonl(record: dict):
    """Append record to JSONL fallback file."""
    JSONL_FALLBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(JSONL_FALLBACK_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    """Test mode: python agent-run-logger.py"""
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent.parent / ".env")

    print("Testing agent-run-logger...")
    run_id = log_run(
        agent_type="qa_ux",
        run_type="compliance_check",
        input_context={"ticket_key": "OTA-TEST", "app_url": "http://localhost:5173"},
        output_summary={"total": 5, "pass": 4, "fail": 1, "pass_rate": 0.8},
        status="COMPLETE",
        tokens_used=1234,
        model="claude-sonnet-4-6",
        prompt_version="1.0",
    )
    print(f"Test run logged with ID: {run_id}")
