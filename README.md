# Telegram News Bot 🤖📰

A Persian financial news bot that fetches RSS feeds and economic calendar events, summarizes them via AI (OpenRouter), and posts to a Telegram channel.

## Features

- **RSS News Sources** — CNBC, Yahoo Finance (extensible via `BaseRSSSource`)
- **ForexFactory Calendar** — Fetches economic events, sends pre-alerts
- **Keyword Scoring** — 130+ keywords with configurable impact weights
- **AI Summarization** — Translates & summarizes news to Persian via DeepSeek V4 Flash
- **Persian Output** — All posts are in Persian with market impact analysis
- **Admin Control Panel** — Optional Telegram bot to edit sources, model, keywords, and scores live

## Impact-Based Alert Windows ⏰

Pre-alerts are sent based on event impact level:

| Impact | Icon | Alert Before Release |
|--------|------|---------------------|
| **High** | 🔴 | **15 minutes** |
| **Medium** | 🟡 | **10 minutes** |
| **Low** | 🟢 | **5 minutes** |

Each alert includes:
- Event title (Persian translation via AI, falls back to English on error)
- Country and impact level
- Forecast vs previous value
- Countdown minutes

## Setup

1. Copy `main.env` and fill in your tokens:
   - `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHANNEL_ID`
   - `OPENROUTER_API_KEY` + `OPENROUTER_MODEL`
   - `FOREXFACTORY_CALENDAR_URL`

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run:
   ```bash
   python main.py
   ```

## Single Instance Lock

The bot creates `bot.lock` on startup to prevent multiple instances. The lock file is auto-removed on exit.
