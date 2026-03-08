# Whitelist current public IP in Azure SQL firewall for 24 hours.
# Run this before starting the dev server when working from a new location.
#
# WHY: Azure SQL only allows connections from known IPs. When your IP changes
# (new network, VPN on/off), you get a connection timeout. This script detects
# your current IP, names the rule with today's date so you can see when it was
# added, and replaces any existing "LocalDev" rule from a prior session.

Set-Location "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"

$ErrorActionPreference = "Stop"

$resourceGroup = "options-analyzer-rg"
$server        = "options-analyzer-sql"

# Get current public IP
Write-Host "Detecting current public IP..." -ForegroundColor Cyan
$ip = (Invoke-RestMethod -Uri "https://api.ipify.org" -UseBasicParsing)
Write-Host "  Your IP: $ip" -ForegroundColor Yellow

# Rule name includes date so history is visible in Azure portal
$ruleName = "LocalDev-$(Get-Date -Format 'yyyyMMdd')"

# Remove any existing LocalDev rules from previous sessions (keeps it tidy)
$existing = az sql server firewall-rule list `
    --server $server `
    --resource-group $resourceGroup `
    --query "[?starts_with(name, 'LocalDev')].name" `
    -o tsv 2>$null

foreach ($old in ($existing -split "`n" | Where-Object { $_ -and $_ -ne $ruleName })) {
    Write-Host "  Removing old rule: $old" -ForegroundColor DarkGray
    az sql server firewall-rule delete `
        --server $server `
        --resource-group $resourceGroup `
        --name $old | Out-Null
}

# Create (or update) today's rule
Write-Host "Setting firewall rule '$ruleName' for $ip..." -ForegroundColor Cyan
az sql server firewall-rule create `
    --server $server `
    --resource-group $resourceGroup `
    --name $ruleName `
    --start-ip-address $ip `
    --end-ip-address $ip | Out-Null

Write-Host "Done. Azure SQL will accept connections from $ip." -ForegroundColor Green
Write-Host "Note: Azure SQL firewall rules don't expire automatically." -ForegroundColor DarkGray
Write-Host "      Run this script again whenever your IP changes." -ForegroundColor DarkGray
