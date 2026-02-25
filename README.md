# ThingsBoard AI Dashboard

An AI-powered IoT dashboard that connects to any ThingsBoard server, fetches your device data, and automatically generates charts and insights using a 4-agent pipeline.

## Features

- **Zero-config login** — email + password or paste a JWT token
- **Device picker** — select from a dropdown, no UUID copy-pasting
- **4-agent pipeline** (LangGraph-style):
  1. **DataFetcher** — authenticates and fetches telemetry & attributes
  2. **DataCleaner** — classifies, cleans, computes stats, finds patterns
  3. **VizRecommender** — Groq AI selects the best visualisations
  4. **DashboardBuilder** — assembles the final dashboard
- **Fallback mode** — smart default charts if Groq is unavailable
- **Groq key is server-side only** — never exposed to the browser

## Project Structure

```
25th TB/
├── app.py                  # Entry point — Flask app + run
├── config.py               # Env loading, API keys, constants
├── database.py             # SQLite helpers (sessions, agent_logs)
├── pipeline.py             # AgentState + run_pipeline orchestrator
├── routes.py               # Flask Blueprint (all HTTP endpoints)
├── agents/
│   ├── data_fetcher.py     # Agent 1 — ThingsBoard API client
│   ├── data_cleaner.py     # Agent 2 — data analysis & pattern detection
│   ├── viz_recommender.py  # Agent 3 — Groq AI chart selection
│   └── dashboard_builder.py# Agent 4 — chart.js config builder
├── templates/
│   └── index.html          # Single-page UI (CSS + HTML + JS)
├── .env                    # Secrets — NOT committed to git
├── .gitignore
└── requirements.txt
```

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Add your Groq API key to .env
#    Get a free key at https://console.groq.com
GROQ_API_KEY=gsk_...

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
