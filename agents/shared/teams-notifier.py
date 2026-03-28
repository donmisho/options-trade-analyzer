"""
Teams notifier for QA agent system.

Uses Power Automate Workflow webhooks (NOT legacy O365 Connectors).
Loads webhook URLs from environment variables, falling back to SecretsManager.

Channels:
  qa-ux   → TEAMS_WORKFLOW_QA_UX   / Key Vault: qa-teams-webhook-ux
  qa-data → TEAMS_WORKFLOW_QA_DATA / Key Vault: qa-teams-webhook-data
"""

import os
import sys
import json
import logging
import requests
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# Channel → env var + secret name mapping
CHANNEL_CONFIG = {
    "qa-ux": {
        "env_var": "TEAMS_WORKFLOW_QA_UX",
        "secret_name": "qa-teams-webhook-ux",
        "display_name": "QA - UX Compliance",
    },
    "qa-data": {
        "env_var": "TEAMS_WORKFLOW_QA_DATA",
        "secret_name": "qa-teams-webhook-data",
        "display_name": "QA - Data Quality",
    },
}


def _get_webhook_url(channel: str) -> Optional[str]:
    """Resolve webhook URL from env var, then Key Vault fallback."""
    config = CHANNEL_CONFIG.get(channel)
    if not config:
        logger.error(f"Unknown channel: {channel}. Valid: {list(CHANNEL_CONFIG)}")
        return None

    # Try env var first (local dev)
    url = os.getenv(config["env_var"])
    if url:
        return url

    # Fall back to SecretsManager (Key Vault)
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
        from app.core.secrets import SecretsManager

        vault_url = os.getenv("AZURE_KEYVAULT_URL")
        secrets = SecretsManager(vault_url=vault_url)
        url = secrets.get(config["secret_name"])
        if url:
            return url
    except Exception as e:
        logger.warning(f"SecretsManager fallback failed: {e}")

    logger.warning(
        f"No webhook URL found for channel '{channel}'. "
        f"Set {config['env_var']} or store Key Vault secret '{config['secret_name']}'."
    )
    return None


def _post_card(channel: str, card_body: dict) -> bool:
    """POST an Adaptive Card to the given channel webhook."""
    url = _get_webhook_url(channel)
    if not url:
        # Log to console as fallback
        print(f"\n[Teams fallback — {channel}]\n{json.dumps(card_body, indent=2)}\n")
        return False

    payload = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "contentUrl": None,
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    **card_body,
                },
            }
        ],
    }

    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        logger.info(f"Teams notification sent to '{channel}'")
        return True
    except Exception as e:
        logger.error(f"Teams POST failed for '{channel}': {e}")
        return False


def post_finding(
    channel: str,
    ticket_key: str,
    component: str,
    expected: str,
    actual: str,
    severity: str,
    suggested_fix: str,
    agent_type: str,
) -> bool:
    """Post a deviation/discrepancy finding to Teams."""
    severity_colors = {
        "BLOCKER": "attention",
        "MAJOR": "warning",
        "MINOR": "default",
        "COSMETIC": "good",
    }
    color = severity_colors.get(severity, "default")

    card = {
        "body": [
            {
                "type": "TextBlock",
                "text": f"{'🔍' if agent_type == 'qa_ux' else '⚠️'} {'UX Deviation' if agent_type == 'qa_ux' else 'Data Discrepancy'} Found",
                "weight": "Bolder",
                "size": "Medium",
                "color": color,
            },
            {
                "type": "FactSet",
                "facts": [
                    {"title": "Ticket", "value": ticket_key},
                    {"title": "Component / Config", "value": component},
                    {"title": "Severity", "value": severity},
                    {"title": "Expected", "value": expected},
                    {"title": "Actual", "value": actual},
                    {"title": "Suggested Fix", "value": suggested_fix},
                ],
            },
        ],
        "actions": [
            {
                "type": "Action.OpenUrl",
                "title": f"Open {ticket_key}",
                "url": f"https://tmtctech-team.atlassian.net/browse/{ticket_key}",
            }
        ],
    }
    return _post_card(channel, card)


def post_summary(
    channel: str,
    agent_type: str,
    total: int,
    passed: int,
    failed: int,
    skipped: int,
    errors: int,
    details: str = "",
) -> bool:
    """Post a run summary with pass rate to Teams."""
    pass_rate = (passed / total * 100) if total > 0 else 0
    color = "good" if pass_rate >= 95 else ("warning" if pass_rate >= 80 else "attention")
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    card = {
        "body": [
            {
                "type": "TextBlock",
                "text": f"QA Run Summary — {agent_type.upper()}",
                "weight": "Bolder",
                "size": "Medium",
            },
            {
                "type": "TextBlock",
                "text": f"Pass rate: **{pass_rate:.1f}%** ({passed}/{total})",
                "color": color,
            },
            {
                "type": "FactSet",
                "facts": [
                    {"title": "Passed", "value": str(passed)},
                    {"title": "Failed", "value": str(failed)},
                    {"title": "Skipped", "value": str(skipped)},
                    {"title": "Errors", "value": str(errors)},
                    {"title": "Run at", "value": timestamp},
                ],
            },
            *([{"type": "TextBlock", "text": details, "wrap": True}] if details else []),
        ]
    }
    return _post_card(channel, card)


def post_escalation(
    channel: str,
    ticket_key: str,
    question: str,
    context: str,
    options: list[str],
) -> bool:
    """Post a decision-needed escalation to Teams."""
    card = {
        "body": [
            {
                "type": "TextBlock",
                "text": "🚨 Decision Required",
                "weight": "Bolder",
                "size": "Medium",
                "color": "attention",
            },
            {
                "type": "FactSet",
                "facts": [
                    {"title": "Ticket", "value": ticket_key},
                    {"title": "Question", "value": question},
                ],
            },
            {"type": "TextBlock", "text": "Context:", "weight": "Bolder"},
            {"type": "TextBlock", "text": context, "wrap": True},
            {"type": "TextBlock", "text": "Options:", "weight": "Bolder"},
            *[{"type": "TextBlock", "text": f"• {opt}", "wrap": True} for opt in options],
        ],
        "actions": [
            {
                "type": "Action.OpenUrl",
                "title": f"Open {ticket_key}",
                "url": f"https://tmtctech-team.atlassian.net/browse/{ticket_key}",
            }
        ],
    }
    return _post_card(channel, card)


if __name__ == "__main__":
    """Test mode: python teams-notifier.py <channel>"""
    import sys
    from dotenv import load_dotenv

    load_dotenv(
        os.path.join(os.path.dirname(__file__), "..", "..", ".env")
    )

    channel = sys.argv[1] if len(sys.argv) > 1 else "qa-ux"
    print(f"Testing Teams notification to channel: {channel}")

    ok = post_finding(
        channel=channel,
        ticket_key="OTA-TEST",
        component="TestComponent / TEST-config",
        expected="Color #1A73E8",
        actual="Color #000000",
        severity="MINOR",
        suggested_fix="Update token value in tokens.js",
        agent_type="qa_ux" if channel == "qa-ux" else "qa_data",
    )
    print(f"Finding: {'OK' if ok else 'FAILED (check console output above)'}")

    ok = post_summary(
        channel=channel,
        agent_type="qa_ux" if channel == "qa-ux" else "qa_data",
        total=64,
        passed=62,
        failed=2,
        skipped=0,
        errors=0,
        details="2 failures in MSFT configs — see test-results/ for details.",
    )
    print(f"Summary: {'OK' if ok else 'FAILED'}")
