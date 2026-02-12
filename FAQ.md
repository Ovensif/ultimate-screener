# FAQ and troubleshooting

## Installation / dependencies

**`ModuleNotFoundError: No module named 'dotenv'` (or other missing module)**

- The app needs its dependencies installed in the **same Python** that runs the script.
- On your VPS, from the project root run:
  ```bash
  cd /root/bot/ultimate-screener
  pip install -r requirements.txt
  ```
  Or install the missing package directly: `pip install python-dotenv`
- If you use **systemd**, it runs `/usr/bin/python3` by default. Either:
  - Install dependencies for that Python: `sudo pip3 install -r requirements.txt`, or
  - Use a venv: create one with `python3 -m venv .venv`, then `source .venv/bin/activate` and `pip install -r requirements.txt`, and in the systemd unit set:
    `ExecStart=/root/bot/ultimate-screener/.venv/bin/python -u src/main.py`

---

## Telegram

**I don’t receive any messages.**

- Confirm `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`. No quotes needed.
- Get the chat ID: send a message to the bot or add the bot to a group, then open `https://api.telegram.org/bot<TOKEN>/getUpdates` and read `message.chat.id`.
- For groups, the chat ID is usually negative (e.g. `-1001234567890`).
- Check logs for “Telegram send failed” or non-200 responses.

**Messages are cut off or look wrong.**

- The bot sends plain text (no Markdown) to avoid parsing issues. If you enabled Markdown in the bot, try turning it off.

---

## MEXC / API

**510 "Requests are too frequent" / 429 Too Many Requests**

- MEXC rate-limits when too many requests are sent in a short time. The screener now:
  - Waits **0.4 s** between each API call (throttle).
  - On 510/429, **retries with longer backoff** (5s, 10s, 20s, …) up to 5 times.
- If you still see it often: increase `SCAN_INTERVAL` (e.g. 600), lower `MAX_COINS` (e.g. 15), or increase `WATCHLIST_REFRESH` so the watchlist is updated less often.
- Don’t run multiple instances of the screener against the same exchange.

**No markets or wrong symbols**

- Ensure CCXT is used with `defaultType: "future"` so you get perpetuals. The screener sets this in `data_fetcher.py`.
- If a symbol fails (e.g. “market not found”), it may be delisted; the screener skips it and continues.

---

## No signals

**The scanner runs but I never get a signal.**

- The logic is strict on purpose: 1D trend + 4H setup + 2+ confluence + R:R ≥ 2.0 + HIGH confidence (if `CONFIDENCE_THRESHOLD=HIGH`). In ranging or low-volatility markets you may see no signals for a while.
- Try:
  - Lower `CONFIDENCE_THRESHOLD` to `MEDIUM` (sends MEDIUM and HIGH).
  - Slightly lower `MIN_RR_RATIO` (e.g. 1.5) – only if you accept lower R:R.
- Check the watchlist: `MAX_COINS`, `MIN_VOLUME`, and the trend score (≥ 4) filter out many symbols. Logs show “Watchlist refreshed: N coins”. If N is 0, relax filters or check MEXC connectivity.
- **BTC filter**: When BTC is down more than 5% in 1 hour, only HIGH confidence signals are sent. So during strong BTC dumps you’ll see fewer alerts.

**Too many signals / spam**

- Each symbol has a 4-hour cooldown: at most one signal per symbol per 4 hours.
- If you still get too many, set `CONFIDENCE_THRESHOLD=HIGH` and keep `MIN_RR_RATIO` at 2.0 or higher.

---

## Time and timezone

- Timestamps in the app and in logs are in UTC. Telegram message timestamps are from the server when the signal was generated.
- For cron, ensure the server timezone is correct (e.g. `TZ=UTC` or your preferred zone).

---

## Debug logs

- Default log level is INFO. To see more detail (e.g. per-symbol skip reasons), set the root logger to DEBUG in code or change `logging.root.setLevel(logging.DEBUG)` in `src/main.py` (or in `_setup_logging()` in the same file) and restart.

---

## Performance and stats

- **Stats**: Run `python src/stats.py` from the project root to see total signals, by side/setup, and (if you’ve been filling it) outcome counts.
- **Signals log**: `data/signals.json` stores each sent signal. You can add an “outcome” field later (e.g. tp1, sl) and use it for win rate and average R in `stats.py` or a daily Telegram summary.
