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
- Optional: [Formspree](https://formspree.io) or similar for form handling

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

### 4. Set Up Form Handling

The signup form needs a backend to receive submissions. Options:

#### Option A: Formspree (Simplest)

1. Create account at [formspree.io](https://formspree.io)
2. Create a new form
3. Copy your form ID
4. Update `index.html`: replace `YOUR_FORM_ID` in the form action

When you receive form submissions, manually run:
```bash
python signup.py "user@email.com" "sydney"
```

#### Option B: Serverless Function (Automated)

Deploy `api/handlers.py` to Vercel, Netlify, or Cloudflare Workers. Update the `API_ENDPOINT` in `confirm.html` and `unsubscribe.html`.

### 5. Test It

```bash
# Install dependencies
pip install -r requirements.txt

# Run the scraper (dry run without RESEND_API_KEY)
python main.py

# Test a signup
python signup.py "test@example.com" "sydney"
```

---

## File Structure

```
fuel-alert/
├── main.py                 # Scraper and email sender
├── signup.py               # Handles new subscriptions
├── requirements.txt        # Python dependencies
├── index.html              # Main website with dashboard
├── confirm.html            # Subscription confirmation page
├── unsubscribe.html        # Unsubscribe page
├── data/
│   ├── state.json          # Current price phase per city
│   └── subscribers.json    # Email list by city
├── api/
│   └── handlers.py         # Serverless function handlers
└── .github/
    └── workflows/
        └── check-prices.yml  # Scheduled GitHub Action
```

---

## Data Storage

**Minimal by design:**

- `subscribers.json`: Email addresses grouped by city
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

- No analytics or tracking pixels
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
