# 📊 Market Digest → Telegram

Automatically pulls end-of-day statistics from Yahoo Finance for **US, Korean, Japanese, and Indian markets** and sends a structured summary to a Telegram chat after each market closes.

---

## Features

| Section | Markets |
|---|---|
| 📦 Top 20 by Volume | US, KR, JP, IN |
| 📈 Top 20 Gainers (% change) | US, KR, JP, IN |
| 📉 Top 20 Losers (% change) | US, KR, JP, IN |
| 💰 Top 20 by Market Cap | US, KR, JP, IN |
| ⚡ Top 20 Options Open Interest | US only |

---

## Schedule

| Workflow | Trigger (UTC) | Local Close |
|---|---|---|
| 🇺🇸 US | 21:30 UTC Mon–Fri | 4:00 PM ET |
| 🇰🇷 Korea | 07:00 UTC Mon–Fri | 3:30 PM KST |
| 🇯🇵 Japan | 07:00 UTC Mon–Fri | 3:30 PM JST |
| 🇮🇳 India | 10:30 UTC Mon–Fri | 3:30 PM IST |

---

## Setup Guide

### 1. Create a Telegram Bot

1. Open Telegram → search for **@BotFather**
2. Send `/newbot`, follow prompts
3. Copy the **Bot Token** (looks like `1234567890:AAFxxxx...`)
4. Add your bot to the target group/channel, then get the **Chat ID**:
   - Send a test message in the group
   - Visit: `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
   - Find `"chat": {"id": -1001234567890}` — that number is your Chat ID

> ⚠️ **Never share your Bot Token publicly or in code.**

### 2. Fork this Repository

Click **Fork** on GitHub. Your fork will run the workflows under your own GitHub account's free Actions minutes.

### 3. Add GitHub Secrets

Go to your forked repo → **Settings → Secrets and variables → Actions → New repository secret**

| Secret name | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Your bot token from BotFather |
| `TELEGRAM_CHAT_ID` | Your chat/channel ID (can be negative for groups) |

> ⚠️ **Do not paste these values anywhere other than the GitHub Secrets UI.**

### 4. Enable GitHub Actions

Go to **Actions** tab → click **"I understand my workflows, go ahead and enable them"** if prompted.

You can also trigger any workflow manually via **Actions → [workflow name] → Run workflow**.

---

## Project Structure

```
.
├── .github/
│   └── workflows/
│       ├── us_digest.yml       # US: 21:30 UTC
│       ├── kr_digest.yml       # Korea: 07:00 UTC
│       ├── jp_digest.yml       # Japan: 07:00 UTC
│       └── in_digest.yml       # India: 10:30 UTC
├── src/
│   ├── main.py                 # Orchestrator (CLI: --market us|kr|jp|in)
│   ├── fetcher.py              # Ticker discovery + OHLCV + market cap + options OI
│   ├── screener.py             # Top-N ranking logic
│   ├── formatter.py            # Telegram HTML message builder
│   └── telegram_bot.py         # Telegram Bot API sender
├── requirements.txt
└── README.md
```

---

## Data Sources

| Data | Source | Notes |
|---|---|---|
| US tickers | NASDAQ Trader FTP | All NYSE + NASDAQ (~7,500–8,000 clean symbols) |
| KR tickers | pykrx (KRX official) | Full KOSPI + KOSDAQ universe |
| JP tickers | Wikipedia (Nikkei 225) | 225 constituents with .T suffix |
| IN tickers | NSE archives (NIFTY 500) | 500 constituents with .NS suffix |
| OHLCV + market cap | Yahoo Finance (yfinance) | Free, no API key required |
| Options OI | Yahoo Finance (yfinance) | US only; nearest 3 expiries |

---

## Runtime Estimates (GitHub Actions)

| Market | Tickers | Est. Runtime |
|---|---|---|
| US (with options OI) | ~7,500 | 90–150 min |
| Korea | ~2,500+ | 20–40 min |
| Japan | 225 | 5–10 min |
| India | 500 | 10–20 min |

GitHub Actions free tier: **2,000 min/month** for private repos, unlimited for public repos.

---

## Limitations

- **Options OI**: Yahoo Finance options data only covers US-listed stocks reliably. Asian markets are excluded from this section.
- **Market holidays**: The script detects the latest available trading session automatically — if a holiday falls on a weekday, it will report the previous session's data.
- **Yahoo Finance rate limits**: Very occasionally, bulk downloads may get throttled. The script uses 0.5s delays between chunks and retries gracefully.
- **Korean market**: pykrx fetches all KOSPI + KOSDAQ tickers but yfinance coverage of smaller KOSDAQ stocks may be incomplete.
