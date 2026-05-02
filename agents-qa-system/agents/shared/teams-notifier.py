"""
Teams Notifier — Power Automate Workflow Webhooks
Posts agent findings to Microsoft Teams channels via Workflow webhook triggers.

IMPORTANT: Microsoft retired O365 Connectors (deadline: April 30, 2026).
This uses the Power Automate "When a Teams webhook request is received"
trigger, which is the current recommended approach.

Setup (per channel):
1. Open Teams → navigate to your channel (e.g., #ota-qa-ux)
2. Click ••• next to the channel name → select "Workflows"
3. Choose "Post to a channel when a webhook request is received"
4. Authenticate with your account
5. Select your Team and Channel → click "Add workflow"
6. Copy the generated webhook URL
7. Store the URL in Key Vault or .env:
     TEAMS_WORKFLOW_QA_UX=https://prod-XX.westus.logic.azure.com/...
     TEAMS_WORKFLOW_QA_DATA=https://prod-XX.westus.logic.azure.com/...
8. Add the workflow URL domain to APPROVED_ENDPOINTS.md

Usage:
    from agents.shared.teams_notifier import post_finding, post_summary

    post_finding(
        channel="qa-ux",
        ticket_key="OTA-289",
        component="ClaudesRead",
        expected="#00C896",
        actual="#4CAF50",
        severity="MAJOR",
    )
"""

import json
import os
import sys
from datetime import datetime, timezone

try:
    import requests
except ImportError:
    print("ERROR: requests library required. Install with: pip install requests")
    sys.exit(1)


CHANNEL_WEBHOOKS = {
    "qa-ux": os.environ.get("TEAMS_WORKFLOW_QA_UX"),
    "qa-data": os.environ.get("TEAMS_WORKFLOW_QA_DATA"),
}


def _post_adaptive_card(webhook_url: str, card: dict) -> bool:
    """Post an Adaptive Card to a Teams channel via Workflow webhook."""
    payload = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "contentUrl": None,
                "content": card,
            }
        ],
    }
    try:
        response = requests.post(
            webhook_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        response.raise_for_status()
        return True
    except requests.RequestException as e:
        print(f"ERROR: Teams webhook failed: {e}")
        return False


def post_finding(
    channel: str,
    ticket_key: str,
    component: str,
    expected: str,
    actual: str,
    severity: str = "MAJOR",
    suggested_fix: str = "",
    agent_type: str = "UX Compliance",
):
    webhook_url = CHANNEL_WEBHOOKS.get(channel)
    if not webhook_url:
        _fallback_log(channel, f"Finding: {ticket_key} / {component} — {severity}")
        return False

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    colors = {"BLOCKER": "attention", "MAJOR": "warning", "MINOR": "default", "COSMETIC": "default"}

    card = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": [
            {
                "type": "TextBlock",
                "text": f"{'🔍' if channel == 'qa-ux' else '⚠️'} {agent_type} — {severity}",
                "weight": "Bolder",
                "size": "Medium",
                "color": colors.get(severity, "default"),
            },
            {
                "type": "FactSet",
                "facts": [
                    {"title": "Ticket", "value": ticket_key},
                    {"title": "Component", "value": component},
                    {"title": "Expected", "value": expected},
                    {"title": "Actual", "value": actual},
                    {"title": "Severity", "value": severity},
                    {"title": "Time", "value": timestamp},
                ],
            },
        ],
    }
    if suggested_fix:
        card["body"].append({
            "type": "TextBlock",
            "text": f"**Suggested fix:** {suggested_fix}",
            "wrap": True,
            "size": "Small",
        })

    success = _post_adaptive_card(webhook_url, card)
    if success:
        print(f"Posted finding to Teams #{channel}: {ticket_key} ({severity})")
    return success


def post_summary(
    channel: str,
    agent_type: str,
    total: int,
    passed: int,
    failed: int,
    skipped: int = 0,
    errors: int = 0,
    details: str = "",
):
    webhook_url = CHANNEL_WEBHOOKS.get(channel)
    if not webhook_url:
        _fallback_log(channel, f"Summary: {agent_type} — {passed}/{total} passed")
        return False

    pass_rate = passed / total if total > 0 else 0
    emoji = "✅" if failed == 0 else "⚠️"
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    card = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": [
            {
                "type": "TextBlock",
                "text": f"{emoji} {agent_type} run complete",
                "weight": "Bolder",
                "size": "Medium",
                "color": "good" if failed == 0 else "warning",
            },
            {
                "type": "ColumnSet",
                "columns": [
                    {
                        "type": "Column",
                        "width": "auto",
                        "items": [{"type": "TextBlock", "text": f"**{pass_rate:.0%}**", "size": "ExtraLarge"}],
                    },
                    {
                        "type": "Column",
                        "width": "stretch",
                        "items": [{
                            "type": "FactSet",
                            "facts": [
                                {"title": "Passed", "value": str(passed)},
                                {"title": "Failed", "value": str(failed)},
                                {"title": "Skipped", "value": str(skipped)},
                                {"title": "Errors", "value": str(errors)},
                            ],
                        }],
                    },
                ],
            },
            {"type": "TextBlock", "text": timestamp, "size": "Small", "isSubtle": True},
        ],
    }
    if details:
        card["body"].append({"type": "TextBlock", "text": details, "wrap": True, "size": "Small"})

    success = _post_adaptive_card(webhook_url, card)
    if success:
        print(f"Posted summary to Teams #{channel}: {agent_type} ({pass_rate:.0%})")
    return success


def post_escalation(
    channel: str,
    ticket_key: str,
    question: str,
    context: str,
    options: list = None,
):
    webhook_url = CHANNEL_WEBHOOKS.get(channel)
    if not webhook_url:
        _fallback_log(channel, f"Escalation: {ticket_key} — {question}")
        return False

    if options is None:
        options = ["APPROVE_FIX", "INVESTIGATE", "DEFER"]

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    card = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": [
            {"type": "TextBlock", "text": f"🛑 Decision needed — {ticket_key}", "weight": "Bolder", "size": "Medium", "color": "attention"},
            {"type": "TextBlock", "text": question, "wrap": True, "weight": "Bolder"},
            {"type": "TextBlock", "text": context, "wrap": True, "size": "Small"},
            {"type": "TextBlock", "text": f"Reply with: {' | '.join(options)}", "size": "Small", "isSubtle": True},
            {"type": "TextBlock", "text": timestamp, "size": "Small", "isSubtle": True},
        ],
    }

    success = _post_adaptive_card(webhook_url, card)
    if success:
        print(f"Posted escalation to Teams #{channel}: {ticket_key}")
    return success


def _fallback_log(channel: str, message: str):
    print(f"[Teams #{channel} — NOT CONFIGURED] {message}")
    print(f"  Set TEAMS_WORKFLOW_{channel.upper().replace('-', '_')} in .env or Key Vault")
    print(f"  See setup instructions in this file's docstring")


if __name__ == "__main__":
    channel = sys.argv[1] if len(sys.argv) > 1 else "qa-ux"
    post_finding(
        channel=channel,
        ticket_key="OTA-TEST",
        component="TestComponent",
        expected="test value A",
        actual="test value B",
        severity="COSMETIC",
        suggested_fix="This is a test notification from the QA agent system",
    )
