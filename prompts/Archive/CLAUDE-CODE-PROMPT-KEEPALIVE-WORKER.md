# Claude Code Prompt: Deploy Cloudflare Worker Keep-Alive Ping

**Jira:** OTA-453, TMTC-10
**Scope:** Create and deploy a Cloudflare Worker that pings OTA and TMTC every 14 minutes to prevent Azure Free tier cold starts.

---

## Prerequisites

```bash
# Fetch Cloudflare API token from shared Key Vault
export CLOUDFLARE_API_TOKEN=$(az keyvault secret show \
  --vault-name kv-tmtc-shared \
  --name cloudflare-api \
  --query value -o tsv)
```

Confirm the token is set:
```bash
echo $CLOUDFLARE_API_TOKEN | head -c 10
```

---

## Step 1: Scaffold the Worker

```bash
cd ~/
mkdir keep-alive-ping && cd keep-alive-ping
npm init -y
npm install wrangler --save-dev
```

## Step 2: Create `wrangler.toml`

```toml
name = "keep-alive-ping"
main = "src/index.js"
compatibility_date = "2024-01-01"

[triggers]
crons = ["*/14 * * * *"]
```

## Step 3: Create `src/index.js`

```js
const TARGETS = [
  {
    name: 'OTA API',
    url: 'https://options-analyzer-api.azurewebsites.net/api/v1/evaluate/health',
  },
  {
    name: 'TMTC Website',
    url: 'https://www.tmtctech.ai/',
  },
];

export default {
  async scheduled(event, env, ctx) {
    const results = await Promise.allSettled(
      TARGETS.map(async (target) => {
        const start = Date.now();
        try {
          const res = await fetch(target.url, {
            method: 'GET',
            headers: { 'User-Agent': 'CloudflareWorker-KeepAlive/1.0' },
            signal: AbortSignal.timeout(15000),
          });
          const elapsed = Date.now() - start;
          console.log(`OK ${target.name}: ${res.status} (${elapsed}ms)`);
          return { name: target.name, status: res.status, elapsed };
        } catch (err) {
          const elapsed = Date.now() - start;
          console.error(`FAIL ${target.name}: ${err.message} (${elapsed}ms)`);
          return { name: target.name, error: err.message, elapsed };
        }
      })
    );
  },
};
```

## Step 4: Deploy

```bash
npx wrangler deploy
```

## Step 5: Verify

```bash
# Watch live logs (wait up to 14 min for next cron tick, or trigger manually)
npx wrangler tail
```

To test locally before deploying:
```bash
npx wrangler dev
# In another terminal:
curl "http://localhost:8787/__scheduled?cron=*/14+*+*+*+*"
```

---

## Acceptance Criteria

- [ ] Worker deploys successfully to Cloudflare (no errors from `wrangler deploy`)
- [ ] `wrangler tail` shows logs for both OTA API and TMTC Website pings
- [ ] Cron is registered as `*/14 * * * *` (visible in Cloudflare dashboard under Workers → Triggers)
- [ ] OTA health endpoint returns 200
- [ ] TMTC root returns 200

## Notes

- This is a standalone project — NOT inside the options-analyzer repo.
- No git repo needed. The worker lives on Cloudflare only.
- If `CLOUDFLARE_API_TOKEN` is not set, `wrangler deploy` will fail with an auth error. Re-run the `az keyvault` command from Prerequisites.
- Free tier: 100K invocations/day. This uses ~103/day. No cost.
