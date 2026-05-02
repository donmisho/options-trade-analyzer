"""
Agent Run Logger
Writes QA agent operations to the agent_run_log table.

Uses the same schema and patterns as the existing agent_run_log in OTA.
This gives a single audit view across all agent activity — build agents,
position monitor, and QA agents share the same log table.

Usage:
    from agents.shared.agent_run_logger import log_agent_run

    log_agent_run(
        agent_type="qa_ux",
        run_type="compliance_check",
        input_context={"ticket_key": "OTA-289"},
        output_summary={"pass": 10, "fail": 1, "pass_rate": 0.909},
        tokens_used=1500,
        model="claude-sonnet-4-20250514",
        prompt_version="1.0",
        status="COMPLETE"
    )

Requires:
    DATABASE_URL — connection string for the OTA database
"""

import json
import os
import uuid
from datetime import datetime, timezone

try:
    from sqlalchemy import create_engine, text
    HAS_SQLALCHEMY = True
except ImportError:
    HAS_SQLALCHEMY = False


def log_agent_run(
    agent_type: str,
    run_type: str,
    input_context: dict,
    output_summary: dict,
    tokens_used: int = 0,
    model: str = "claude-sonnet-4-20250514",
    prompt_version: str = "1.0",
    status: str = "COMPLETE",
):
    """
    Log an agent run to the agent_run_log table.

    Args:
        agent_type: qa_ux | qa_data | fe_dev | be_dev
        run_type: compliance_check | data_validation | fix_implementation
        input_context: Dict with context (ticket key, config, etc.)
        output_summary: Dict with results (pass/fail counts, etc.)
        tokens_used: Total Claude tokens consumed
        model: Claude model used
        prompt_version: SKILL.md version
        status: COMPLETE | FAILED | ESCALATED
    """
    run_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()

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
        "created_at": timestamp,
    }

    # Try database first, fall back to file
    if HAS_SQLALCHEMY and os.environ.get("DATABASE_URL"):
        _log_to_database(record)
    else:
        _log_to_file(record)

    return run_id


def _log_to_database(record: dict):
    """Insert into agent_run_log table."""
    database_url = os.environ["DATABASE_URL"]
    engine = create_engine(database_url)

    sql = text("""
        INSERT INTO agent_run_log
            (run_id, agent_type, run_type, input_context, output_summary,
             tokens_used, model, prompt_version, status, created_at)
        VALUES
            (:run_id, :agent_type, :run_type, :input_context, :output_summary,
             :tokens_used, :model, :prompt_version, :status, :created_at)
    """)

    params = {
        **record,
        "input_context": json.dumps(record["input_context"]),
        "output_summary": json.dumps(record["output_summary"]),
    }

    with engine.connect() as conn:
        conn.execute(sql, params)
        conn.commit()

    print(f"Logged to agent_run_log: {record['run_id']} ({record['agent_type']}/{record['run_type']})")


def _log_to_file(record: dict):
    """Fall back to file-based logging when DB is unavailable."""
    from pathlib import Path

    log_dir = Path(__file__).parent.parent / "qa-context"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "agent-run-log.jsonl"

    with open(log_file, "a") as f:
        f.write(json.dumps(record, default=str) + "\n")

    print(f"Logged to file: {record['run_id']} ({record['agent_type']}/{record['run_type']})")
    if not os.environ.get("DATABASE_URL"):
        print("  (DATABASE_URL not set — using file fallback)")


if __name__ == "__main__":
    # Test: log a sample run
    run_id = log_agent_run(
        agent_type="qa_ux",
        run_type="compliance_check",
        input_context={"ticket_key": "OTA-289", "mode": "test"},
        output_summary={"pass": 10, "fail": 1, "pass_rate": 0.909},
        tokens_used=0,
        model="test",
        prompt_version="1.0",
        status="COMPLETE",
    )
    print(f"Test run logged: {run_id}")
