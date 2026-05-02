"""
build-diagram-with-icons.py
Finds Azure SVG icons, embeds them as base64, and writes architecture-diagram.drawio

Run from the project root:
    python build-diagram-with-icons.py
"""

import base64
import os
import sys

ICON_PACK_ROOT = r"C:\Users\DonMishory\OneDrive - jmholistic.com\Microsoft Content\Architecture Diagrams and Icons"
OUTPUT_FILE = "architecture-diagram.drawio"


def find_icon(root, search_terms):
    """Recursively find first SVG matching any search term."""
    for dirpath, _, filenames in os.walk(root):
        for fname in filenames:
            if not fname.lower().endswith(".svg"):
                continue
            name_lower = fname.lower()
            for term in search_terms:
                if term.lower() in name_lower:
                    return os.path.join(dirpath, fname)
    return None


def get_uri(path, label):
    """Read SVG file and return base64 data URI."""
    if path and os.path.exists(path):
        print(f"  [OK ] {label}: {os.path.basename(path)}")
        with open(path, "rb") as f:
            data = f.read()
    else:
        print(f"  [???] {label}: NOT FOUND — using placeholder")
        data = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 18 18"><circle cx="9" cy="9" r="8" fill="#0078d4"/><text x="9" y="13" text-anchor="middle" font-size="8" font-family="Arial" font-weight="bold" fill="white">?</text></svg>'
    b64 = base64.b64encode(data).decode("utf-8")
    return f"data:image/svg+xml;base64,{b64}"


print("\nSearching for Azure icons...")
print(f"Icon pack: {ICON_PACK_ROOT}\n")

sql_uri  = get_uri(find_icon(ICON_PACK_ROOT, ["SQL Database", "SQL-Database", "Azure SQL"]),          "SQL Database")
stor_uri = get_uri(find_icon(ICON_PACK_ROOT, ["Storage Accounts", "Storage-Accounts"]),               "Storage Accounts")
blob_uri = get_uri(find_icon(ICON_PACK_ROOT, ["Storage Blob", "Storage-Blob", "Blob Storage"]),       "Storage Blob")
kv_uri   = get_uri(find_icon(ICON_PACK_ROOT, ["Key Vaults", "Key-Vaults", "Key Vault"]),              "Key Vaults")
cog_uri  = get_uri(find_icon(ICON_PACK_ROOT, ["Cognitive Services", "AI Foundry", "Azure AI"]),       "Cognitive Services")
app_uri  = get_uri(find_icon(ICON_PACK_ROOT, ["App Services", "App-Services"]),                       "App Services")
web_uri  = get_uri(find_icon(ICON_PACK_ROOT, ["Static Web Apps", "Static-Web-Apps"]),                 "Static Web Apps")

print("\nBuilding diagram...")

# Use a list of parts to avoid any quote/interpolation issues
parts = []

def a(s):
    parts.append(s)

a('<mxfile host="Claude" modified="2026-03-20" version="21.0.0">')
a('<diagram name="OTA Architecture" id="ota-arch-v4">')
a('<mxGraphModel dx="1422" dy="762" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="1654" pageHeight="1400" math="0" shadow="0">')
a('<root>')
a('<mxCell id="0" />')
a('<mxCell id="1" parent="0" />')

# Title
a('<mxCell id="title" value="Options Trade Analyzer - System Architecture" style="text;html=1;strokeColor=none;fillColor=none;align=center;verticalAlign=middle;whiteSpace=wrap;fontSize=22;fontStyle=1;fontColor=#1a1a2e;" vertex="1" parent="1"><mxGeometry x="200" y="20" width="1200" height="36" as="geometry" /></mxCell>')
a('<mxCell id="subtitle" value="Phase 2.3.x current state  -  Dashed border = Phase 3.x planned" style="text;html=1;strokeColor=none;fillColor=none;align=center;verticalAlign=middle;whiteSpace=wrap;fontSize=12;fontColor=#666666;" vertex="1" parent="1"><mxGeometry x="200" y="54" width="1200" height="20" as="geometry" /></mxCell>')

# Browser layer
a('<mxCell id="grp-browser" value="Browser - React / Vite" style="swimlane;startSize=32;fillColor=#dae8fc;strokeColor=#6c8ebf;fontStyle=1;fontSize=13;rounded=1;arcSize=3;" vertex="1" parent="1"><mxGeometry x="40" y="90" width="1574" height="150" as="geometry" /></mxCell>')
a('<mxCell id="ui-dashboard" value="Dashboard Widget Framework" style="rounded=1;whiteSpace=wrap;fillColor=#fff2cc;strokeColor=#d6b656;fontStyle=1;fontSize=11;" vertex="1" parent="grp-browser"><mxGeometry x="20" y="45" width="160" height="65" as="geometry" /></mxCell>')
a('<mxCell id="ui-widgets" value="Widget Registry&#xa;market_overview - actions&#xa;pnl_by_strategy - chart - media" style="rounded=1;whiteSpace=wrap;fillColor=#fff2cc;strokeColor=#d6b656;fontSize=10;" vertex="1" parent="grp-browser"><mxGeometry x="200" y="45" width="200" height="65" as="geometry" /></mxCell>')
a('<mxCell id="ui-secstrat" value="Security Strategies" style="rounded=1;whiteSpace=wrap;fillColor=#dae8fc;strokeColor=#6c8ebf;fontSize=11;" vertex="1" parent="grp-browser"><mxGeometry x="430" y="45" width="160" height="65" as="geometry" /></mxCell>')
a('<mxCell id="ui-verticals" value="Verticals" style="rounded=1;whiteSpace=wrap;fillColor=#dae8fc;strokeColor=#6c8ebf;fontSize=11;" vertex="1" parent="grp-browser"><mxGeometry x="610" y="45" width="160" height="65" as="geometry" /></mxCell>')
a('<mxCell id="ui-putscalls" value="Puts and Calls" style="rounded=1;whiteSpace=wrap;fillColor=#dae8fc;strokeColor=#6c8ebf;fontSize=11;" vertex="1" parent="grp-browser"><mxGeometry x="790" y="45" width="160" height="65" as="geometry" /></mxCell>')
a('<mxCell id="ui-positions" value="Positions" style="rounded=1;whiteSpace=wrap;fillColor=#dae8fc;strokeColor=#6c8ebf;fontSize=11;" vertex="1" parent="grp-browser"><mxGeometry x="970" y="45" width="160" height="65" as="geometry" /></mxCell>')
a('<mxCell id="e-dash-widgets" style="edgeStyle=orthogonalEdgeStyle;" edge="1" source="ui-dashboard" target="ui-widgets" parent="grp-browser"><mxGeometry relative="1" as="geometry" /></mxCell>')

# Backend layer
a('<mxCell id="grp-api" value="Backend - FastAPI (Python)" style="swimlane;startSize=32;fillColor=#d5e8d4;strokeColor=#82b366;fontStyle=1;fontSize=13;rounded=1;arcSize=3;" vertex="1" parent="1"><mxGeometry x="40" y="300" width="1574" height="185" as="geometry" /></mxCell>')
a('<mxCell id="rt-market" value="market_routes&#xa;/api/market/*" style="rounded=1;whiteSpace=wrap;fillColor=#d5e8d4;strokeColor=#82b366;fontSize=10;" vertex="1" parent="grp-api"><mxGeometry x="20" y="45" width="160" height="60" as="geometry" /></mxCell>')
a('<mxCell id="rt-analysis" value="analysis_routes&#xa;/api/analysis/*" style="rounded=1;whiteSpace=wrap;fillColor=#d5e8d4;strokeColor=#82b366;fontSize=10;" vertex="1" parent="grp-api"><mxGeometry x="200" y="45" width="160" height="60" as="geometry" /></mxCell>')
a('<mxCell id="rt-eval" value="evaluation_routes&#xa;/api/evaluate/*" style="rounded=1;whiteSpace=wrap;fillColor=#d5e8d4;strokeColor=#82b366;fontSize=10;" vertex="1" parent="grp-api"><mxGeometry x="380" y="45" width="160" height="60" as="geometry" /></mxCell>')
a('<mxCell id="rt-position" value="position_routes&#xa;/api/positions/*" style="rounded=1;whiteSpace=wrap;fillColor=#d5e8d4;strokeColor=#82b366;fontSize=10;" vertex="1" parent="grp-api"><mxGeometry x="560" y="45" width="160" height="60" as="geometry" /></mxCell>')
a('<mxCell id="rt-dashboard" value="dashboard_routes&#xa;/api/dashboard/*" style="rounded=1;whiteSpace=wrap;fillColor=#d5e8d4;strokeColor=#82b366;fontSize=10;" vertex="1" parent="grp-api"><mxGeometry x="740" y="45" width="160" height="60" as="geometry" /></mxCell>')
a('<mxCell id="rt-auth" value="auth_routes&#xa;/api/auth/*" style="rounded=1;whiteSpace=wrap;fillColor=#d5e8d4;strokeColor=#82b366;fontSize=10;" vertex="1" parent="grp-api"><mxGeometry x="920" y="45" width="160" height="60" as="geometry" /></mxCell>')
a('<mxCell id="skill-loader" value="skill_loader.py&#xa;loads SKILL.md files" style="rounded=1;whiteSpace=wrap;fillColor=#f8cecc;strokeColor=#b85450;fontSize=10;" vertex="1" parent="grp-api"><mxGeometry x="380" y="120" width="160" height="50" as="geometry" /></mxCell>')
a('<mxCell id="health-grade" value="health_grade.py&#xa;A-F engine" style="rounded=1;whiteSpace=wrap;fillColor=#f8cecc;strokeColor=#b85450;fontSize=10;" vertex="1" parent="grp-api"><mxGeometry x="560" y="120" width="160" height="50" as="geometry" /></mxCell>')
a('<mxCell id="e-eval-skill" style="edgeStyle=orthogonalEdgeStyle;" edge="1" source="rt-eval" target="skill-loader" parent="grp-api"><mxGeometry relative="1" as="geometry" /></mxCell>')
a('<mxCell id="e-pos-health" style="edgeStyle=orthogonalEdgeStyle;" edge="1" source="rt-position" target="health-grade" parent="grp-api"><mxGeometry relative="1" as="geometry" /></mxCell>')

# Data layer
a('<mxCell id="grp-data" value="Data Layer - Azure" style="swimlane;startSize=32;fillColor=#f5f5f5;strokeColor=#666666;fontStyle=1;fontSize=13;rounded=1;arcSize=3;" vertex="1" parent="1"><mxGeometry x="40" y="550" width="1574" height="240" as="geometry" /></mxCell>')

# SQL group with embedded icon
a('<mxCell id="grp-sql" value="Azure SQL - options-analyzer-db" style="swimlane;startSize=28;fillColor=#e1d5e7;strokeColor=#9673a6;fontSize=11;rounded=1;arcSize=3;" vertex="1" parent="grp-data"><mxGeometry x="20" y="40" width="1000" height="185" as="geometry" /></mxCell>')
a(f'<mxCell id="sql-badge" value="" style="image;aspect=fixed;html=1;image={sql_uri};" vertex="1" parent="grp-sql"><mxGeometry x="4" y="-20" width="36" height="36" as="geometry" /></mxCell>')
a('<mxCell id="db-users" value="users" style="shape=cylinder3;whiteSpace=wrap;fillColor=#e1d5e7;strokeColor=#9673a6;fontSize=10;verticalLabelPosition=bottom;verticalAlign=top;" vertex="1" parent="grp-sql"><mxGeometry x="60" y="45" width="90" height="80" as="geometry" /></mxCell>')
a('<mxCell id="db-positions" value="positions" style="shape=cylinder3;whiteSpace=wrap;fillColor=#e1d5e7;strokeColor=#9673a6;fontSize=10;verticalLabelPosition=bottom;verticalAlign=top;" vertex="1" parent="grp-sql"><mxGeometry x="170" y="45" width="90" height="80" as="geometry" /></mxCell>')
a('<mxCell id="db-dashlayout" value="dashboard_layouts&#xa;(2.3.x)" style="shape=cylinder3;whiteSpace=wrap;fillColor=#e1d5e7;strokeColor=#9673a6;fontSize=10;verticalLabelPosition=bottom;verticalAlign=top;" vertex="1" parent="grp-sql"><mxGeometry x="280" y="45" width="90" height="80" as="geometry" /></mxCell>')
a('<mxCell id="db-dashmedia" value="dashboard_media&#xa;(2.3.x)" style="shape=cylinder3;whiteSpace=wrap;fillColor=#e1d5e7;strokeColor=#9673a6;fontSize=10;verticalLabelPosition=bottom;verticalAlign=top;" vertex="1" parent="grp-sql"><mxGeometry x="390" y="45" width="90" height="80" as="geometry" /></mxCell>')
a('<mxCell id="db-agentlog" value="agent_run_log&#xa;(Phase 3.x)" style="shape=cylinder3;whiteSpace=wrap;fillColor=#f5f5f5;strokeColor=#bbb;strokeDashArray=4 4;fontSize=10;fontColor=#999;verticalLabelPosition=bottom;verticalAlign=top;" vertex="1" parent="grp-sql"><mxGeometry x="500" y="45" width="90" height="80" as="geometry" /></mxCell>')
a('<mxCell id="db-insights" value="insights&#xa;(Phase 3.x)" style="shape=cylinder3;whiteSpace=wrap;fillColor=#f5f5f5;strokeColor=#bbb;strokeDashArray=4 4;fontSize=10;fontColor=#999;verticalLabelPosition=bottom;verticalAlign=top;" vertex="1" parent="grp-sql"><mxGeometry x="610" y="45" width="90" height="80" as="geometry" /></mxCell>')
a('<mxCell id="db-symctx" value="symbol_context&#xa;(Phase 3.x)" style="shape=cylinder3;whiteSpace=wrap;fillColor=#f5f5f5;strokeColor=#bbb;strokeDashArray=4 4;fontSize=10;fontColor=#999;verticalLabelPosition=bottom;verticalAlign=top;" vertex="1" parent="grp-sql"><mxGeometry x="720" y="45" width="90" height="80" as="geometry" /></mxCell>')

# Blob group with embedded icons
a('<mxCell id="grp-blob" value="Azure Blob - otaunstructured" style="swimlane;startSize=28;fillColor=#ffe6cc;strokeColor=#d79b00;fontSize=11;rounded=1;arcSize=3;" vertex="1" parent="grp-data"><mxGeometry x="1040" y="40" width="420" height="185" as="geometry" /></mxCell>')
a(f'<mxCell id="storage-badge" value="" style="image;aspect=fixed;html=1;image={stor_uri};" vertex="1" parent="grp-blob"><mxGeometry x="4" y="-20" width="36" height="36" as="geometry" /></mxCell>')
a(f'<mxCell id="blob-media" value="dashboard-media/" style="image;aspect=fixed;html=1;points=[];align=center;image={blob_uri};fontSize=10;verticalLabelPosition=bottom;verticalAlign=top;" vertex="1" parent="grp-blob"><mxGeometry x="30" y="45" width="70" height="70" as="geometry" /></mxCell>')
a(f'<mxCell id="blob-docs" value="documents/" style="image;aspect=fixed;html=1;points=[];align=center;image={blob_uri};fontSize=10;verticalLabelPosition=bottom;verticalAlign=top;" vertex="1" parent="grp-blob"><mxGeometry x="165" y="45" width="70" height="70" as="geometry" /></mxCell>')
a(f'<mxCell id="blob-exports" value="backtest-exports/ (Phase 3.3.x)" style="image;aspect=fixed;html=1;points=[];align=center;image={blob_uri};fontSize=10;verticalLabelPosition=bottom;verticalAlign=top;opacity=35;" vertex="1" parent="grp-blob"><mxGeometry x="300" y="45" width="70" height="70" as="geometry" /></mxCell>')

# Key Vault
a(f'<mxCell id="kv" value="Azure Key Vault&#xa;options-analyzer" style="image;aspect=fixed;html=1;points=[];align=center;image={kv_uri};fontSize=11;verticalLabelPosition=bottom;verticalAlign=top;" vertex="1" parent="grp-data"><mxGeometry x="1490" y="75" width="65" height="65" as="geometry" /></mxCell>')

# AI & External
a('<mxCell id="grp-ai" value="AI and External Services" style="swimlane;startSize=32;fillColor=#fff2cc;strokeColor=#d6b656;fontStyle=1;fontSize=13;rounded=1;arcSize=3;" vertex="1" parent="1"><mxGeometry x="40" y="860" width="1200" height="180" as="geometry" /></mxCell>')
a(f'<mxCell id="foundry-icon" value="" style="image;aspect=fixed;html=1;points=[];align=center;image={cog_uri};" vertex="1" parent="grp-ai"><mxGeometry x="20" y="55" width="60" height="60" as="geometry" /></mxCell>')
a('<mxCell id="foundry-label" value="Azure AI Foundry&#xa;ota-foundry-resource&#xa;claude-sonnet-4-6" style="rounded=1;whiteSpace=wrap;fillColor=#dae8fc;strokeColor=#6c8ebf;fontSize=10;fontStyle=1;" vertex="1" parent="grp-ai"><mxGeometry x="90" y="50" width="180" height="70" as="geometry" /></mxCell>')
a('<mxCell id="skills" value="SKILL.md files&#xa;app/skills/*/SKILL.md" style="rounded=1;whiteSpace=wrap;fillColor=#dae8fc;strokeColor=#6c8ebf;fontSize=10;" vertex="1" parent="grp-ai"><mxGeometry x="290" y="50" width="180" height="70" as="geometry" /></mxCell>')
a(f'<mxCell id="appservice-icon" value="" style="image;aspect=fixed;html=1;points=[];align=center;image={app_uri};" vertex="1" parent="grp-ai"><mxGeometry x="510" y="55" width="60" height="60" as="geometry" /></mxCell>')
a('<mxCell id="appservice-label" value="App Service&#xa;options-analyzer-api&#xa;(FastAPI host)" style="rounded=1;whiteSpace=wrap;fillColor=#d5e8d4;strokeColor=#82b366;fontSize=10;" vertex="1" parent="grp-ai"><mxGeometry x="580" y="50" width="180" height="70" as="geometry" /></mxCell>')
a(f'<mxCell id="staticweb-icon" value="" style="image;aspect=fixed;html=1;points=[];align=center;image={web_uri};" vertex="1" parent="grp-ai"><mxGeometry x="800" y="55" width="60" height="60" as="geometry" /></mxCell>')
a('<mxCell id="staticweb-label" value="Static Web App&#xa;options-analyzer-web&#xa;(React frontend host)" style="rounded=1;whiteSpace=wrap;fillColor=#d5e8d4;strokeColor=#82b366;fontSize=10;" vertex="1" parent="grp-ai"><mxGeometry x="870" y="50" width="180" height="70" as="geometry" /></mxCell>')
a('<mxCell id="e-foundry-skills" style="edgeStyle=orthogonalEdgeStyle;" edge="1" source="foundry-label" target="skills" parent="grp-ai"><mxGeometry relative="1" as="geometry" /></mxCell>')

# Schwab
a('<mxCell id="schwab" value="Schwab API&#xa;quotes - chains - OAuth&#xa;(sole market data provider)" style="rounded=1;whiteSpace=wrap;fillColor=#d5e8d4;strokeColor=#82b366;fontSize=10;fontStyle=1;" vertex="1" parent="1"><mxGeometry x="1280" y="910" width="200" height="80" as="geometry" /></mxCell>')

# Legend
a('<mxCell id="legend" value="Legend" style="swimlane;startSize=28;fillColor=#f5f5f5;strokeColor=#666;fontSize=12;fontStyle=1;rounded=1;" vertex="1" parent="1"><mxGeometry x="1280" y="1020" width="300" height="215" as="geometry" /></mxCell>')
a('<mxCell id="leg1" value="React Frontend" style="rounded=1;fillColor=#dae8fc;strokeColor=#6c8ebf;fontSize=11;" vertex="1" parent="legend"><mxGeometry x="10" y="35" width="160" height="28" as="geometry" /></mxCell>')
a('<mxCell id="leg2" value="FastAPI Backend" style="rounded=1;fillColor=#d5e8d4;strokeColor=#82b366;fontSize=11;" vertex="1" parent="legend"><mxGeometry x="10" y="70" width="160" height="28" as="geometry" /></mxCell>')
a('<mxCell id="leg3" value="Azure SQL / Blob" style="rounded=1;fillColor=#e1d5e7;strokeColor=#9673a6;fontSize=11;" vertex="1" parent="legend"><mxGeometry x="10" y="105" width="160" height="28" as="geometry" /></mxCell>')
a('<mxCell id="leg4" value="AI / Key Vault" style="rounded=1;fillColor=#f8cecc;strokeColor=#b85450;fontSize=11;" vertex="1" parent="legend"><mxGeometry x="10" y="140" width="160" height="28" as="geometry" /></mxCell>')
a('<mxCell id="leg5" value="Phase 3.x (planned)" style="rounded=1;fillColor=#f5f5f5;strokeColor=#bbb;strokeDashArray=4 4;fontSize=11;fontColor=#888;" vertex="1" parent="legend"><mxGeometry x="10" y="175" width="160" height="28" as="geometry" /></mxCell>')

# Agents
a('<mxCell id="grp-agents" value="Phase 3.x - Agent Platform (planned)" style="swimlane;startSize=32;fillColor=#f5f5f5;strokeColor=#aaaaaa;fontStyle=3;fontSize=13;rounded=1;arcSize=3;strokeDashArray=8 4;fontColor=#999999;" vertex="1" parent="1"><mxGeometry x="40" y="1100" width="1200" height="150" as="geometry" /></mxCell>')
a('<mxCell id="agent-posmon" value="Position Monitor Agent&#xa;runs after market close" style="rounded=1;whiteSpace=wrap;fillColor=#f5f5f5;strokeColor=#bbb;strokeDashArray=4 4;fontSize=10;fontColor=#888;" vertex="1" parent="grp-agents"><mxGeometry x="20" y="50" width="200" height="70" as="geometry" /></mxCell>')
a('<mxCell id="agent-insight" value="Insight Engine&#xa;generic anomaly detection" style="rounded=1;whiteSpace=wrap;fillColor=#f5f5f5;strokeColor=#bbb;strokeDashArray=4 4;fontSize=10;fontColor=#888;" vertex="1" parent="grp-agents"><mxGeometry x="250" y="50" width="200" height="70" as="geometry" /></mxCell>')
a('<mxCell id="agent-portfolio" value="Portfolio Risk Agent&#xa;3.1.x" style="rounded=1;whiteSpace=wrap;fillColor=#f5f5f5;strokeColor=#bbb;strokeDashArray=4 4;fontSize=10;fontColor=#888;" vertex="1" parent="grp-agents"><mxGeometry x="480" y="50" width="200" height="70" as="geometry" /></mxCell>')
a('<mxCell id="agent-scan" value="Market Scan Agent&#xa;3.2.x" style="rounded=1;whiteSpace=wrap;fillColor=#f5f5f5;strokeColor=#bbb;strokeDashArray=4 4;fontSize=10;fontColor=#888;" vertex="1" parent="grp-agents"><mxGeometry x="710" y="50" width="200" height="70" as="geometry" /></mxCell>')
a('<mxCell id="e-posmon-insight" style="edgeStyle=orthogonalEdgeStyle;strokeDashArray=4 4;strokeColor=#bbb;" edge="1" source="agent-posmon" target="agent-insight" parent="grp-agents"><mxGeometry relative="1" as="geometry" /></mxCell>')

# Edges
edges = [
    ("e-dash-market",    "ui-dashboard",  "rt-market",       "1"),
    ("e-dash-dash",      "ui-dashboard",  "rt-dashboard",    "1"),
    ("e-sec-analysis",   "ui-secstrat",   "rt-analysis",     "1"),
    ("e-sec-eval",       "ui-secstrat",   "rt-eval",         "1"),
    ("e-vert-analysis",  "ui-verticals",  "rt-analysis",     "1"),
    ("e-pc-analysis",    "ui-putscalls",  "rt-analysis",     "1"),
    ("e-pos-rt",         "ui-positions",  "rt-position",     "1"),
    ("e-market-schwab",  "rt-market",     "schwab",          "1"),
    ("e-analysis-schwab","rt-analysis",   "schwab",          "1"),
    ("e-eval-foundry",   "rt-eval",       "foundry-label",   "1"),
    ("e-rt-pos-db",      "rt-position",   "db-positions",    "1"),
    ("e-rt-dash-layout", "rt-dashboard",  "db-dashlayout",   "1"),
    ("e-rt-dash-media",  "rt-dashboard",  "db-dashmedia",    "1"),
    ("e-rt-dash-blob",   "rt-dashboard",  "blob-media",      "1"),
    ("e-rt-auth-users",  "rt-auth",       "db-users",        "1"),
    ("e-api-kv",         "grp-api",       "kv",              "1"),
    ("e-agent-pos",      "agent-posmon",  "db-positions",    "1"),
    ("e-agent-sym",      "agent-posmon",  "db-symctx",       "1"),
    ("e-insight-db",     "agent-insight", "db-insights",     "1"),
    ("e-insight-foundry","agent-insight", "foundry-label",   "1"),
]

for eid, src, tgt, parent in edges:
    dash = ' strokeDashArray=4 4; strokeColor=#bbb;' if "agent" in eid or "insight" in eid else ""
    a(f'<mxCell id="{eid}" style="edgeStyle=orthogonalEdgeStyle;{dash}" edge="1" source="{src}" target="{tgt}" parent="{parent}"><mxGeometry relative="1" as="geometry" /></mxCell>')

a('</root></mxGraphModel></diagram></mxfile>')

xml = "".join(parts)

# Backup and write
if os.path.exists(OUTPUT_FILE):
    import shutil
    shutil.copy2(OUTPUT_FILE, OUTPUT_FILE + ".bak")
    print(f"Backed up previous diagram to {OUTPUT_FILE}.bak")

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    f.write(xml)

size_kb = os.path.getsize(OUTPUT_FILE) / 1024
print(f"\nDone! {OUTPUT_FILE} written ({size_kb:.1f} KB)")
print("\nNext steps:")
print("  1. Open architecture-diagram.drawio in VS Code (Draw.io extension)")
print("  2. Icons are fully embedded - no internet required")
print("  3. git add architecture-diagram.drawio")
