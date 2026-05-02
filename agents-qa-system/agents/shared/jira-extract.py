"""
Jira Extract Script
Pulls active OTA tickets for QA agent consumption.

Usage:
    python agents/shared/jira-extract.py

Requires:
    JIRA_API_TOKEN — in .env locally or Key Vault in prod
    JIRA_USER_EMAIL — the Atlassian account email

Endpoint:
    https://tmtctech-team.atlassian.net
    (must be in APPROVED_ENDPOINTS.md)

Output:
    agents/qa-context/jira-extract.json
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: requests library required. Install with: pip install requests")
    sys.exit(1)


# ─── CONFIGURATION ──────────────────────────────────────────
JIRA_BASE_URL = "https://tmtctech-team.atlassian.net"
JIRA_PROJECT_KEY = "OTA"
OUTPUT_PATH = Path(__file__).parent.parent / "qa-context" / "jira-extract.json"

# Load credentials from environment
JIRA_USER_EMAIL = os.environ.get("JIRA_USER_EMAIL")
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN")


def fetch_issues():
    """Fetch all Features and Subtasks where status != Done."""
    if not JIRA_USER_EMAIL or not JIRA_API_TOKEN:
        print("ERROR: Set JIRA_USER_EMAIL and JIRA_API_TOKEN environment variables")
        sys.exit(1)

    auth = (JIRA_USER_EMAIL, JIRA_API_TOKEN)
    headers = {"Accept": "application/json"}

    # JQL: all Features and Subtasks that aren't Done
    jql = (
        f'project = {JIRA_PROJECT_KEY} '
        f'AND issuetype in (Feature, Subtask, Epic) '
        f'AND status != Done '
        f'ORDER BY key ASC'
    )

    all_issues = []
    start_at = 0
    max_results = 50

    while True:
        url = f"{JIRA_BASE_URL}/rest/api/3/search"
        params = {
            "jql": jql,
            "startAt": start_at,
            "maxResults": max_results,
            "fields": "summary,description,status,issuetype,labels,parent",
        }

        response = requests.get(url, headers=headers, auth=auth, params=params)
        response.raise_for_status()
        data = response.json()

        issues = data.get("issues", [])
        if not issues:
            break

        for issue in issues:
            fields = issue["fields"]

            # Extract description text — Jira v3 uses ADF format
            description = ""
            desc_field = fields.get("description")
            if desc_field:
                if isinstance(desc_field, str):
                    description = desc_field
                elif isinstance(desc_field, dict):
                    # ADF format — extract text content recursively
                    description = _extract_adf_text(desc_field)

            parent_key = None
            parent = fields.get("parent")
            if parent:
                parent_key = parent.get("key")

            all_issues.append({
                "key": issue["key"],
                "summary": fields.get("summary", ""),
                "description": description,
                "status": fields.get("status", {}).get("name", ""),
                "type": fields.get("issuetype", {}).get("name", ""),
                "parent_key": parent_key,
                "labels": fields.get("labels", []),
            })

        start_at += len(issues)
        if start_at >= data.get("total", 0):
            break

    return all_issues


def _extract_adf_text(node):
    """Recursively extract text from Atlassian Document Format."""
    if isinstance(node, str):
        return node

    text_parts = []

    if isinstance(node, dict):
        if node.get("type") == "text":
            text_parts.append(node.get("text", ""))
        if node.get("type") == "hardBreak":
            text_parts.append("\n")
        for child in node.get("content", []):
            text_parts.append(_extract_adf_text(child))

    elif isinstance(node, list):
        for item in node:
            text_parts.append(_extract_adf_text(item))

    return " ".join(filter(None, text_parts))


def main():
    print(f"Fetching active {JIRA_PROJECT_KEY} tickets from {JIRA_BASE_URL}...")
    issues = fetch_issues()

    # Ensure output directory exists
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    extract = {
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "project": JIRA_PROJECT_KEY,
        "source": JIRA_BASE_URL,
        "filter": "status != Done, types: Feature/Subtask/Epic",
        "count": len(issues),
        "issues": issues,
    }

    with open(OUTPUT_PATH, "w") as f:
        json.dump(extract, f, indent=2, ensure_ascii=False)

    print(f"Extracted {len(issues)} issues to {OUTPUT_PATH}")

    # Summary by type and status
    from collections import Counter
    type_counts = Counter(i["type"] for i in issues)
    status_counts = Counter(i["status"] for i in issues)
    print(f"  By type: {dict(type_counts)}")
    print(f"  By status: {dict(status_counts)}")


if __name__ == "__main__":
    main()
