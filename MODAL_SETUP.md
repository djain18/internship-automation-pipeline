# Modal Deployment Setup

## Quick Start

### Step 1: Install Modal
```bash
pip install modal
```

### Step 2: Authenticate
```bash
modal token new
```
This opens browser for login. Create account if needed (free).

### Step 3: Create Secrets
```bash
modal secret create internship-secrets \
  APIFY_API_TOKEN=your_apify_api_token_here \
  FIRECRAWL_API_KEY=your_firecrawl_api_key_here \
  BROWSERLESS_API_KEY=your_browserless_api_key_here \
  ZYTE_API_KEY=your_zyte_api_key_here \
  GOOGLE_SHEET_ID=YOUR_SHEET_ID_HERE
```

For Google credentials (multi-line JSON), use the Modal dashboard:
1. Go to https://modal.com/secrets
2. Edit `internship-secrets`
3. Add `GOOGLE_CREDENTIALS_JSON` with contents of credentials.json
4. Add `GOOGLE_TOKEN_JSON` with contents of token.json

### Step 4: Deploy
```bash
modal deploy modal_app.py
```

### Step 5: Test
```bash
# Manual trigger via webhook
curl https://YOUR_USERNAME--internship-pipeline-run-now.modal.run

# Or run directly
modal run modal_app.py
```

---

## Scheduled Runs

The app is configured to run at:
- **10:00 AM IST** (4:30 UTC) - Morning run
- **6:00 PM IST** (12:30 UTC) - Evening run

To change times, edit `modal_app.py`:
```python
@app.function(schedule=modal.Cron("30 4 * * *"))  # Change this
```

Cron format: `minute hour day month weekday`

---

## Webhook Endpoints

| Endpoint | Purpose |
|----------|---------|
| `/run-now` | Manual full pipeline run |
| `/run-now?source=linkedin` | Quick run (LinkedIn only) |
| `/health` | Health check |

Full URL format: `https://YOUR_USERNAME--internship-pipeline-ENDPOINT.modal.run`

---

## Monitoring

1. **Modal Dashboard:** https://modal.com/apps
   - View logs
   - See run history
   - Monitor costs

2. **Google Sheet:** Results appear after each run

---

## Cost Estimate

| Component | Cost |
|-----------|------|
| Modal compute | ~$0.10-0.50/day |
| Apify (free tier) | $0 |
| Firecrawl (free tier) | $0 |
| **Total** | **~$2-5/month** |

---

## Troubleshooting

### "Secret not found"
```bash
modal secret list  # Check if exists
modal secret create internship-secrets ...  # Create it
```

### "Script not found"
Ensure you're deploying from the project root directory.

### "Google auth failed"
Re-generate token.json locally, then update the secret.
