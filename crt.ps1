#!/usr/bin/env pwsh
# crt.ps1 — cd into the CRT Patient Analytics project and launch Claude Code
# Usage: .\crt.ps1   (or just `crt` if on PATH)

Set-Location "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\CRT Patient Analytics\crt-patient-analytics"
claude --dangerously-skip-permissions @args
