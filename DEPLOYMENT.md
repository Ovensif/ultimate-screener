# Deployment – Run 24/7

Ways to run the screener continuously or on a schedule.

## Linux: systemd service

1. Copy the project to the server (e.g. `/opt/crypto_futures_screener`).
2. Create `.env` from `config/.env.example` and set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.
3. Install dependencies: `pip install -r requirements.txt` (prefer a venv).
4. Run the install script (from project root):

   ```bash
   bash deployment/install_service.sh /opt/crypto_futures_screener
   ```

   This copies the systemd unit (with your path), enables and starts the service.

5. Check logs:

   ```bash
   sudo journalctl -u mexc-screener -f
   ```

6. Restart/stop:

   ```bash
   sudo systemctl restart mexc-screener
   sudo systemctl stop mexc-screener
   ```

The unit file uses `Restart=always` and `RestartSec=10` so the process is restarted on failure.

## Linux/Unix: cron (one-shot every 5 min)

If you prefer cron instead of a long-running process:

1. Edit `deployment/cron_example.txt` and set the real project path.
2. Add to crontab:

   ```bash
   crontab -e
   # Paste the line, e.g.:
   */5 * * * * cd /opt/crypto_futures_screener && python3 src/main.py --once >> logs/cron.log 2>&1
   ```

Each run does one watchlist refresh (if needed) and one full scan, then exits.

## Windows: Task Scheduler

1. Use the batch files in `deployment/`:
   - **run_screener.bat** – runs `python src/main.py` (continuous; keep the window open or run in background).
   - **run_once.bat** – runs `python src/main.py --once` (single scan).

2. For scheduled runs:
   - Open Task Scheduler.
   - Create a new task; trigger: e.g. every 5 minutes or at startup.
   - Action: Start a program → Program: `python` or full path to `python.exe`; Arguments: `src\main.py --once`; Start in: project folder (e.g. `C:\...\crypto_futures_screener`).
   - If you use a venv, set the program to the venv’s `python.exe` and Start in to the project root.

## Logs and data

- **Logs**: `logs/screener.log` (rotating, 2 MB × 3 backups). Ensure `logs/` exists (created automatically on first run).
- **Signals**: `data/signals.json` – every sent signal is appended for stats.
- **Cache**: `data/cache/` – OHLCV cache to reduce API calls.

## Health check

There is no built-in HTTP health endpoint. You can:

- Monitor `logs/screener.log` for errors.
- Check that `data/signals.json` is updated when signals are sent.
- Optionally write a “last scan” timestamp to a file in `data/` and have an external monitor read it.
