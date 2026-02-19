# Ultimate Screener (SWH/SWL)

Simple bot that:

1. **Filters pairs** by 24h volume ≥ 300,000 (configurable)
2. **Runs every 10 minutes** (configurable)
3. **Checks if each pair has already swept** Swing High (SWH) or Swing Low (SWL), using logic from [Pine Script Crypto View 1.0](https://www.tradingview.com/pine-script/) (pivot length 5, lookback 30 bars)

Runs **as a Linux systemd service only** (e.g. on a VPS).

## Features

- **Volume filter**: Only USDT perpetual futures with 24h volume ≥ `MIN_VOLUME` (default 300,000)
- **SWH/SWL sweep**: Pine-style pivot high/low (length 5), then detect if price has swept those levels within the last 30 bars
- **Interval**: Scan runs every `SCAN_INTERVAL` seconds (default 600 = 10 minutes)
- **Telegram**: Sends a Top 10 table to your chat whenever the bot finds pairs that swept SWH/SWL (requires token and chat ID)

## Requirements

- **Linux** (for systemd service; the process exits on non-Linux)
- Python 3.9+
- MEXC public API (ccxt) — no API keys needed for OHLCV/ticker

## Install (Linux server)

```bash
cd /opt/ultimate-screener
cp config/.env.example .env
# Edit .env: MIN_VOLUME=300000, SCAN_INTERVAL=600; optional Telegram
bash deployment/install_service.sh /opt/ultimate-screener
```

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| MIN_VOLUME | Min 24h volume (USD) to include a pair | 300000 |
| SCAN_INTERVAL | Seconds between scans | 600 (10 min) |
| SWING_PIVOT_LEN | Pivot bars left/right (Pine style) | 5 |
| SWING_LOOKBACK | Bars after pivot to check for sweep | 30 |
| SWING_TIMEFRAME | OHLCV timeframe for swing detection | 4h |
| TELEGRAM_BOT_TOKEN | Telegram bot token (required; sends Top 10 table when sweeps found) | — |
| TELEGRAM_CHAT_ID | Telegram chat ID (required) | — |

## Run

- **As service (Linux)**: Installed by `install_service.sh`. Use `sudo systemctl start mexc-screener`, `journalctl -u mexc-screener -f`, etc.
- **One-shot (Linux only)**: `python -u src/main.py --once` — runs one scan and exits (still requires Linux).

If something fails, see [DEPLOYMENT.md](DEPLOYMENT.md#where-to-see-errors) for where to see errors (journal vs log file vs terminal).

## Project structure

```
ultimate-screener/
├── src/
│   ├── main.py           # Entry: Linux check, scheduler every 10 min
│   ├── config.py         # MIN_VOLUME, SCAN_INTERVAL, swing params
│   ├── data_fetcher.py   # MEXC OHLCV, ticker, markets
│   ├── sweep_screener.py # Volume filter + SWH/SWL sweep (Pine logic)
│   └── telegram_bot.py   # Optional sweep report
├── config/
│   └── .env.example
├── deployment/
│   ├── install_service.sh   # Linux: venv + systemd
│   └── mexc-screener.service
├── data/ and logs/
└── requirements.txt
```

## Swing High / Low (Pine reference)

Logic follows **Crypto View 1.0** Pine script:

- **Pivot High**: `ta.pivothigh(high, 5, 5)` — bar is a swing high if it’s the max of 5 bars left and 5 bars right
- **Pivot Low**: `ta.pivotlow(low, 5, 5)`
- **Swept**: Within 30 bars after the pivot bar, price has gone through the level (high ≥ swing high or low ≤ swing low)

## Documentation

- [DEPLOYMENT.md](DEPLOYMENT.md) — Install and run as systemd service on Linux

## Disclaimer

For education and research. Not financial advice.
