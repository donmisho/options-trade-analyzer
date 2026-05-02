# build-diagram-with-icons.ps1
# ─────────────────────────────────────────────────────────────────────────────
# Finds the 7 Azure SVG icons from the Microsoft icon pack, base64-encodes them,
# and writes architecture-diagram.drawio with all icons fully embedded.
#
# Usage:
#   .\build-diagram-with-icons.ps1
#
# Run from the project root (options-analyzer/)
# ─────────────────────────────────────────────────────────────────────────────

$ErrorActionPreference = "Stop"
$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$IconPackRoot = "C:\Users\DonMishory\OneDrive - jmholistic.com\Microsoft Content\Architecture Diagrams and Icons"
$OutputPath  = Join-Path $ScriptDir "architecture-diagram.drawio"

# ── Helper: find icon file by partial name under a root folder ────────────────
function Find-Icon {
    param([string]$Root, [string[]]$SearchTerms)
    foreach ($term in $SearchTerms) {
        $found = Get-ChildItem -Path $Root -Recurse -Filter "*.svg" -ErrorAction SilentlyContinue |
                 Where-Object { $_.Name -like "*$term*" } |
                 Select-Object -First 1
        if ($found) { return $found.FullName }
    }
    return $null
}

# ── Helper: read SVG and return base64 data URI ───────────────────────────────
function Get-IconDataUri {
    param([string]$Path, [string]$Label)
    if (-not $Path -or -not (Test-Path $Path)) {
        Write-Warning "  [$Label] NOT FOUND — will use placeholder"
        # Simple colored circle as fallback
        $fallback = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 18 18"><circle cx="9" cy="9" r="8" fill="#0078d4"/><text x="9" y="13" text-anchor="middle" font-size="8" font-family="Arial" font-weight="bold" fill="white">?</text></svg>'
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($fallback)
        return "data:image/svg+xml;base64," + [Convert]::ToBase64String($bytes)
    }
    Write-Host "  [$Label] Found: $Path" -ForegroundColor Green
    $bytes = [System.IO.File]::ReadAllBytes($Path)
    return "data:image/svg+xml;base64," + [Convert]::ToBase64String($bytes)
}

# ── Find each icon ─────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "Searching for Azure icons in:" -ForegroundColor Cyan
Write-Host "  $IconPackRoot" -ForegroundColor White
Write-Host ""

$sqlPath        = Find-Icon $IconPackRoot @("SQL Database", "SQL-Database", "Azure SQL")
$storagePath    = Find-Icon $IconPackRoot @("Storage Accounts", "Storage-Accounts")
$blobPath       = Find-Icon $IconPackRoot @("Storage Blob", "Storage-Blob", "Blob Storage", "Azure-Blob")
$kvPath         = Find-Icon $IconPackRoot @("Key Vaults", "Key-Vaults", "Key Vault")
$cognitivePath  = Find-Icon $IconPackRoot @("Cognitive Services", "Cognitive-Services", "Azure AI", "AI Foundry")
$appSvcPath     = Find-Icon $IconPackRoot @("App Services", "App-Services")
$staticWebPath  = Find-Icon $IconPackRoot @("Static Web Apps", "Static-Web-Apps", "Static Web App")

# ── Encode to base64 data URIs ─────────────────────────────────────────────────
$SQL        = Get-IconDataUri $sqlPath       "SQL Database"
$STORAGE    = Get-IconDataUri $storagePath   "Storage Accounts"
$BLOB       = Get-IconDataUri $blobPath      "Storage Blob"
$KV         = Get-IconDataUri $kvPath        "Key Vaults"
$COGNITIVE  = Get-IconDataUri $cognitivePath "Cognitive Services"
$APPSERVICE = Get-IconDataUri $appSvcPath    "App Services"
$STATICWEB  = Get-IconDataUri $staticWebPath "Static Web Apps"

Write-Host ""
Write-Host "Building diagram..." -ForegroundColor Cyan

# ── Build the mxGraph XML ──────────────────────────────────────────────────────
$xml = @"
<mxfile host="Claude" modified="2026-03-20" version="21.0.0">
  <diagram name="OTA Architecture" id="ota-arch-v4">
    <mxGraphModel dx="1422" dy="762" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="1654" pageHeight="1400" math="0" shadow="0">
      <root>
        <mxCell id="0" />
        <mxCell id="1" parent="0" />

        <mxCell id="title" value="Options Trade Analyzer — System Architecture" style="text;html=1;strokeColor=none;fillColor=none;align=center;verticalAlign=middle;whiteSpace=wrap;fontSize=22;fontStyle=1;fontColor=#1a1a2e;" vertex="1" parent="1">
          <mxGeometry x="200" y="20" width="1200" height="36" as="geometry" />
        </mxCell>
        <mxCell id="subtitle" value="Phase 2.3.x current state  ·  Dashed border = Phase 3.x planned" style="text;html=1;strokeColor=none;fillColor=none;align=center;verticalAlign=middle;whiteSpace=wrap;fontSize=12;fontColor=#666666;" vertex="1" parent="1">
          <mxGeometry x="200" y="54" width="1200" height="20" as="geometry" />
        </mxCell>

        <!-- BROWSER -->
        <mxCell id="grp-browser" value="Browser — React / Vite" style="swimlane;startSize=32;fillColor=#dae8fc;strokeColor=#6c8ebf;fontStyle=1;fontSize=13;rounded=1;arcSize=3;" vertex="1" parent="1">
          <mxGeometry x="40" y="90" width="1574" height="150" as="geometry" />
        </mxCell>
        <mxCell id="ui-dashboard" value="Dashboard&#xa;Widget Framework" style="rounded=1;whiteSpace=wrap;fillColor=#fff2cc;strokeColor=#d6b656;fontStyle=1;fontSize=11;" vertex="1" parent="grp-browser">
          <mxGeometry x="20" y="45" width="160" height="65" as="geometry" />
        </mxCell>
        <mxCell id="ui-widgets" value="Widget Registry&#xa;market_overview · actions&#xa;pnl_by_strategy · chart · media" style="rounded=1;whiteSpace=wrap;fillColor=#fff2cc;strokeColor=#d6b656;fontSize=10;" vertex="1" parent="grp-browser">
          <mxGeometry x="200" y="45" width="200" height="65" as="geometry" />
        </mxCell>
        <mxCell id="ui-secstrat" value="Security Strategies" style="rounded=1;whiteSpace=wrap;fillColor=#dae8fc;strokeColor=#6c8ebf;fontSize=11;" vertex="1" parent="grp-browser">
          <mxGeometry x="430" y="45" width="160" height="65" as="geometry" />
        </mxCell>
        <mxCell id="ui-verticals" value="Verticals" style="rounded=1;whiteSpace=wrap;fillColor=#dae8fc;strokeColor=#6c8ebf;fontSize=11;" vertex="1" parent="grp-browser">
          <mxGeometry x="610" y="45" width="160" height="65" as="geometry" />
        </mxCell>
        <mxCell id="ui-putscalls" value="Puts &amp; Calls" style="rounded=1;whiteSpace=wrap;fillColor=#dae8fc;strokeColor=#6c8ebf;fontSize=11;" vertex="1" parent="grp-browser">
          <mxGeometry x="790" y="45" width="160" height="65" as="geometry" />
        </mxCell>
        <mxCell id="ui-positions" value="Positions" style="rounded=1;whiteSpace=wrap;fillColor=#dae8fc;strokeColor=#6c8ebf;fontSize=11;" vertex="1" parent="grp-browser">
          <mxGeometry x="970" y="45" width="160" height="65" as="geometry" />
        </mxCell>
        <mxCell id="e-dash-widgets" style="edgeStyle=orthogonalEdgeStyle;" edge="1" source="ui-dashboard" target="ui-widgets" parent="grp-browser">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>

        <!-- BACKEND -->
        <mxCell id="grp-api" value="Backend — FastAPI (Python)" style="swimlane;startSize=32;fillColor=#d5e8d4;strokeColor=#82b366;fontStyle=1;fontSize=13;rounded=1;arcSize=3;" vertex="1" parent="1">
          <mxGeometry x="40" y="300" width="1574" height="185" as="geometry" />
        </mxCell>
        <mxCell id="rt-market" value="market_routes&#xa;/api/market/*" style="rounded=1;whiteSpace=wrap;fillColor=#d5e8d4;strokeColor=#82b366;fontSize=10;" vertex="1" parent="grp-api">
          <mxGeometry x="20" y="45" width="160" height="60" as="geometry" />
        </mxCell>
        <mxCell id="rt-analysis" value="analysis_routes&#xa;/api/analysis/*" style="rounded=1;whiteSpace=wrap;fillColor=#d5e8d4;strokeColor=#82b366;fontSize=10;" vertex="1" parent="grp-api">
          <mxGeometry x="200" y="45" width="160" height="60" as="geometry" />
        </mxCell>
        <mxCell id="rt-eval" value="evaluation_routes&#xa;/api/evaluate/*" style="rounded=1;whiteSpace=wrap;fillColor=#d5e8d4;strokeColor=#82b366;fontSize=10;" vertex="1" parent="grp-api">
          <mxGeometry x="380" y="45" width="160" height="60" as="geometry" />
        </mxCell>
        <mxCell id="rt-position" value="position_routes&#xa;/api/positions/*" style="rounded=1;whiteSpace=wrap;fillColor=#d5e8d4;strokeColor=#82b366;fontSize=10;" vertex="1" parent="grp-api">
          <mxGeometry x="560" y="45" width="160" height="60" as="geometry" />
        </mxCell>
        <mxCell id="rt-dashboard" value="dashboard_routes&#xa;/api/dashboard/*" style="rounded=1;whiteSpace=wrap;fillColor=#d5e8d4;strokeColor=#82b366;fontSize=10;" vertex="1" parent="grp-api">
          <mxGeometry x="740" y="45" width="160" height="60" as="geometry" />
        </mxCell>
        <mxCell id="rt-auth" value="auth_routes&#xa;/api/auth/*" style="rounded=1;whiteSpace=wrap;fillColor=#d5e8d4;strokeColor=#82b366;fontSize=10;" vertex="1" parent="grp-api">
          <mxGeometry x="920" y="45" width="160" height="60" as="geometry" />
        </mxCell>
        <mxCell id="skill-loader" value="skill_loader.py&#xa;loads SKILL.md files" style="rounded=1;whiteSpace=wrap;fillColor=#f8cecc;strokeColor=#b85450;fontSize=10;" vertex="1" parent="grp-api">
          <mxGeometry x="380" y="120" width="160" height="50" as="geometry" />
        </mxCell>
        <mxCell id="health-grade" value="health_grade.py&#xa;A-F engine" style="rounded=1;whiteSpace=wrap;fillColor=#f8cecc;strokeColor=#b85450;fontSize=10;" vertex="1" parent="grp-api">
          <mxGeometry x="560" y="120" width="160" height="50" as="geometry" />
        </mxCell>
        <mxCell id="e-eval-skill" style="edgeStyle=orthogonalEdgeStyle;" edge="1" source="rt-eval" target="skill-loader" parent="grp-api">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>
        <mxCell id="e-pos-health" style="edgeStyle=orthogonalEdgeStyle;" edge="1" source="rt-position" target="health-grade" parent="grp-api">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>

        <!-- DATA LAYER -->
        <mxCell id="grp-data" value="Data Layer — Azure" style="swimlane;startSize=32;fillColor=#f5f5f5;strokeColor=#666666;fontStyle=1;fontSize=13;rounded=1;arcSize=3;" vertex="1" parent="1">
          <mxGeometry x="40" y="550" width="1574" height="240" as="geometry" />
        </mxCell>

        <!-- Azure SQL -->
        <mxCell id="grp-sql" value="Azure SQL — options-analyzer-db" style="swimlane;startSize=28;fillColor=#e1d5e7;strokeColor=#9673a6;fontSize=11;rounded=1;arcSize=3;" vertex="1" parent="grp-data">
          <mxGeometry x="20" y="40" width="1000" height="185" as="geometry" />
        </mxCell>
        <mxCell id="sql-badge" value="" style="image;aspect=fixed;html=1;image=$SQL;" vertex="1" parent="grp-sql">
          <mxGeometry x="4" y="-20" width="36" height="36" as="geometry" />
        </mxCell>
        <mxCell id="db-users" value="users" style="shape=cylinder3;whiteSpace=wrap;fillColor=#e1d5e7;strokeColor=#9673a6;fontSize=10;verticalLabelPosition=bottom;verticalAlign=top;" vertex="1" parent="grp-sql">
          <mxGeometry x="60" y="45" width="90" height="80" as="geometry" />
        </mxCell>
        <mxCell id="db-positions" value="positions" style="shape=cylinder3;whiteSpace=wrap;fillColor=#e1d5e7;strokeColor=#9673a6;fontSize=10;verticalLabelPosition=bottom;verticalAlign=top;" vertex="1" parent="grp-sql">
          <mxGeometry x="170" y="45" width="90" height="80" as="geometry" />
        </mxCell>
        <mxCell id="db-dashlayout" value="dashboard_layouts&#xa;(2.3.x)" style="shape=cylinder3;whiteSpace=wrap;fillColor=#e1d5e7;strokeColor=#9673a6;fontSize=10;verticalLabelPosition=bottom;verticalAlign=top;" vertex="1" parent="grp-sql">
          <mxGeometry x="280" y="45" width="90" height="80" as="geometry" />
        </mxCell>
        <mxCell id="db-dashmedia" value="dashboard_media&#xa;(2.3.x)" style="shape=cylinder3;whiteSpace=wrap;fillColor=#e1d5e7;strokeColor=#9673a6;fontSize=10;verticalLabelPosition=bottom;verticalAlign=top;" vertex="1" parent="grp-sql">
          <mxGeometry x="390" y="45" width="90" height="80" as="geometry" />
        </mxCell>
        <mxCell id="db-agentlog" value="agent_run_log&#xa;(Phase 3.x)" style="shape=cylinder3;whiteSpace=wrap;fillColor=#f5f5f5;strokeColor=#bbb;strokeDashArray=4 4;fontSize=10;fontColor=#999;verticalLabelPosition=bottom;verticalAlign=top;" vertex="1" parent="grp-sql">
          <mxGeometry x="500" y="45" width="90" height="80" as="geometry" />
        </mxCell>
        <mxCell id="db-insights" value="insights&#xa;(Phase 3.x)" style="shape=cylinder3;whiteSpace=wrap;fillColor=#f5f5f5;strokeColor=#bbb;strokeDashArray=4 4;fontSize=10;fontColor=#999;verticalLabelPosition=bottom;verticalAlign=top;" vertex="1" parent="grp-sql">
          <mxGeometry x="610" y="45" width="90" height="80" as="geometry" />
        </mxCell>
        <mxCell id="db-symctx" value="symbol_context&#xa;(Phase 3.x)" style="shape=cylinder3;whiteSpace=wrap;fillColor=#f5f5f5;strokeColor=#bbb;strokeDashArray=4 4;fontSize=10;fontColor=#999;verticalLabelPosition=bottom;verticalAlign=top;" vertex="1" parent="grp-sql">
          <mxGeometry x="720" y="45" width="90" height="80" as="geometry" />
        </mxCell>

        <!-- Azure Blob -->
        <mxCell id="grp-blob" value="Azure Blob — otaunstructured" style="swimlane;startSize=28;fillColor=#ffe6cc;strokeColor=#d79b00;fontSize=11;rounded=1;arcSize=3;" vertex="1" parent="grp-data">
          <mxGeometry x="1040" y="40" width="420" height="185" as="geometry" />
        </mxCell>
        <mxCell id="storage-badge" value="" style="image;aspect=fixed;html=1;image=$STORAGE;" vertex="1" parent="grp-blob">
          <mxGeometry x="4" y="-20" width="36" height="36" as="geometry" />
        </mxCell>
        <mxCell id="blob-media" value="dashboard-media/" style="image;aspect=fixed;html=1;points=[];align=center;image=$BLOB;fontSize=10;verticalLabelPosition=bottom;verticalAlign=top;" vertex="1" parent="grp-blob">
          <mxGeometry x="30" y="45" width="70" height="70" as="geometry" />
        </mxCell>
        <mxCell id="blob-docs" value="documents/" style="image;aspect=fixed;html=1;points=[];align=center;image=$BLOB;fontSize=10;verticalLabelPosition=bottom;verticalAlign=top;" vertex="1" parent="grp-blob">
          <mxGeometry x="165" y="45" width="70" height="70" as="geometry" />
        </mxCell>
        <mxCell id="blob-exports" value="backtest-exports/&#xa;(Phase 3.3.x)" style="image;aspect=fixed;html=1;points=[];align=center;image=$BLOB;fontSize=10;verticalLabelPosition=bottom;verticalAlign=top;opacity=35;" vertex="1" parent="grp-blob">
          <mxGeometry x="300" y="45" width="70" height="70" as="geometry" />
        </mxCell>

        <!-- Key Vault -->
        <mxCell id="kv" value="Azure Key Vault&#xa;options-analyzer" style="image;aspect=fixed;html=1;points=[];align=center;image=$KV;fontSize=11;verticalLabelPosition=bottom;verticalAlign=top;" vertex="1" parent="grp-data">
          <mxGeometry x="1490" y="75" width="65" height="65" as="geometry" />
        </mxCell>

        <!-- AI & EXTERNAL SERVICES -->
        <mxCell id="grp-ai" value="AI &amp; External Services" style="swimlane;startSize=32;fillColor=#fff2cc;strokeColor=#d6b656;fontStyle=1;fontSize=13;rounded=1;arcSize=3;" vertex="1" parent="1">
          <mxGeometry x="40" y="860" width="1200" height="180" as="geometry" />
        </mxCell>
        <mxCell id="foundry-icon" value="" style="image;aspect=fixed;html=1;points=[];align=center;image=$COGNITIVE;" vertex="1" parent="grp-ai">
          <mxGeometry x="20" y="55" width="60" height="60" as="geometry" />
        </mxCell>
        <mxCell id="foundry-label" value="Azure AI Foundry&#xa;ota-foundry-resource&#xa;claude-sonnet-4-6" style="rounded=1;whiteSpace=wrap;fillColor=#dae8fc;strokeColor=#6c8ebf;fontSize=10;fontStyle=1;" vertex="1" parent="grp-ai">
          <mxGeometry x="90" y="50" width="180" height="70" as="geometry" />
        </mxCell>
        <mxCell id="skills" value="SKILL.md files&#xa;app/skills/*/SKILL.md&#xa;prompt engineering" style="rounded=1;whiteSpace=wrap;fillColor=#dae8fc;strokeColor=#6c8ebf;fontSize=10;" vertex="1" parent="grp-ai">
          <mxGeometry x="290" y="50" width="180" height="70" as="geometry" />
        </mxCell>
        <mxCell id="appservice-icon" value="" style="image;aspect=fixed;html=1;points=[];align=center;image=$APPSERVICE;" vertex="1" parent="grp-ai">
          <mxGeometry x="510" y="55" width="60" height="60" as="geometry" />
        </mxCell>
        <mxCell id="appservice-label" value="App Service&#xa;options-analyzer-api&#xa;(FastAPI host)" style="rounded=1;whiteSpace=wrap;fillColor=#d5e8d4;strokeColor=#82b366;fontSize=10;" vertex="1" parent="grp-ai">
          <mxGeometry x="580" y="50" width="180" height="70" as="geometry" />
        </mxCell>
        <mxCell id="staticweb-icon" value="" style="image;aspect=fixed;html=1;points=[];align=center;image=$STATICWEB;" vertex="1" parent="grp-ai">
          <mxGeometry x="800" y="55" width="60" height="60" as="geometry" />
        </mxCell>
        <mxCell id="staticweb-label" value="Static Web App&#xa;options-analyzer-web&#xa;(React frontend host)" style="rounded=1;whiteSpace=wrap;fillColor=#d5e8d4;strokeColor=#82b366;fontSize=10;" vertex="1" parent="grp-ai">
          <mxGeometry x="870" y="50" width="180" height="70" as="geometry" />
        </mxCell>
        <mxCell id="e-foundry-skills" style="edgeStyle=orthogonalEdgeStyle;" edge="1" source="foundry-label" target="skills" parent="grp-ai">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>

        <!-- Schwab -->
        <mxCell id="schwab" value="Schwab API&#xa;quotes · chains · OAuth&#xa;(sole market data provider)" style="rounded=1;whiteSpace=wrap;fillColor=#d5e8d4;strokeColor=#82b366;fontSize=10;fontStyle=1;" vertex="1" parent="1">
          <mxGeometry x="1280" y="910" width="200" height="80" as="geometry" />
        </mxCell>

        <!-- LEGEND -->
        <mxCell id="legend" value="Legend" style="swimlane;startSize=28;fillColor=#f5f5f5;strokeColor=#666;fontSize=12;fontStyle=1;rounded=1;" vertex="1" parent="1">
          <mxGeometry x="1280" y="1020" width="300" height="215" as="geometry" />
        </mxCell>
        <mxCell id="leg1" value="React Frontend" style="rounded=1;fillColor=#dae8fc;strokeColor=#6c8ebf;fontSize=11;" vertex="1" parent="legend">
          <mxGeometry x="10" y="35" width="160" height="28" as="geometry" />
        </mxCell>
        <mxCell id="leg2" value="FastAPI Backend" style="rounded=1;fillColor=#d5e8d4;strokeColor=#82b366;fontSize=11;" vertex="1" parent="legend">
          <mxGeometry x="10" y="70" width="160" height="28" as="geometry" />
        </mxCell>
        <mxCell id="leg3" value="Azure SQL / Blob" style="rounded=1;fillColor=#e1d5e7;strokeColor=#9673a6;fontSize=11;" vertex="1" parent="legend">
          <mxGeometry x="10" y="105" width="160" height="28" as="geometry" />
        </mxCell>
        <mxCell id="leg4" value="AI / Key Vault" style="rounded=1;fillColor=#f8cecc;strokeColor=#b85450;fontSize=11;" vertex="1" parent="legend">
          <mxGeometry x="10" y="140" width="160" height="28" as="geometry" />
        </mxCell>
        <mxCell id="leg5" value="Phase 3.x (planned)" style="rounded=1;fillColor=#f5f5f5;strokeColor=#bbb;strokeDashArray=4 4;fontSize=11;fontColor=#888;" vertex="1" parent="legend">
          <mxGeometry x="10" y="175" width="160" height="28" as="geometry" />
        </mxCell>

        <!-- PHASE 3.X AGENTS -->
        <mxCell id="grp-agents" value="Phase 3.x — Agent Platform (planned)" style="swimlane;startSize=32;fillColor=#f5f5f5;strokeColor=#aaaaaa;fontStyle=3;fontSize=13;rounded=1;arcSize=3;strokeDashArray=8 4;fontColor=#999999;" vertex="1" parent="1">
          <mxGeometry x="40" y="1100" width="1200" height="150" as="geometry" />
        </mxCell>
        <mxCell id="agent-posmon" value="Position Monitor Agent&#xa;runs after market close" style="rounded=1;whiteSpace=wrap;fillColor=#f5f5f5;strokeColor=#bbb;strokeDashArray=4 4;fontSize=10;fontColor=#888;" vertex="1" parent="grp-agents">
          <mxGeometry x="20" y="50" width="200" height="70" as="geometry" />
        </mxCell>
        <mxCell id="agent-insight" value="Insight Engine&#xa;generic anomaly detection" style="rounded=1;whiteSpace=wrap;fillColor=#f5f5f5;strokeColor=#bbb;strokeDashArray=4 4;fontSize=10;fontColor=#888;" vertex="1" parent="grp-agents">
          <mxGeometry x="250" y="50" width="200" height="70" as="geometry" />
        </mxCell>
        <mxCell id="agent-portfolio" value="Portfolio Risk Agent&#xa;3.1.x" style="rounded=1;whiteSpace=wrap;fillColor=#f5f5f5;strokeColor=#bbb;strokeDashArray=4 4;fontSize=10;fontColor=#888;" vertex="1" parent="grp-agents">
          <mxGeometry x="480" y="50" width="200" height="70" as="geometry" />
        </mxCell>
        <mxCell id="agent-scan" value="Market Scan Agent&#xa;3.2.x" style="rounded=1;whiteSpace=wrap;fillColor=#f5f5f5;strokeColor=#bbb;strokeDashArray=4 4;fontSize=10;fontColor=#888;" vertex="1" parent="grp-agents">
          <mxGeometry x="710" y="50" width="200" height="70" as="geometry" />
        </mxCell>
        <mxCell id="e-posmon-insight" style="edgeStyle=orthogonalEdgeStyle;strokeDashArray=4 4;strokeColor=#bbb;" edge="1" source="agent-posmon" target="agent-insight" parent="grp-agents">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>

        <!-- CROSS-GROUP EDGES -->
        <mxCell id="e-dash-market" style="edgeStyle=orthogonalEdgeStyle;" edge="1" source="ui-dashboard" target="rt-market" parent="1"><mxGeometry relative="1" as="geometry" /></mxCell>
        <mxCell id="e-dash-dash" style="edgeStyle=orthogonalEdgeStyle;" edge="1" source="ui-dashboard" target="rt-dashboard" parent="1"><mxGeometry relative="1" as="geometry" /></mxCell>
        <mxCell id="e-sec-analysis" style="edgeStyle=orthogonalEdgeStyle;" edge="1" source="ui-secstrat" target="rt-analysis" parent="1"><mxGeometry relative="1" as="geometry" /></mxCell>
        <mxCell id="e-sec-eval" style="edgeStyle=orthogonalEdgeStyle;" edge="1" source="ui-secstrat" target="rt-eval" parent="1"><mxGeometry relative="1" as="geometry" /></mxCell>
        <mxCell id="e-vert-analysis" style="edgeStyle=orthogonalEdgeStyle;" edge="1" source="ui-verticals" target="rt-analysis" parent="1"><mxGeometry relative="1" as="geometry" /></mxCell>
        <mxCell id="e-pc-analysis" style="edgeStyle=orthogonalEdgeStyle;" edge="1" source="ui-putscalls" target="rt-analysis" parent="1"><mxGeometry relative="1" as="geometry" /></mxCell>
        <mxCell id="e-pos-rt" style="edgeStyle=orthogonalEdgeStyle;" edge="1" source="ui-positions" target="rt-position" parent="1"><mxGeometry relative="1" as="geometry" /></mxCell>
        <mxCell id="e-market-schwab" style="edgeStyle=orthogonalEdgeStyle;" edge="1" source="rt-market" target="schwab" parent="1"><mxGeometry relative="1" as="geometry" /></mxCell>
        <mxCell id="e-analysis-schwab" style="edgeStyle=orthogonalEdgeStyle;" edge="1" source="rt-analysis" target="schwab" parent="1"><mxGeometry relative="1" as="geometry" /></mxCell>
        <mxCell id="e-eval-foundry" style="edgeStyle=orthogonalEdgeStyle;" edge="1" source="rt-eval" target="foundry-label" parent="1"><mxGeometry relative="1" as="geometry" /></mxCell>
        <mxCell id="e-rt-pos-db" style="edgeStyle=orthogonalEdgeStyle;" edge="1" source="rt-position" target="db-positions" parent="1"><mxGeometry relative="1" as="geometry" /></mxCell>
        <mxCell id="e-rt-dash-layout" style="edgeStyle=orthogonalEdgeStyle;" edge="1" source="rt-dashboard" target="db-dashlayout" parent="1"><mxGeometry relative="1" as="geometry" /></mxCell>
        <mxCell id="e-rt-dash-media" style="edgeStyle=orthogonalEdgeStyle;" edge="1" source="rt-dashboard" target="db-dashmedia" parent="1"><mxGeometry relative="1" as="geometry" /></mxCell>
        <mxCell id="e-rt-dash-blob" style="edgeStyle=orthogonalEdgeStyle;" edge="1" source="rt-dashboard" target="blob-media" parent="1"><mxGeometry relative="1" as="geometry" /></mxCell>
        <mxCell id="e-rt-auth-users" style="edgeStyle=orthogonalEdgeStyle;" edge="1" source="rt-auth" target="db-users" parent="1"><mxGeometry relative="1" as="geometry" /></mxCell>
        <mxCell id="e-api-kv" style="edgeStyle=orthogonalEdgeStyle;" edge="1" source="grp-api" target="kv" parent="1"><mxGeometry relative="1" as="geometry" /></mxCell>
        <mxCell id="e-agent-pos" style="edgeStyle=orthogonalEdgeStyle;strokeDashArray=4 4;strokeColor=#bbb;" edge="1" source="agent-posmon" target="db-positions" parent="1"><mxGeometry relative="1" as="geometry" /></mxCell>
        <mxCell id="e-agent-sym" style="edgeStyle=orthogonalEdgeStyle;strokeDashArray=4 4;strokeColor=#bbb;" edge="1" source="agent-posmon" target="db-symctx" parent="1"><mxGeometry relative="1" as="geometry" /></mxCell>
        <mxCell id="e-insight-db" style="edgeStyle=orthogonalEdgeStyle;strokeDashArray=4 4;strokeColor=#bbb;" edge="1" source="agent-insight" target="db-insights" parent="1"><mxGeometry relative="1" as="geometry" /></mxCell>
        <mxCell id="e-insight-foundry" style="edgeStyle=orthogonalEdgeStyle;strokeDashArray=4 4;strokeColor=#bbb;" edge="1" source="agent-insight" target="foundry-label" parent="1"><mxGeometry relative="1" as="geometry" /></mxCell>

      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
"@

# ── Write file ─────────────────────────────────────────────────────────────────
if (Test-Path $OutputPath) {
    Copy-Item $OutputPath "$OutputPath.bak" -Force
    Write-Host "Previous diagram backed up to: architecture-diagram.drawio.bak" -ForegroundColor DarkGray
}

[System.IO.File]::WriteAllText($OutputPath, $xml, [System.Text.Encoding]::UTF8)

$sizeKB = [Math]::Round((Get-Item $OutputPath).Length / 1KB, 1)
Write-Host ""
Write-Host "Done! architecture-diagram.drawio written ($sizeKB KB)" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Open architecture-diagram.drawio in VS Code (Draw.io extension)" -ForegroundColor White
Write-Host "  2. Icons are fully embedded — no internet required" -ForegroundColor White
Write-Host "  3. git add architecture-diagram.drawio" -ForegroundColor White
