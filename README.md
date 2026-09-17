# ⛽ Fuel Alert

**One email when petrol prices hit the bottom. That's it.**

A privacy-first alert system that monitors Australian fuel price cycles and notifies subscribers when it's time to fill up.

*Inspired by "How They Get You" by Chris Kohler*

---

## How It Works

1. The ACCC publishes [petrol price cycle data](https://www.accc.gov.au/consumers/petrol-and-fuel/petrol-price-cycles-in-the-5-largest-cities) for Sydney, Melbourne, Brisbane, Adelaide, and Perth
2. This system scrapes that data 3x weekly (Mon/Wed/Fri)
3. When a city transitions from WAIT → BUY (prices at bottom), subscribers get one email
4. The email says: "Fill up within 24 hours" — that's it

**No spam. No weekly digests. No tracking.**

---

## Setup

### Prerequisites

- GitHub account
- [Resend](https://resend.com) account (free tier: 3,000 emails/month)
- [Cloudflare](https://cloudflare.com) account (Pages for the site, Workers + KV for signups)

### 1. Fork/Clone This Repo

```bash
git clone https://github.com/yourusername/fuel-alert.git
cd fuel-alert
```

### 2. Set Up GitHub Secrets

Go to your repo → Settings → Secrets and variables → Actions → New repository secret

Add these secrets:

| Name | Description |
|------|-------------|
| `RESEND_API_KEY` | Your Resend API key |
| `FROM_EMAIL` | Sender email (must be verified in Resend) |
| `SITE_URL` | Your GitHub Pages URL (e.g., `https://yourusername.github.io/fuel-alert`) |
| `SECRET_KEY` | Random string for token generation (use `openssl rand -hex 32`) |

### 3. Enable GitHub Pages

1. Go to repo Settings → Pages
2. Source: "Deploy from a branch"
3. Branch: `main`, folder: `/ (root)`
4. Save

Your site will be live at `https://yourusername.github.io/fuel-alert`

### 4. Deploy the Signup Worker

Signups, confirmations and unsubscribes are handled by a Cloudflare Worker in `worker/`, which stores confirmed subscribers in Workers KV (so no email addresses live in this repo).

```bash
cd worker
npx wrangler login
npx wrangler kv namespace create SUBSCRIBERS   # paste the id into wrangler.toml
npx wrangler secret put RESEND_API_KEY
npx wrangler secret put SECRET_KEY    # same value as the GitHub secret
npx wrangler secret put ADMIN_TOKEN   # same value as the GitHub secret
npx wrangler deploy
```

Add `ADMIN_TOKEN` (and optionally `TEST_EMAIL`) as GitHub secrets too.

### 5. Test It

```bash
# Install dependencies
pip install -r requirements.txt

# Run the scraper (dry run without RESEND_API_KEY)
python main.py

# Simulate a price drop end to end (emails only the TEST_EMAIL secret):
# Actions → Fuel Price Check → Run workflow → pick a city
```

---

## File Structure

```
fuel-alert/
├── main.py                 # Scraper and email sender
├── requirements.txt        # Pinned Python dependencies
├── index.html              # Main website with dashboard
├── confirm.html            # Subscription confirmation page
├── unsubscribe.html        # Unsubscribe page
├── _headers                # Security headers (Cloudflare Pages)
├── data/
│   ├── state.json          # Current price phase per city
│   └── last_run.txt        # Last scheduled run (keeps the schedule active)
├── worker/
│   ├── wrangler.toml       # Worker config (KV, rate limit)
│   └── src/index.js        # Signup, confirm, unsubscribe, subscriber list
└── .github/
    └── workflows/
        └── check-prices.yml  # Scheduled GitHub Action
```

---

## Data Storage

**Minimal by design:**

- Workers KV: email + city for confirmed subscribers (not in this repo)
- `state.json`: Last known price phase per city (BUY/WAIT)

That's it. No names, no timestamps, no IP addresses, no tracking.

---

## Price Classification Logic

The ACCC uses consistent language in their buying tips:

| ACCC Says | We Classify As |
|-----------|----------------|
| "lowest point", "good time to buy" | BUY |
| "decreasing", "may decrease further" | WAIT |
| "high point", "increasing" | WAIT |

We only email on **WAIT → BUY** transitions.

---

## Customization

### Change Notification Frequency

Edit `.github/workflows/check-prices.yml`:

```yaml
schedule:
  # Current: Mon/Wed/Fri at 12:30pm AEST
  - cron: '30 2 * * 1,3,5'
  
  # Daily at 7am AEST:
  # - cron: '0 21 * * *'
```

### Email Template

Edit the `send_buy_alert()` function in `main.py`.

### Add More Cities

The ACCC only provides cycle data for the 5 largest cities. Regional areas don't have predictable cycles.

---

## Privacy

- No analytics scripts, cookies or tracking pixels; the homepage only sends an anonymous "page viewed" ping so daily visit totals can be counted
- No cookies (except essential session cookies if using serverless functions)
- No third-party scripts
- Email + city is the only data stored
- One-click unsubscribe in every email

---

## License

MIT — do whatever you want with it.

---

## Credits

- Data source: [ACCC Petrol Price Cycles](https://www.accc.gov.au/consumers/petrol-and-fuel/petrol-price-cycles-in-the-5-largest-cities)
- Inspiration: *"How They Get You"* by Chris Kohler
