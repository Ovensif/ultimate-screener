# Deploy the screener on a Linux server (systemd service)

The bot is intended to run **only on Linux** as a systemd service. It exits with a message if run on Windows/macOS.

---

## Step 1: Put the project on the server

- **Git**: clone into `/opt` (or your preferred path).
- **Upload**: upload the full project folder to the server.

Example with git:

```bash
sudo mkdir -p /opt
sudo git clone https://github.com/YOUR_USER/ultimate-screener.git /opt/ultimate-screener
```

---

## Step 2: Go into the project folder

```bash
cd /opt/ultimate-screener
```

Use your actual path if different (e.g. `/root/bot/ultimate-screener`).

---

## Step 3: Create the `.env` file

1. Copy the example:

   ```bash
   cp config/.env.example .env
   ```

2. Edit:

   ```bash
   nano .env
   ```

3. Set:

   - `MIN_VOLUME=300000` (pairs with 24h volume ≥ this)
   - `SCAN_INTERVAL=600` (run every 10 minutes)
   - `TELEGRAM_BOT_TOKEN=...` (required — bot sends a Top 10 table to Telegram when it finds sweeps)
   - `TELEGRAM_CHAT_ID=...` (required)

4. Save and exit: **Ctrl+O**, **Enter**, **Ctrl+X**.

---

## Step 4: Run the install script (Linux only)

This script:

- Checks it is running on Linux (exits otherwise)
- Creates a Python venv and installs dependencies
- Installs the systemd service

Run (you may be asked for your password):

```bash
bash deployment/install_service.sh /opt/ultimate-screener
```

Use your actual project path if different. If the script says “Create .env…”, go back to Step 3.

---

## Step 5: Check that it’s running

View recent log lines:

```bash
sudo journalctl -u mexc-screener -n 30
```

Follow logs live:

```bash
sudo journalctl -u mexc-screener -f
```

Press **Ctrl+C** to stop.

---

## Useful commands

- **Start**: `sudo systemctl start mexc-screener`
- **Stop**: `sudo systemctl stop mexc-screener`
- **Restart** (e.g. after changing `.env`): `sudo systemctl restart mexc-screener`
- **Status**: `sudo systemctl status mexc-screener`
- **Live logs**: `sudo journalctl -u mexc-screener -f`

---

## Where to see errors

- **Running as a service**  
  Errors (and all output) go to the **systemd journal**. To view recent lines:
  ```bash
  sudo journalctl -u mexc-screener -n 50
  ```
  To follow live:
  ```bash
  sudo journalctl -u mexc-screener -f
  ```
  The app also writes logs to **`logs/screener.log`** in the project folder (e.g. `/opt/ultimate-screener/logs/screener.log`). Check that file for the same messages if you prefer.

- **Running manually** (e.g. `python -u src/main.py --once`)  
  Errors appear in the **terminal** (stdout/stderr). Log messages go to the terminal and to **`logs/screener.log`** in the project folder.

---

## One-shot run (Linux only)

From project root:

```bash
.venv/bin/python -u src/main.py --once
```

Runs one scan (volume filter + SWH/SWL sweep) and exits. Useful for testing.

---

## If something goes wrong

1. **Service exits with code 1**  
   Run: `sudo journalctl -u mexc-screener -n 50` and read the last lines (e.g. missing `.env`, wrong path).

2. **“No module named 'dotenv'”**  
   Re-run the install script so the venv and service are updated:  
   `cd /opt/ultimate-screener`  
   `bash deployment/install_service.sh /opt/ultimate-screener`

3. **Different project path**  
   Run the install script again with the new path:  
   `bash deployment/install_service.sh /NEW/PATH/ultimate-screener`

---

## Logs and data

- **App log**: `logs/screener.log` in the project folder
- **Cache**: `data/cache/` (OHLCV cache)
- **Top 10 state**: `data/top10_sweep_sent.json` — list of symbols last sent in the Telegram table, used to show 🔁 vs 🆕

The service uses `Restart=always` so it restarts automatically if it crashes.
