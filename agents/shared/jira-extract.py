"""
Jira extractor for QA agent system.

Pulls active OTA tickets and writes agents/qa-context/jira-extract.json.

Credentials (in priority order):
  1. JIRA_API_TOKEN env var (or Key Vault: jira-api-token)
  2. JIRA_USER_EMAIL env var (from .env)
"""

import os
import sys
import json
import base64
import logging
import requests
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

JIRA_BASE_URL = "https://tmtctech-team.atlassian.net"
JQL = 'project = OTA AND issuetype in (Feature, Subtask, Epic) AND status not in ("Done") ORDER BY key ASC'
OUTPUT_PATH = Path(__file__).parent.parent / "qa-context" / "jira-extract.json"


def _get_credentials() -> tuple[str, str]:
    """Resolve Jira email and API token."""
    email = os.getenv("JIRA_USER_EMAIL")
    token = os.getenv("JIRA_API_TOKEN")

    if not token:
        # Fall back to SecretsManager (Key Vault)
        try:
            sys.path.insert(0, str(Path(__file__).parent.parent.parent))
            from app.core.secrets import SecretsManager

            vault_url = os.getenv("AZURE_KEYVAULT_URL")
            secrets = SecretsManager(vault_url=vault_url)
            token = secrets.get("jira-api-token")
        except Exception as e:
            logger.warning(f"SecretsManager fallback failed: {e}")

    if not email:
        raise ValueError("JIRA_USER_EMAIL not set in environment")
    if not token:
        raise ValueError(
            "Jira API token not found. Set JIRA_API_TOKEN env var or "
            "store 'jira-api-token' in Key Vault."
        )

    return email, token


def _auth_header(email: str, token: str) -> dict:
    creds = base64.b64encode(f"{email}:{token}".encode()).decode()
    return {
        "Authorization": f"Basic {creds}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _extract_adf_text(content) -> str:
    """Recursively extract plain text from Atlassian Document Format nodes."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        if content.get("type") == "text":
            return content.get("text", "")
        parts = []
        for child in content.get("content", []):
            parts.append(_extract_adf_text(child))
        separator = "\n" if content.get("type") in ("paragraph", "heading", "bulletList", "orderedList", "listItem") else ""
        return separator.join(filter(None, parts))
    if isinstance(content, list):
        return "\n".join(filter(None, [_extract_adf_text(item) for item in content]))
    return ""


def _fetch_issues(headers: dict) -> list[dict]:
    """Fetch all matching issues with cursor-based pagination."""
    issues = []
    next_page_token = None

    while True:
        body = {
            "jql": JQL,
            "maxResults": 50,
            "fields": ["summary", "description", "status", "issuetype", "parent", "labels"],
        }
        if next_page_token:
            body["nextPageToken"] = next_page_token

        resp = requests.post(
            f"{JIRA_BASE_URL}/rest/api/3/search/jql",
            headers=headers,
            json=body,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        for issue in data.get("issues", []):
            fields = issue.get("fields", {})
            description_raw = fields.get("description")
            description_text = _extract_adf_text(description_raw) if description_raw else ""

            parent = fields.get("parent", {})
            issues.append({
                "key": issue["key"],
                "summary": fields.get("summary", ""),
                "description": description_text,
                "status": fields.get("status", {}).get("name", ""),
                "type": fields.get("issuetype", {}).get("name", ""),
                "parent_key": parent.get("key") if parent else None,
                "labels": fields.get("labels", []),
            })

        if data.get("isLast", True):
            break
        next_page_token = data.get("nextPageToken")
        if not next_page_token:
            break

    return issues


def main():
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent.parent / ".env")

    email, token = _get_credentials()
    headers = _auth_header(email, token)

    logger.info(f"Fetching OTA tickets from {JIRA_BASE_URL}...")
    issues = _fetch_issues(headers)

    # Count by type and status
    by_type: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for issue in issues:
        by_type[issue["type"]] = by_type.get(issue["type"], 0) + 1
        by_status[issue["status"]] = by_status.get(issue["status"], 0) + 1

    output = {
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "project": "OTA",
        "source": JIRA_BASE_URL,
        "filter": JQL,
        "count": len(issues),
        "issues": issues,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nExtracted {len(issues)} issues -> {OUTPUT_PATH}")
    print("\nBy type:")
    for t, count in sorted(by_type.items()):
        print(f"  {t}: {count}")
    print("\nBy status:")
    for s, count in sorted(by_status.items()):
        print(f"  {s}: {count}")


if __name__ == "__main__":
    main()
