# MEXC Futures Signal Screener

Professional cryptocurrency futures trading signal screener for MEXC exchange. Scans altcoin USDT perpetuals, applies trend-following breakout/retest and liquidity-sweep logic, and sends high-probability signals via Telegram.

## Features

- **Dynamic watchlist**: Top coins by volume, volatility, and trend strength (refreshed hourly).
- **Multi-timeframe analysis**: 1D trend filter + 4H setup detection (breakout retest, liquidity sweep, trend continuation).
- **Confluence scoring**: Volume, RSI, MACD, support/resistance; only HIGH confidence signals sent (configurable).
- **Risk management**: Min 1:2 R:R, stop capped 2–3%, position sizing for your account.
- **Telegram alerts**: Formatted messages with entry zone, stop, targets, and chart link.
- **Anti-spam**: Max one signal per coin per 4 hours; BTC dump filter (suppress when BTC &lt; -5% 1h).

## Requirements

- Python 3.9+
- MEXC (ccxt), Telegram Bot Token and Chat ID
- `pandas-ta` for full technical context and confluence (RSI, MACD, ADX, EMA, Bollinger Bands, OBV, ATR, Stoch RSI). Built-in fallbacks exist for core indicators if the package cannot be installed on your Python version.

## Install

```bash
cd crypto_futures_screener
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

From project root (`crypto_futures_screener`):

```bash
python src/main.py
```

You should receive a Telegram message: "Scanner started, monitoring N coins". Signals are sent when conditions are met.

One-shot (single scan then exit, e.g. for cron):

```bash
python src/main.py --once
```

## Configuration

See `config/.env.example`. Key variables:

| Variable | Description | Default |
|----------|-------------|---------|
| TELEGRAM_BOT_TOKEN | Bot token from @BotFather | required |
| TELEGRAM_CHAT_ID | Chat or group ID for alerts | required |
| SCAN_INTERVAL | Seconds between scans | 300 |
| WATCHLIST_REFRESH | Seconds between watchlist refresh | 3600 |
| MIN_VOLUME | Min 24h volume (USD) for watchlist | 100000000 |
| MAX_COINS | Max symbols in watchlist | 20 |
| ACCOUNT_SIZE | Account size for position sizing | 200 |
| RISK_PER_TRADE | Risk % per trade | 2 |
| MIN_RR_RATIO | Minimum risk:reward | 2.0 |
| CONFIDENCE_THRESHOLD | HIGH or MEDIUM | HIGH |

## Project structure

```
crypto_futures_screener/
├── src/
│   ├── main.py           # Orchestrator and scheduler
│   ├── config.py          # Settings from .env
│   ├── data_fetcher.py    # MEXC OHLCV, ticker, markets
│   ├── market_analyzer.py # Structure, volume, indicators
│   ├── signal_generator.py# Setup and confluence logic
│   ├── telegram_bot.py    # Telegram alerts
│   ├── watchlist_manager.py
│   ├── risk_calculator.py
│   └── stats.py           # Performance stats from signal log
├── config/
│   ├── .env.example
│   └── blacklist.txt
├── data/                  # Cache and signals.json
├── logs/                  # screener.log
├── deployment/            # systemd, cron, Windows
└── tests/
    └── run_all_tests.py   # Single test entrypoint
```

## Tests

From project root:

```bash
python tests/run_all_tests.py
```

Runs: MEXC connection, Telegram (if token set), technical analysis, signal generation on synthetic data, risk calculator.

## Stats

View signal counts and breakdown:

```bash
python src/stats.py
```

## Documentation

- [STRATEGY.md](STRATEGY.md) – Trading logic and setups
- [API.md](API.md) – MEXC API usage and rate limits
- [DEPLOYMENT.md](DEPLOYMENT.md) – Run 24/7 (systemd, cron, Windows)
- [FAQ.md](FAQ.md) – Troubleshooting

## Disclaimer

This tool is for education and research. Verify every setup yourself. Not financial advice.
