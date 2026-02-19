# Ultimate Screener (SWH/SWL)

Simple bot that:

1. **Filters pairs** by 24h volume ≥ 300,000 (configurable)
2. **Runs every 10 minutes** (configurable)
3. **Checks if each pair swept** Swing High (SWH) or Swing Low (SWL) on the current bar, using **Pine Script Crypto View 1.0** logic (confPivotLen=5, confSwingBars=30)

Runs **as a Linux systemd service only** (e.g. on a VPS).

## Features

- **Volume filter**: Only USDT perpetual futures with 24h volume ≥ `MIN_VOLUME` (default 300,000)
- **SWH/SWL sweep**: Same as Crypto View 1.0 — `ta.pivothigh`/`ta.pivotlow(5,5)`, swept when current bar breaks level within 30 bars of the swing
- **Interval**: Scan runs every `SCAN_INTERVAL` seconds (default 600 = 10 minutes)
- **Telegram**: Top 10 alert with **Signal** (▲ LONG / ▼ SHORT / ▲▼ BOTH), **Level** (price swept), and **Status** (🆕 new / 🔁 returning) for daily trading

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
| SWING_PIVOT_LEN | Pivot length (Crypto View confPivotLen) | 5 |
| SWING_LOOKBACK | Bars after swing to count as swept (confSwingBars) | 30 |
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
│   ├── sweep_screener.py # Volume filter + SWH/SWL sweep (Crypto View 1.0)
│   └── telegram_bot.py   # Optional sweep report
├── config/
│   └── .env.example
├── deployment/
│   ├── install_service.sh   # Linux: venv + systemd
│   └── mexc-screener.service
├── data/ and logs/
└── requirements.txt
```

## Swing High / Low (Crypto View 1.0)

Logic matches the Pine Script **Crypto View 1.0** (Tables group):

- **Pivots**: `ta.pivothigh(high, 5, 5)` and `ta.pivotlow(low, 5, 5)` — bar is SWH/SWL if it’s the max/min of 5 bars left and 5 right
- **Swept**: Current bar is within 30 bars after the swing bar **and** its high ≥ last swing high (or low ≤ last swing low)
- **Telegram**: Signal = ▲ LONG (swept SL), ▼ SHORT (swept SH), or ▲▼ BOTH; Level = key price to watch for deviation/continuation

## Documentation

- [DEPLOYMENT.md](DEPLOYMENT.md) — Install and run as systemd service on Linux

## Disclaimer

For education and research. Not financial advice.
