# Dash AI

An AI-powered IoT analytics platform that connects to your ThingsBoard instance. Dash AI instantly fetches your device data and automatically generates beautiful, actionable insights using a 4-agent LLM pipeline.

## Features

- **Google-like AI Native UI** — Modern, clean design with landing and auth pages
- **Zero-config Connect** — Sign in with email + password or paste a JWT token
- **Smart Device Picker** — Select from an interactive dropdown
- **4-agent AI Pipeline**:
  1. **DataFetcher** — Authenticates and retrieves telemetry & attributes
  2. **DataCleaner** — Cleans, computes stats, and finds patterns in IoT data
  3. **VizRecommender** — AI curates the best charts and visualization methods
  4. **DashboardBuilder** — Assembles the final Dash AI view
- **Fallback Mode** — Smart default charts if AI generation is unavailable
- **Secure by Design** — AI API keys are handled server-side
- **User Authentication** — PostgreSQL registry (default for production via Neon) or local SQLite fallback to save your setup

## Project Structure

```
25th TB/
├── app.py                  # Entry point — Flask app + run
├── config.py               # Env loading, API keys, constants
├── database.py             # SQLite helpers (users, sessions, agent_logs)
├── pipeline.py             # AgentState + run_pipeline orchestrator
├── routes.py               # Flask Blueprint (all HTTP endpoints)
├── agents/
│   ├── data_fetcher.py     # Agent 1 — ThingsBoard API client
│   ├── data_cleaner.py     # Agent 2 — data analysis & pattern detection
│   ├── viz_recommender.py  # Agent 3 — AI chart selection
│   └── dashboard_builder.py# Agent 4 — chart.js config builder
├── templates/
│   ├── base.html           # Main UI shell (CSS, fonts, topbar)
│   ├── landing.html        # Public homepage
│   ├── login.html          # User sign in page
│   ├── register.html       # User signup page
│   └── dashboard.html      # Main app / Connect / Visualization views
├── .env                    # Secrets — NOT committed to git
├── .gitignore
└── requirements.txt
```

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Add your secrets to .env
#    Get Groq key at https://console.groq.com
#    Get Neon DB url at https://neon.tech
GROQ_API_KEY=gsk_...
DATABASE_URL=postgres://user:pass@ep-hostname.neon.tech/neondb?sslmode=require

# 3. Run the server
python app.py
# → http://localhost:5050
```

## Supported ThingsBoard Setups

| Option | URL |
|---|---|
| ThingsBoard Cloud | `https://thingsboard.cloud` |
| Demo Server | `https://demo.thingsboard.io` (user: `tenant@thingsboard.org` / `tenant`) |
| Self-hosted | Your own server URL |
| PE / Edge | Your PE or Edge deployment URL |

## Requirements

- Python 3.9+
- Flask ≥ 3.0
- requests ≥ 2.31
- A ThingsBoard account (free tier works)
- A Groq API key (optional — fallback charts work without it)
