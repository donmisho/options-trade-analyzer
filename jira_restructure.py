"""
jira_restructure.py -- OTA Jira Project Restructure Script
==========================================================
Phases:
  0 -- Auth setup (fetch token from Key Vault, verify /myself)
  1 -- Create cross-project Polaris work item links
  2 -- Convert active OTA Subtasks to Stories
  3 -- Rename Epics (drop legacy phase prefixes)
  4 -- Append "Roadmap Category" link to Epic descriptions
  5 -- Investigate duplicate Epics (read-only report)

Description format for Phase 4: Uses Jira REST API v2 (wiki markup) for
descriptions, which is simpler than constructing ADF JSON for v3.

Run: python jira_restructure.py [--phase 0|1|2|3|4|5|all]
     Defaults to --phase 0 (auth check only).

Rate limiting: 100ms sleep between API calls (Atlassian Standard tier = 100 req/min).
"""

import argparse
import json
import os
import subprocess
import sys
import time

import requests

# ── Constants ────────────────────────────────────────────────────────────────
JIRA_BASE_V3 = "https://tmtctech-team.atlassian.net/rest/api/3"
JIRA_BASE_V2 = "https://tmtctech-team.atlassian.net/rest/api/2"
JIRA_BROWSE  = "https://tmtctech-team.atlassian.net/browse"
KV_VAULT     = "options-analyzer"
KV_TOKEN_SECRET = "jira-api-token"
RATE_SLEEP   = 0.1   # seconds between calls

# ── Auth helpers ─────────────────────────────────────────────────────────────

def fetch_token_from_kv() -> str:
    """Fetch the Jira API token from Azure Key Vault."""
    cmd = (f"az keyvault secret show --vault-name {KV_VAULT} "
           f"--name {KV_TOKEN_SECRET} --query value -o tsv")
    result = subprocess.run(
        cmd, capture_output=True, text=True, check=True, shell=True
    )
    return result.stdout.strip()


def get_email() -> str:
    """Return the Atlassian email from env or prompt once."""
    email = os.environ.get("JIRA_EMAIL", "")
    if not email:
        email = input("Enter your Atlassian account email: ").strip()
        os.environ["JIRA_EMAIL"] = email
    return email


def build_session(email: str, token: str) -> requests.Session:
    sess = requests.Session()
    sess.auth = (email, token)
    sess.headers.update({"Accept": "application/json", "Content-Type": "application/json"})
    return sess


def check_response(resp: requests.Response, context: str = "") -> None:
    """Abort with full error body if the response is not 2xx."""
    if not resp.ok:
        print(f"\n[ERROR] {context}")
        print(f"  Status: {resp.status_code}")
        try:
            print(f"  Body:   {json.dumps(resp.json(), indent=2)}")
        except Exception:
            print(f"  Body:   {resp.text}")
        sys.exit(1)

# ── Phase 0 ──────────────────────────────────────────────────────────────────

def phase0() -> tuple[requests.Session, str, str]:
    """Auth setup. Returns (session, email, accountId)."""
    print("=== Phase 0: Auth Setup ===")
    print(f"Fetching Jira API token from Key Vault '{KV_VAULT}' / secret '{KV_TOKEN_SECRET}' ...")
    token = fetch_token_from_kv()
    print("  Token fetched OK.")

    email = get_email()
    sess  = build_session(email, token)

    print(f"Verifying auth via GET /myself ...")
    resp = sess.get(f"{JIRA_BASE_V3}/myself")
    check_response(resp, "GET /myself")
    me = resp.json()
    account_id = me["accountId"]
    display    = me.get("displayName", "")
    print(f"  Auth OK -- accountId: {account_id}  ({display})")
    print("\nPhase 0 complete. Confirm before proceeding to Phase 1.\n")
    return sess, email, account_id

# ── Phase 1 ──────────────────────────────────────────────────────────────────

PHASE1_PAIRS = [
    # (idea_key, epic_key, already_exists)
    ("OTAR-7",  "OTA-501", True),
    ("OTAR-7",  "OTA-4",   True),
    ("OTAR-7",  "OTA-6",   True),
    ("OTAR-7",  "OTA-14",  True),
    ("OTAR-7",  "OTA-272", True),
    ("OTAR-7",  "OTA-273", False),
    ("OTAR-7",  "OTA-436", False),
    ("OTAR-8",  "OTA-329", False),
    ("OTAR-8",  "OTA-376", False),
    ("OTAR-8",  "OTA-393", False),
    ("OTAR-9",  "OTA-365", False),
    ("OTAR-10", "OTA-7",   False),
    ("OTAR-11", "OTA-5",   False),
    ("OTAR-11", "OTA-300", False),
    ("OTAR-11", "OTA-443", False),
    ("OTAR-14", "OTA-10",  False),
    ("OTAR-16", "OTA-11",  False),
    ("OTAR-17", "OTA-455", False),
    ("OTAR-19", "OTA-13",  False),
    ("OTAR-19", "OTA-208", False),
    ("OTAR-19", "OTA-312", False),
    ("OTAR-21", "OTA-12",  False),
    ("OTAR-21", "OTA-14",  False),
    ("OTAR-23", "OTA-8",   False),
    ("OTAR-23", "OTA-329", False),
    ("OTAR-23", "OTA-356", False),
    ("OTAR-23", "OTA-365", False),
    ("OTAR-23", "OTA-376", False),
    ("OTAR-23", "OTA-393", False),
    ("OTAR-24", "OTA-9",   False),
    ("OTAR-24", "OTA-236", False),
    ("OTAR-24", "OTA-476", False),
    ("OTAR-24", "OTA-477", False),
    ("OTAR-24", "OTA-498", False),
]


def has_polaris_link(sess: requests.Session, epic_key: str, idea_key: str) -> bool:
    """Return True if a Polaris work item link to idea_key already exists on epic_key."""
    resp = sess.get(f"{JIRA_BASE_V3}/issue/{epic_key}",
                    params={"fields": "issuelinks"})
    check_response(resp, f"GET {epic_key} issuelinks")
    links = resp.json().get("fields", {}).get("issuelinks", [])
    for lnk in links:
        lt = lnk.get("type", {}).get("name", "")
        if "polaris" in lt.lower():
            for direction in ("inwardIssue", "outwardIssue"):
                if lnk.get(direction, {}).get("key") == idea_key:
                    return True
    return False


def phase1(sess: requests.Session) -> None:
    print("=== Phase 1: Create Cross-Project Polaris Links ===")
    created = 0
    skipped = 0
    errors  = []

    for idea_key, epic_key, pre_exists in PHASE1_PAIRS:
        time.sleep(RATE_SLEEP)
        if pre_exists:
            print(f"  SKIP (pre-known)  {idea_key} -> {epic_key}")
            skipped += 1
            continue

        # Idempotency check
        if has_polaris_link(sess, epic_key, idea_key):
            print(f"  SKIP (exists)     {idea_key} -> {epic_key}")
            skipped += 1
            continue

        payload = {
            "type": {"name": "Polaris work item link"},
            "inwardIssue":  {"key": idea_key},
            "outwardIssue": {"key": epic_key},
        }
        print(f"  POST /issueLink  {idea_key} -> {epic_key}  payload: {json.dumps(payload)}")
        resp = sess.post(f"{JIRA_BASE_V3}/issueLink", json=payload)
        time.sleep(RATE_SLEEP)

        if resp.status_code in (200, 201):
            print(f"    [OK] Created")
            created += 1
        else:
            msg = f"{idea_key}->{epic_key}: HTTP {resp.status_code} -- {resp.text[:200]}"
            print(f"    [ERR] ERROR: {msg}")
            errors.append(msg)

    print(f"\nPhase 1 complete: {created} created, {skipped} skipped, {len(errors)} errors.")
    if errors:
        print("Errors:")
        for e in errors:
            print(f"  - {e}")
    print()

# ── Phase 2 ──────────────────────────────────────────────────────────────────

DONE_STATUSES = {"Code & Test Complete", "Production Deployed", "Done"}


def fetch_active_subtasks(sess: requests.Session) -> list[dict]:
    jql = ('project = OTA AND issuetype = Subtask '
           'AND status NOT IN ("Code & Test Complete", "Production Deployed", "Done")')
    results, start = [], 0
    while True:
        resp = sess.get(f"{JIRA_BASE_V3}/search/jql",
                        params={"jql": jql, "startAt": start, "maxResults": 100,
                                "fields": "summary,status,parent,issuetype"})
        check_response(resp, "JQL subtask search")
        data   = resp.json()
        issues = data.get("issues", [])
        results.extend(issues)
        start += len(issues)
        if start >= data.get("total", 0):
            break
        time.sleep(RATE_SLEEP)
    return results


def phase2(sess: requests.Session) -> None:
    print("=== Phase 2: Convert Active Subtasks to Stories ===")
    subtasks = fetch_active_subtasks(sess)

    if not subtasks:
        print("  No active Subtasks found. Phase 2 skipped.\n")
        return

    print(f"\nFound {len(subtasks)} active Subtask(s):\n")
    print(f"  {'Key':<12} {'Parent':<12} {'Status':<25} Summary")
    print(f"  {'-'*12} {'-'*12} {'-'*25} {'-'*50}")
    for iss in subtasks:
        key    = iss["key"]
        parent = iss["fields"].get("parent", {}).get("key", "(none)")
        status = iss["fields"]["status"]["name"]
        summ   = iss["fields"]["summary"][:60]
        print(f"  {key:<12} {parent:<12} {status:<25} {summ}")

    print()
    confirm = input("Convert ALL of the above Subtasks to Stories? (yes/no): ").strip().lower()
    if confirm != "yes":
        print("Phase 2 aborted by user.\n")
        return

    converted = 0
    errors    = []

    for iss in subtasks:
        key         = iss["key"]
        orig_parent = iss["fields"].get("parent", {}).get("key")
        time.sleep(RATE_SLEEP)

        payload = {"fields": {"issuetype": {"id": "10214"}}}  # Story in OTA project
        print(f"  PUT /issue/{key}  {json.dumps(payload)}")
        resp = sess.put(f"{JIRA_BASE_V3}/issue/{key}", json=payload)
        time.sleep(RATE_SLEEP)

        if not resp.ok:
            msg = f"{key}: HTTP {resp.status_code} -- {resp.text[:200]}"
            print(f"    [ERR] ERROR: {msg}")
            errors.append(msg)
            continue

        # Verify conversion
        v = sess.get(f"{JIRA_BASE_V3}/issue/{key}", params={"fields": "issuetype,parent"})
        check_response(v, f"verify {key}")
        vdata       = v.json()["fields"]
        new_type    = vdata["issuetype"]["name"]
        new_parent  = vdata.get("parent", {}).get("key")

        if new_type != "Story":
            errors.append(f"{key}: issuetype is still '{new_type}' after PUT")
            print(f"    [ERR] Type not updated: {new_type}")
            continue

        # Restore parent if lost
        if orig_parent and new_parent != orig_parent:
            print(f"    Parent drift detected ({new_parent} != {orig_parent}), restoring ...")
            fix = sess.put(f"{JIRA_BASE_V3}/issue/{key}",
                           json={"fields": {"parent": {"key": orig_parent}}})
            time.sleep(RATE_SLEEP)
            if not fix.ok:
                errors.append(f"{key}: failed to restore parent {orig_parent}: {fix.status_code}")
                print(f"    [ERR] Parent restore failed: {fix.status_code}")
            else:
                print(f"    [OK] Parent restored to {orig_parent}")

        print(f"    [OK] {key} -> Story  (parent: {new_parent or orig_parent})")
        converted += 1

    print(f"\nPhase 2 complete: {converted} converted, {len(errors)} errors.")
    if errors:
        print("Errors:")
        for e in errors:
            print(f"  - {e}")
    print()

# ── Phase 3 ──────────────────────────────────────────────────────────────────

PHASE3_RENAMES = [
    ("OTA-4",   "2.0.x Pre-Flight Fixes + Scoring Pipeline",
                "Pre-Flight Fixes & Scoring Pipeline"),
    ("OTA-5",   "2.1.x Security Strategies Page",
                "Security Strategies Page"),
    ("OTA-6",   "Structured Evaluation + Probability Matrix (Phase 2.11)",
                "Structured Evaluation & Probability Matrix"),
    ("OTA-7",   "2.2.x Positions & Portfolio",
                "Positions & Portfolio"),
    ("OTA-8",   "2.3.x Dashboard Overhaul",
                "Dashboard Overhaul"),
    ("OTA-9",   "2.4.x Infrastructure & Strategy Admin",
                "Infrastructure & Strategy Admin"),
    ("OTA-10",  "2.5.x Live Trading Preparation",
                "Live Trading Preparation"),
    ("OTA-11",  "3.x.x Agentic Platform",
                "Agentic Platform"),
    ("OTA-12",  "3.3.x Backtesting Engine",
                "Backtesting Engine"),
    ("OTA-13",  "4.x.x Intelligence Expansion",
                "Intelligence Expansion"),
    ("OTA-356", "Experience Framework v3 Sprint 2 \u2014 Strategy Pages + Positions Page v3 Redesign",
                "Experience Framework v3 \u2014 Strategy Pages & Positions (initial scope)"),
    ("OTA-365", "Experience Framework v3 Sprint 3 \u2014 Strategy Pages + Positions v3 Redesign",
                "Experience Framework v3 \u2014 Strategy Pages & Positions Page"),
    ("OTA-376", "Sprint 4 Experience Framework v3: Trade Wiring & Data Integration",
                "Experience Framework v3 -- Trade Wiring & Data Integration"),
    ("OTA-393", "Sprint 5 Experience Framework v3: Integration, Polish & Cleanup",
                "Experience Framework v3 -- Integration, Polish & Cleanup"),
]


def phase3(sess: requests.Session) -> None:
    print("=== Phase 3: Rename Epics ===")
    renamed  = 0
    skipped  = 0
    errors   = []

    for key, old_summary, new_summary in PHASE3_RENAMES:
        time.sleep(RATE_SLEEP)
        resp = sess.get(f"{JIRA_BASE_V3}/issue/{key}", params={"fields": "summary"})
        check_response(resp, f"GET {key} summary")
        current = resp.json()["fields"]["summary"]

        if current != old_summary:
            print(f"  SKIP {key}: current summary does not match old pattern")
            print(f"         current: {current!r}")
            print(f"         old:     {old_summary!r}")
            skipped += 1
            continue

        payload = {"fields": {"summary": new_summary}}
        print(f"  PUT /issue/{key}  summary -> {new_summary!r}")
        r = sess.put(f"{JIRA_BASE_V3}/issue/{key}", json=payload)
        time.sleep(RATE_SLEEP)

        if r.ok:
            print(f"    [OK] Renamed")
            renamed += 1
        else:
            msg = f"{key}: HTTP {r.status_code} -- {r.text[:200]}"
            print(f"    [ERR] ERROR: {msg}")
            errors.append(msg)

    print(f"\nPhase 3 complete: {renamed} renamed, {skipped} skipped, {len(errors)} errors.")
    if errors:
        print("Errors:")
        for e in errors:
            print(f"  - {e}")
    print()

# ── Phase 4 ──────────────────────────────────────────────────────────────────

# Maps epic_key -> list of (otar_key, label)
PHASE4_MAPPING: dict[str, list[tuple[str, str]]] = {
    "OTA-4":   [("OTAR-7",  "Trade Evaluation Quality")],
    "OTA-5":   [("OTAR-11", "Trade Discovery & Scanning")],
    "OTA-6":   [("OTAR-7",  "Trade Evaluation Quality")],
    "OTA-7":   [("OTAR-10", "Position Management & Monitoring")],
    "OTA-8":   [("OTAR-23", "UX Foundation & Design System")],
    "OTA-9":   [("OTAR-24", "Platform Operations & Observability")],
    "OTA-10":  [("OTAR-14", "Live Trade Execution")],
    "OTA-11":  [("OTAR-16", "Insights & Agentic Platform")],
    "OTA-12":  [("OTAR-21", "Backtesting & Strategy Validation")],
    "OTA-13":  [("OTAR-19", "Data Sources & Market Intelligence")],
    "OTA-14":  [("OTAR-7",  "Trade Evaluation Quality"),
                ("OTAR-21", "Backtesting & Strategy Validation")],
    "OTA-208": [("OTAR-19", "Data Sources & Market Intelligence")],
    "OTA-236": [("OTAR-24", "Platform Operations & Observability")],
    "OTA-272": [("OTAR-7",  "Trade Evaluation Quality")],
    "OTA-273": [("OTAR-7",  "Trade Evaluation Quality")],
    "OTA-300": [("OTAR-11", "Trade Discovery & Scanning")],
    "OTA-312": [("OTAR-19", "Data Sources & Market Intelligence")],
    "OTA-329": [("OTAR-23", "UX Foundation & Design System"),
                ("OTAR-8",  "Trade-to-Strategy Journey")],
    "OTA-356": [("OTAR-23", "UX Foundation & Design System")],
    "OTA-365": [("OTAR-23", "UX Foundation & Design System"),
                ("OTAR-9",  "Strategy-to-Trade Journey")],
    "OTA-376": [("OTAR-23", "UX Foundation & Design System"),
                ("OTAR-8",  "Trade-to-Strategy Journey")],
    "OTA-393": [("OTAR-23", "UX Foundation & Design System"),
                ("OTAR-8",  "Trade-to-Strategy Journey")],
    "OTA-436": [("OTAR-7",  "Trade Evaluation Quality")],
    "OTA-455": [("OTAR-17", "Identity & Access")],
    "OTA-476": [("OTAR-24", "Platform Operations & Observability")],
    "OTA-477": [("OTAR-24", "Platform Operations & Observability")],
    "OTA-498": [("OTAR-24", "Platform Operations & Observability")],
    "OTA-501": [("OTAR-7",  "Trade Evaluation Quality")],
    "OTA-443": [("OTAR-11", "Trade Discovery & Scanning")],
}

# ── ADF helpers ──────────────────────────────────────────────────────────────

def adf_text(text: str) -> dict:
    return {"type": "text", "text": text}


def adf_link_mark(href: str) -> dict:
    return {"type": "link", "attrs": {"href": href}}


def adf_paragraph(content: list) -> dict:
    return {"type": "paragraph", "content": content}


def adf_rule() -> dict:
    return {"type": "rule"}


def build_roadmap_adf_nodes(categories: list[tuple[str, str]]) -> list[dict]:
    """Return a list of ADF nodes to append: a rule, then one paragraph per category."""
    nodes = [adf_rule()]
    label_node = adf_paragraph([
        adf_text("Roadmap Category: ") if len(categories) == 1
        else adf_text("Roadmap Categories: ")
    ])
    nodes.append(label_node)
    for otar_key, cat_name in categories:
        url   = f"{JIRA_BROWSE}/{otar_key}"
        label = f"{otar_key} -- {cat_name}"
        para  = adf_paragraph([
            {"type": "text", "text": label,
             "marks": [adf_link_mark(url)]}
        ])
        nodes.append(para)
    return nodes


def desc_has_roadmap_category(description: dict | None) -> bool:
    """Walk ADF content looking for 'Roadmap Category' text."""
    if not description:
        return False
    raw = json.dumps(description)
    return "Roadmap Category" in raw


def phase4(sess: requests.Session) -> None:
    print("=== Phase 4: Append Roadmap Category to Epic Descriptions ===")
    updated = 0
    skipped = 0
    errors  = []

    for epic_key, categories in PHASE4_MAPPING.items():
        time.sleep(RATE_SLEEP)
        resp = sess.get(f"{JIRA_BASE_V3}/issue/{epic_key}",
                        params={"fields": "description"})
        check_response(resp, f"GET {epic_key} description")
        current_desc = resp.json()["fields"].get("description")

        if desc_has_roadmap_category(current_desc):
            print(f"  SKIP {epic_key}: description already contains 'Roadmap Category'")
            skipped += 1
            continue

        # Build new ADF doc
        existing_content = []
        if current_desc and current_desc.get("content"):
            existing_content = current_desc["content"]

        new_content = existing_content + build_roadmap_adf_nodes(categories)
        new_desc = {
            "type": "doc",
            "version": 1,
            "content": new_content
        }

        payload = {"fields": {"description": new_desc}}
        cat_display = ", ".join(f"{k} {n}" for k, n in categories)
        print(f"  PUT /issue/{epic_key}  append roadmap category: {cat_display}")
        r = sess.put(f"{JIRA_BASE_V3}/issue/{epic_key}", json=payload)
        time.sleep(RATE_SLEEP)

        if r.ok:
            print(f"    [OK] Updated")
            updated += 1
        else:
            msg = f"{epic_key}: HTTP {r.status_code} -- {r.text[:200]}"
            print(f"    [ERR] ERROR: {msg}")
            errors.append(msg)

    print(f"\nPhase 4 complete: {updated} updated, {skipped} skipped, {len(errors)} errors.")
    if errors:
        print("Errors:")
        for e in errors:
            print(f"  - {e}")
    print()

# ── Phase 5 ──────────────────────────────────────────────────────────────────

def count_children(sess: requests.Session, key: str) -> tuple[int, int]:
    """Return (total_children, active_children) for an issue."""
    jql_all    = f"parent = {key}"
    jql_active = (f'parent = {key} AND status NOT IN '
                  f'("Code & Test Complete", "Production Deployed", "Done")')

    def jql_count(jql: str) -> int:
        r = sess.get(f"{JIRA_BASE_V3}/search/jql",
                     params={"jql": jql, "maxResults": 0, "fields": "summary"})
        if not r.ok:
            return -1
        return r.json().get("total", 0)

    total  = jql_count(jql_all)
    time.sleep(RATE_SLEEP)
    active = jql_count(jql_active)
    return total, active


def fetch_issue_summary(sess: requests.Session, key: str) -> dict:
    resp = sess.get(f"{JIRA_BASE_V3}/issue/{key}",
                    params={"fields": "summary,status,description,created"})
    check_response(resp, f"GET {key}")
    f = resp.json()["fields"]
    desc_raw = f.get("description") or {}
    desc_text = json.dumps(desc_raw)[:500]
    return {
        "key":     key,
        "summary": f.get("summary", ""),
        "status":  f["status"]["name"],
        "created": f.get("created", "")[:10],
        "desc":    desc_text,
    }


def phase5(sess: requests.Session) -> None:
    print("=== Phase 5: Investigate Duplicate Epics (READ-ONLY) ===\n")

    pairs = [("OTA-356", "OTA-365"), ("OTA-476", "OTA-477")]

    for a_key, b_key in pairs:
        print(f"--- {a_key} vs {b_key} ---")
        time.sleep(RATE_SLEEP)
        a = fetch_issue_summary(sess, a_key)
        time.sleep(RATE_SLEEP)
        b = fetch_issue_summary(sess, b_key)
        time.sleep(RATE_SLEEP)
        a_tot, a_act = count_children(sess, a_key)
        time.sleep(RATE_SLEEP)
        b_tot, b_act = count_children(sess, b_key)

        w = 30
        print(f"  {'Field':<20} {a_key:<40} {b_key}")
        print(f"  {'-'*20} {'-'*40} {'-'*40}")
        print(f"  {'Summary':<20} {a['summary'][:38]:<40} {b['summary'][:38]}")
        print(f"  {'Status':<20} {a['status']:<40} {b['status']}")
        print(f"  {'Created':<20} {a['created']:<40} {b['created']}")
        print(f"  {'Children (total)':<20} {str(a_tot):<40} {str(b_tot)}")
        print(f"  {'Children (active)':<20} {str(a_act):<40} {str(b_act)}")
        print()
        print(f"  {a_key} description (first 500 chars of ADF JSON):")
        print(f"    {a['desc'][:500]}")
        print()
        print(f"  {b_key} description (first 500 chars of ADF JSON):")
        print(f"    {b['desc'][:500]}")
        print()

    print("Phase 5 complete. No changes made.\n")

# ── Entry point ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="OTA Jira restructure script")
    parser.add_argument(
        "--phase",
        default="0",
        choices=["0", "1", "2", "3", "4", "5", "all"],
        help="Which phase to run (default: 0 -- auth check only)"
    )
    args = parser.parse_args()

    sess, email, account_id = phase0()

    if args.phase == "0":
        print("(Run with --phase 1|2|3|4|5|all to continue)")
        return

    phases_to_run = (["1", "2", "3", "4", "5"]
                     if args.phase == "all"
                     else [args.phase])

    if "1" in phases_to_run:
        phase1(sess)
    if "2" in phases_to_run:
        phase2(sess)
    if "3" in phases_to_run:
        phase3(sess)
    if "4" in phases_to_run:
        phase4(sess)
    if "5" in phases_to_run:
        phase5(sess)

    print("=== Summary ===")
    print("Run complete. See per-phase output above for counts.")


if __name__ == "__main__":
    main()
