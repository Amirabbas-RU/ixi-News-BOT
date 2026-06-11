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

Copy the example file (`example.env` has full explanations for every variable) and edit it:
```bash
cp example.env main.env
nano main.env
```

All configuration lives in `main.env`. Here's what every section does:

<details>
<summary><b>⏱ Schedule & Thresholds</b></summary>

| Variable | Description | Example |
|----------|-------------|---------|
| `NEWS_UPDATE_INTERVAL_MINUTES` | How often the bot fetches news (in minutes) | `20` |
| `RESET_DATABASE` | Delete DB & start fresh on next run (`true`/`false`) | `false` |
| `MIN_IMPACT_SCORE` | Minimum score required for a news to be published (higher = fewer posts) | `15` |
| `MAX_POSTS_PER_DAY` | Maximum posts sent per day across all sources | `30` |
</details>

<details>
<summary><b>🤖 Telegram Settings</b></summary>

| Variable | Description | Example |
|----------|-------------|---------|
| `TELEGRAM_BOT_TOKEN` | Your bot token from [@BotFather](https://t.me/BotFather) | `"123456:ABC-DEF..."` |
| `TELEGRAM_CHANNEL_ID` | Target channel ID (numeric like `-1001234567890` or `@username`) | `-1000000000000` |
| `ADMIN_TELEGRAM_ID` | Telegram user ID allowed to use the control panel (`0` = disabled) | `0` |
| `BOT_PANEL` | Enable the Telegram admin panel (`true`/`false`) | `false` |
| `BOT_PANEL_BOT_TOKEN` | Separate bot token for the control panel (leave empty to reuse the main bot) | `""` |
</details>

<details>
<summary><b>📡 RSS Feed URLs</b></summary>

| Variable | Source | Example |
|----------|--------|---------|
| `CNBC_RSS_URL` | CNBC News | `https://www.cnbc.com/id/100003114/device/rss/rss.html` |
| `YAHOO_RSS_URL` | Yahoo Finance | `https://finance.yahoo.com/news/rssindex` |
| `REUTERS_RSS_URL` | Reuters World News | `http://feeds.reuters.com/reuters/worldNews` |
| `INVESTING_RSS_URL` | Investing.com | `https://www.investing.com/rss/news_25.rss` |
| `FOREXFACTORY_CALENDAR_URL` | ForexFactory Calendar | `https://nfs.faireconomy.media/ff_calendar_thisweek.xml` |
</details>

<details>
<summary><b>🧠 AI Summarization (OpenRouter)</b></summary>

| Variable | Description | Example |
|----------|-------------|---------|
| `OPENROUTER_API_KEY` | Your API key from [openrouter.ai/keys](https://openrouter.ai/keys) | `"sk-or-v1-..."` |
| `OPENROUTER_MODEL` | AI model for summarization | `"moonshotai/kimi-k2.6:free"` |
| `OPENROUTER_BASE_URL` | API base URL (change only for custom proxy) | `"https://openrouter.ai/api/v1"` |
</details>

<details>
<summary><b>🔑 Keyword Scoring — <code>HIGH_IMPACT_KEYWORDS</code></b></summary>

JSON object mapping keywords to impact scores. When a news title or content matches any keyword, that score is added to the article's total.

```json
{
  "Fed": 5,        // Critical — monetary policy
  "CPI": 5,        // Critical — inflation data
  "War": 5,        // Critical — geopolitical risk
  "Inflation": 4,  // High impact
  "Bitcoin": 4,    // High impact
  "NASDAQ": 4,     // High impact
  "Oil": 3,        // Medium impact
  "Gold": 3,       // Medium impact
  "Iran": 3,       // Medium impact
  "USD": 2,        // Low impact
  "AAPL": 2,       // Stock ticker
  "TSLA": 2        // Stock ticker
}
```

**Score guide:** `5` = critical · `4` = high · `3` = medium · `2` = low
</details>

<details>
<summary><b>📊 Source Scores — <code>SOURCE_SCORE</code></b></summary>

JSON object with base scores for each source. Every article from that source gets this score added automatically.

```json
{
  "Yahoo": 3,
  "CNBC": 3,
  "ForexFactory": 3
}
```
</details>

---

### 3. Run
```bash
python main.py
```

### 4. Control Panel (optional)
Set `BOT_PANEL=true` and `ADMIN_TELEGRAM_ID=your_id` in `main.env` to enable the Telegram control panel — manage sources, keywords, scores, and restart the bot directly from Telegram.

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


<img width="492" height="942" alt="image" src="https://github.com/user-attachments/assets/ee5da64b-2bb0-45dc-b702-ffd338c114f4" />


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
