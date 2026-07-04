#!/usr/bin/env pwsh
# excel.ps1 — cd into the Excel Options Chain Import project and launch Claude Code
# Usage: .\excel.ps1   (or just `excel` if on PATH)

Set-Location "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Excel Options Chain Import"
claude --dangerously-skip-permissions @args
