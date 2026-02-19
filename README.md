# Ultimate Screener (SWH/SWL)

Simple bot that:

1. **Filters pairs** by 24h volume ≥ 300,000 (configurable)
2. **Runs every 10 minutes** (configurable)
3. **Checks if each pair has a confirmed liquidity sweep** of Swing High (SWH) or Swing Low (SWL), using logic from commit aec9c8e (pivot 7/3 bars, wick beyond S/R + close back inside + confirmation)

Runs **as a Linux systemd service only** (e.g. on a VPS).

## Features

- **Volume filter**: Only USDT perpetual futures with 24h volume ≥ `MIN_VOLUME` (default 300,000)
- **SWH/SWL sweep**: Pivot high/low (7 left, 3 right bars); S/R from last 5 swing levels; sweep = wick beyond level, close back inside, confirmed by candle direction
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
| SWING_PIVOT_LEFT | Pivot bars to the left | 7 |
| SWING_PIVOT_RIGHT | Pivot bars to the right | 3 |
| SWING_TIMEFRAME | OHLCV timeframe for sweep detection | 4h |
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
│   ├── sweep_screener.py # Volume filter + SWH/SWL liquidity sweep (aec9c8e)
│   └── telegram_bot.py   # Optional sweep report
├── config/
│   └── .env.example
├── deployment/
│   ├── install_service.sh   # Linux: venv + systemd
│   └── mexc-screener.service
├── data/ and logs/
└── requirements.txt
```

## Swing High / Low (aec9c8e liquidity sweep)

Sweep logic from commit aec9c8e:

- **Pivots**: Rolling max/min with 7 bars left, 3 bars right; keep last 10 swing highs and 10 swing lows
- **S/R**: Strongest support = top of last 5 swing lows; strongest resistance = top of last 5 swing highs
- **Sweep**: Wick beyond the level (low &lt; support or high &gt; resistance), then close back inside; **confirmed** when the sweep candle closes in direction (bullish for long sweep, bearish for short)

## Documentation

- [DEPLOYMENT.md](DEPLOYMENT.md) — Install and run as systemd service on Linux

## Disclaimer

For education and research. Not financial advice.
