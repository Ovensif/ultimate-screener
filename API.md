# MEXC API Usage

The screener uses **CCXT** to talk to MEXC. Only **public** endpoints are required for scanning and alerts; API key/secret are optional (e.g. for future private features).

## Exchange and symbol format

- **Exchange**: MEXC, with `options = {"defaultType": "future"}` so all calls target **USDT-margined perpetual futures**.
- **Symbol format**: Unified CCXT format, e.g. `BTC/USDT:USDT` (base/quote:settlement).

## Endpoints used

| Purpose | CCXT method | MEXC concept |
|--------|-------------|--------------|
| List perpetuals | `fetch_markets()` | Contract list (filter by type future / swap, quote USDT) |
| 24h ticker | `fetch_ticker(symbol)` | 24h stats: last, bid, ask, volume, percentage change |
| OHLCV | `fetch_ohlcv(symbol, timeframe, limit)` | K-line/candlestick data |

## Timeframes

Supported and mapped to MEXC:

- `1d` – daily
- `4h` – 4-hour
- `1h` – 1-hour (e.g. BTC 1h change)
- `15m` – 15-minute (optional)

## Rate limits

MEXC enforces per-endpoint rate limits. The code:

- Uses a **single** exchange instance.
- Implements **retry with exponential backoff** on failures.
- Respects **429** and **Retry-After** when present.
- Caches OHLCV briefly (e.g. 1 minute) to avoid duplicate calls in the same scan.

Avoid bursting many symbols in parallel; the current design fetches sequentially or in small batches to stay within limits.

## Official docs

- [MEXC Futures API](https://www.mexc.com/api-docs/futures/)
- [CCXT Manual](https://docs.ccxt.com/)

## Optional: API key and secret

Set `MEXC_API_KEY` and `MEXC_API_SECRET` in `.env` if you need private endpoints later (e.g. account or orders). The screener does **not** require them for signal generation and Telegram alerts.
