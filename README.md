# Cold Email Outreach System

Local web app for lead generation and cold email outreach targeting tradespeople. Scrapes leads from multiple sources, scores them by likelihood to convert, and manages a 3-email drip sequence via Gmail.

## Stack
- **Backend**: Flask, SQLite, Google APIs (Gmail + Sheets)
- **Frontend**: Jinja2 templates, Tailwind CSS (CDN), vanilla JS
- **Scrapers**: requests + BeautifulSoup with rate limiting + UA rotation

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Google API credentials (optional)
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project and enable **Gmail API** and **Google Sheets API**
3. Create OAuth 2.0 credentials (Desktop app)
4. Download the JSON and save as `data/credentials.json`

### 3. Run setup wizard
```bash
python setup_wizard.py
```
Authenticates Gmail and Sheets (or skip for later), creates the database, and copies `.env.example` to `.env`.

### 4. Configure .env
Edit `.env` with your settings:
- `HUNTER_API_KEY` — optional, for email finding via Hunter.io
- `SEND_FROM_EMAIL` — your Gmail address
- `DAILY_SEND_LIMIT` — max emails per day (default 30)

### 5. Start the app
```bash
python backend/app.py
```
Open http://localhost:5000

## Features

### Lead Scraping
- Google Maps local search
- Yelp business search
- State license databases (CA CSLB, TX TDLR, FL DBPR)
- Email extraction from websites + Hunter.io

### Lead Scoring
Automatically scores leads to prioritize solo operators and micro-businesses:

| Signal | Points |
|--------|--------|
| No website or basic/outdated website | +20 |
| Modern website | -10 |
| Google reviews 10-100 | +15 |
| Google reviews 1-9 | +10 |
| Google reviews 100-300 | +5 |
| Google reviews 300+ | -15 |
| Single location | +10 |
| Multiple locations | -20 |
| Owner name visible | +15 |
| Generic/owner email | +10 |
| Gatekeeper language | -15 |
| No online booking system | +10 |
| Has scheduling software | -10 |

**Tiers:** Hot (50+), Warm (25-49), Cool (0-24), Skip (below 0)

### Email Outreach
- 3-email drip sequences with configurable delays
- 3 template styles: intro, referral, value-first
- Review/edit queue filtered by lead tier
- Gmail API integration with daily send limits
- Sent email tracking

### Lead Management
- Filterable/searchable lead table sorted by score
- Tier badges (Hot/Warm/Cool/Skip) with color coding
- Status tracking (new → contacted → replied → converted)
- Manual score override per lead
- Google Sheets bidirectional sync
- Bulk operations (generate emails, delete)

## Pages
| Page | URL | Description |
|------|-----|-------------|
| Dashboard | `/` | Stats overview + tier breakdown |
| Scrape | `/scrape` | Run scrapers with progress + tier summary |
| Leads | `/leads` | Lead table with tier/score columns + filters |
| Queue | `/queue` | Email review (Hot/Warm by default) |
| Sent | `/sent` | Sent email tracking |
| Settings | `/settings` | API connections + email config |

## Project Structure
```
backend/
  app.py              # Flask routes + API
  database.py         # SQLite schema + CRUD
  email_generator.py  # 3-email template engine
  gmail_service.py    # Gmail API OAuth2 send
  sheets_service.py   # Google Sheets sync
  lead_scorer.py      # Lead scoring engine
  scrapers/
    google_maps.py    # Google local search
    yelp.py           # Yelp business search
    license_dbs.py    # CA/TX/FL license DBs
    email_finder.py   # Website email extraction + Hunter.io
frontend/
  templates/          # Jinja2 templates
  static/             # JS + CSS
```
