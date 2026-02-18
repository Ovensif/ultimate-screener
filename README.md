# MEXC Alert 10 Bot

Bot that sends you a **Top 10 altcoin list** via Telegram when the list changes. Coins are selected from a liquid watchlist and must have:

1. **RSI in strong or weak zone** (RSI ≥ 65 or RSI ≤ 35)
2. **Confirmed sweep of swing high/low on 4H** (liquidity sweep)

The list is not “top 10 by market cap”—it’s the top 10 that meet these criteria. You get a **single Telegram message** only when the list composition changes (coins in/out).

## Features

- **Dynamic watchlist**: Candidate pool by volume, volatility, and trend (refreshed on an interval).
- **4H-only screening**: RSI strong/weak + confirmed sweep of swing high/low on 4H.
- **Telegram on change only**: One message when the Top 10 list changes (Out / In / current list).
- **Configurable**: Intervals, RSI thresholds, and list size via `.env`.

## Requirements

- Python 3.9+
- MEXC (ccxt), Telegram Bot Token and Chat ID
- `pandas-ta` recommended for full technical analysis (RSI, structure, etc.); fallbacks exist if not installed.

## Install

```bash
cd ultimate-screener
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
```

Copy and edit environment:

```bash
copy config\.env.example .env
# Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env
```

## Run

From project root:

```bash
python main.py
```
or
```bash
python src/main.py
```

You get a Telegram message: "Scanner started, monitoring N coins". After that, you only receive a message when the **Top 10 list changes** (Out / In / current list).

One-shot (build list once and exit, e.g. for cron):

```bash
python main.py --once
```

## Configuration

See `config/.env.example`. Key variables:

| Variable | Description | Default |
|----------|-------------|---------|
| TELEGRAM_BOT_TOKEN | Bot token from @BotFather | required |
| TELEGRAM_CHAT_ID | Chat or group ID for alerts | required |
| WATCHLIST_REFRESH | Seconds between watchlist refresh | 3600 |
| ALERT10_INTERVAL | Seconds between Top 10 list runs | 3600 |
| ALERT10_MAX_COINS | Size of the list sent | 10 |
| ALERT10_RSI_STRONG | RSI ≥ this = strong zone | 65 |
| ALERT10_RSI_WEAK | RSI ≤ this = weak zone | 35 |
| MIN_VOLUME | Min 24h volume (USD) for watchlist | 100000000 |
| MAX_COINS | Max symbols in watchlist (candidate pool) | 20 |

## How often it runs

When run as a service (e.g. systemd on a VPS):

- **Watchlist** is refreshed every `WATCHLIST_REFRESH` seconds (default: 1 hour).
- **Alert 10** (build list, compare, send Telegram if changed) runs every `ALERT10_INTERVAL` seconds (default: 1 hour), plus once at startup.

So by default the bot evaluates the Top 10 list **every hour**. Set `ALERT10_INTERVAL` and `WATCHLIST_REFRESH` in `.env` to change that (values in seconds).

## Project structure

```
ultimate-screener/
├── src/
│   ├── main.py              # Orchestrator and scheduler
│   ├── config.py            # Settings from .env
│   ├── data_fetcher.py      # MEXC OHLCV, ticker, markets
│   ├── market_analyzer.py   # Structure, volume, indicators, sweep
│   ├── alert10_screener.py  # Top 10: RSI + 4H sweep filter
│   ├── telegram_bot.py      # Startup + Alert 10 list-change messages
│   └── watchlist_manager.py # Candidate pool for screener
├── config/
│   ├── .env.example
│   └── blacklist.txt
├── data/                    # Cache, alert10_list.json
├── logs/                    # screener.log
└── tests/
    └── run_all_tests.py     # MEXC, Telegram, TA, Alert10 screener
```

## Tests

From project root:

```bash
python tests/run_all_tests.py
```

Runs: MEXC connection, Telegram (if token set), technical analysis (market_analyzer), Alert10 screener.

## Documentation

- [API.md](API.md) – MEXC API usage and rate limits
- [DEPLOYMENT.md](DEPLOYMENT.md) – Run 24/7 (systemd, cron, Windows)
- [FAQ.md](FAQ.md) – Troubleshooting

## Disclaimer

This tool is for education and research. Not financial advice.
