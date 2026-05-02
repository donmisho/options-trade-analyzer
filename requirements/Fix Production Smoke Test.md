# Task: Fix prod smoke test — wrong hostname AND remove Schwab check

Two bugs in the prod smoke test step that was just added to deploy-to-prod.yml:

1. The PROD_URL hostname is wrong. The actual prod App Service hostname includes a regional uniqueness suffix.
2. The Schwab check is too strict for current prod state. Schwab is showing as disconnected in prod (likely related to a known Key Vault Forbidden issue with token refresh — separate Story to investigate). Until that's resolved, the smoke test should only validate database connectivity.

## What to do

### Step 1: Verify current state

```bash
cat .github/workflows/deploy-to-prod.yml
```

Confirm the smoke test step uses `PROD_URL: "https://options-analyzer-api.azurewebsites.net"` and a check that includes both `database.status` and `schwab.status`. If different, stop and report.

### Step 2: Make two changes to the smoke test step

**Change 1:** Update the `PROD_URL` value:
- Old: `https://options-analyzer-api.azurewebsites.net`
- New: `https://options-analyzer-api-d7aqhsdmd6f2anbc.centralus-01.azurewebsites.net`

**Change 2:** Remove the Schwab check. The validation should only check that `database.status == connected`. Replace the existing `if` condition block with this:

```bash
            if [ "$http_code" = "200" ] && echo "$body" | grep -q '"database":{"status":"connected"'; then
```

Do not change anything else in the step. Do not change the URL anywhere else. Do not modify any other file.

### Step 3: Validate the YAML

```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/deploy-to-prod.yml'))"
```

If error, stop and report.

### Step 4: Show me the diff

```bash
git diff .github/workflows/deploy-to-prod.yml
```

Wait for my approval before committing.

### Step 5: After I approve

```bash
git add .github/workflows/deploy-to-prod.yml
git commit -m "fix: correct prod hostname and relax prod smoke test to DB-only

The actual prod App Service URL includes a regional uniqueness
suffix that I had not accounted for in the previous commit.
Verified via 'az webapp list --resource-group options-analyzer-rg'.

Also removes the schwab.status check from the prod smoke test.
Schwab is currently showing as disconnected in prod due to a
suspected Key Vault Forbidden issue with token refresh (separate
Story to investigate). Until that's resolved, gating prod deploys
on schwab.status would block all deploys. Database connectivity
is the more important gate and remains in place."
git push
```

### Step 6: Stop

Do not trigger any deploy. Do not modify any other files. Do not investigate the Schwab issue. Report completion.