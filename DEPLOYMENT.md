# Deploy the screener on a VPS (step by step)

Follow these steps in order. Copy and paste the commands. If your project is not in `/opt/ultimate-screener`, replace that path with your real path everywhere.

---

## Step 1: Put the project on the server

- If you use **git**: clone the repo into `/opt` (or any folder you like).
- If you use **upload**: upload the whole project folder to the server (e.g. `/opt/ultimate-screener`).

Example with git (run on the server):

```bash
sudo mkdir -p /opt
sudo git clone https://github.com/YOUR_USER/ultimate-screener.git /opt/ultimate-screener
```

(Replace the URL with your real repo. If you don’t use git, skip this and use your own path.)

---

## Step 2: Go into the project folder

Type this and press Enter:

```bash
cd /opt/ultimate-screener
```

You must be inside this folder for the next steps. If your project is somewhere else (e.g. `/root/bot/ultimate-screener`), use that path instead of `/opt/ultimate-screener`.

---

## Step 3: Create the `.env` file

The bot needs your Telegram token and chat ID. Do this:

1. Copy the example file:

   ```bash
   cp config/.env.example .env
   ```

2. Open the file to edit it:

   ```bash
   nano .env
   ```

3. Fill in these two lines (get the values from Telegram/BotFather):

   - `TELEGRAM_BOT_TOKEN=your_bot_token_here`
   - `TELEGRAM_CHAT_ID=your_chat_id_here`

4. Save and exit: press **Ctrl+O**, then **Enter**, then **Ctrl+X**.

---

## Step 4: Run the install script

This script will:

- Create a Python “venv” (virtual environment) in the project
- Install all required packages into that venv
- Install the systemd service so the screener runs 24/7

Run this **one** command (you may be asked for your password):

```bash
bash deployment/install_service.sh /opt/ultimate-screener
```

- If your project is in another folder, use that path instead of `/opt/ultimate-screener`.
- If you see “Create .env…” and the script exits, go back to Step 3 and make sure `.env` exists and has the two values set.

When it finishes, the service is installed and should already be running.

---

## Step 5: Check that it’s running

See the last lines of the service log:

```bash
sudo journalctl -u mexc-screener -n 30
```

You should see Python starting and no big red error. To watch the log live (updates as it runs):

```bash
sudo journalctl -u mexc-screener -f
```

Press **Ctrl+C** to stop watching.

---

## Step 6: Useful commands (after it’s installed)

- **Start the service** (if it’s stopped):  
  `sudo systemctl start mexc-screener`

- **Stop the service**:  
  `sudo systemctl stop mexc-screener`

- **Restart the service** (e.g. after you change `.env` or code):  
  `sudo systemctl restart mexc-screener`

- **See status** (running or failed):  
  `sudo systemctl status mexc-screener`

- **Watch logs live**:  
  `sudo journalctl -u mexc-screener -f`

---

## If something goes wrong

1. **Service keeps stopping (exit code 1)**  
   Run:  
   `sudo journalctl -u mexc-screener -n 50`  
   Read the last lines; they usually say what failed (e.g. missing `.env`, wrong path).

2. **“No module named 'dotenv'” or similar**  
   The service must use the project’s venv. Re-run the install script so it recreates/updates the venv and service:  
   `cd /opt/ultimate-screener`  
   `bash deployment/install_service.sh /opt/ultimate-screener`

3. **You changed the project path**  
   Run the install script again with the **new** path:  
   `bash deployment/install_service.sh /NEW/PATH/ultimate-screener`

---

## Logs and data

- **App log file**: `logs/screener.log` (in the project folder).
- **Signals log**: `data/signals.json`.
- **Cache**: `data/cache/`.

The service is set to restart automatically if it crashes (`Restart=always`).
