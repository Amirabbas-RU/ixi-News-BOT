<p align="center">
  <img src="https://readme-typing-svg.herokuapp.com?font=Fira+Code&weight=700&size=32&duration=3000&pause=1000&color=00D4AA&center=true&vCenter=true&width=600&height=70&lines=ixi+News+BOT;AI-Powered+Telegram+News+Bot;Financial+News+Aggregator" alt="ixi News BOT" />
</p>

<p align="center">
  <b>🤖 A smart Telegram bot that fetches, scores, summarizes, and publishes financial news automatically</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-00D4AA?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/Telegram-Bot-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white" />
  <img src="https://img.shields.io/badge/OpenRouter-AI-FF6B6B?style=for-the-badge&logo=openai&logoColor=white" />
  <img src="https://img.shields.io/badge/RSS-Feeds-FFA500?style=for-the-badge&logo=rss&logoColor=white" />
</p>

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 📡 **Multi-Source RSS** | Fetches news from CNBC, Yahoo Finance, ForexFactory & more |
| 🧠 **AI Summarization** | Uses OpenRouter AI to translate & summarize news into Persian |
| 📊 **Smart Scoring** | Keyword-based impact scoring with configurable weights |
| 🤖 **Telegram Integration** | Auto-posts high-impact news to your Telegram channel |
| 🎛 **Control Panel** | Telegram-based admin panel to manage sources, keywords & settings |
| ⏰ **Scheduled Runs** | Configurable interval for automatic news fetching & posting |
| 🔄 **Duplicate Detection** | Prevents re-sending the same news within a day |
| 🐳 **Standalone Build** | PyInstaller support for running as `.exe` without Python |

---

## 📰 Supported Sources

| Source | Type | Status |
|--------|------|--------|
| CNBC | RSS Feed | ✅ Active |
| Yahoo Finance | RSS Feed | ✅ Active |
| ForexFactory | Economic Calendar | ✅ Active |
| Reuters | RSS Feed | 🔜 Ready (configurable) |
| Investing.com | RSS Feed | 🔜 Ready (configurable) |

---

## 🚀 Quick Start

### 1. Clone & Install
```bash
git clone https://github.com/AmirabbasRouintan/ixi-News-BOT.git
cd ixi-News-BOT
pip install -r requirements.txt
```

### 2. Configure `main.env`
```env
# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHANNEL_ID=@your_channel

# OpenRouter AI
OPENROUTER_API_KEY=your_api_key
OPENROUTER_MODEL=openai/gpt-4o-mini

# RSS Feeds (fill URLs)
CNBC_RSS_URL=https://search.cnbc.com/rs/...
YAHOO_RSS_URL=https://finance.yahoo.com/...
```

### 3. Run
```bash
python main.py
```

### 4. Control Panel (optional)
Set `BOT_PANEL=true` in `main.env` to enable the Telegram control panel for managing keywords, sources & settings on the fly.

---

## ⚙️ Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `NEWS_UPDATE_INTERVAL_MINUTES` | Fetch interval | `60` |
| `MIN_IMPACT_SCORE` | Minimum score to publish | `7` |
| `MAX_POSTS_PER_DAY` | Daily post limit | `10` |
| `HIGH_IMPACT_KEYWORDS` | JSON keyword→score map | `{"Fed": 5, ...}` |
| `SOURCE_SCORE` | JSON source→score map | `{"CNBC": 4, ...}` |

---

## 🧠 Scoring System

```
News Score = Keyword Match Score + Source Score + Impact Bonus
```

| Keyword | Score |
|---------|-------|
| Fed / Interest Rate / CPI | 5 |
| Inflation / War / Bitcoin / ECB | 4 |
| Oil / Bank / NASDAQ / S&P 500 | 3 |
| Market / Economy / Gold / USD | 2 |

---

## 🛠 Built With

- **[python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)** — Telegram Bot API
- **[feedparser](https://github.com/kurtmckee/feedparser)** — RSS parsing
- **[OpenAI Python SDK](https://github.com/openai/openai-python)** — OpenRouter API integration
- **[python-dotenv](https://github.com/theskumar/python-dotenv)** — Environment management
- **[PyInstaller](https://github.com/pyinstaller/pyinstaller)** — Standalone executable build

---

## 📄 License

This project is open source and available under the MIT License.

---

<p align="center">
  <img src="https://readme-typing-svg.herokuapp.com?font=Fira+Code&weight=600&size=18&duration=4000&pause=500&color=FFD700&center=true&vCenter=true&width=500&lines=%E2%AD%90+If+you+like+this+project%2C+give+it+a+star!;%F0%9F%92%AA+I+have+done+a+lot+of+hours+on+this+project;%F0%9F%99%8F+Your+support+keeps+me+motivated!" alt="Star Banner" />
</p>

<p align="center">
  <b>⭐ If you find this project useful, please give it a star on GitHub! ⭐</b>
  <br/>
  <sub>I have spent countless hours building & improving this bot. Your support means the world to me 🙏</sub>
</p>

<p align="center">
  <a href="https://github.com/AmirabbasRouintan/ixi-News-BOT">
    <img src="https://img.shields.io/github/stars/AmirabbasRouintan/ixi-News-BOT?style=for-the-badge&logo=github&color=FFD700" alt="GitHub Stars" />
  </a>
</p>
