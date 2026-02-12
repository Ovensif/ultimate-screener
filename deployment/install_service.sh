#!/bin/bash
# Install systemd service for MEXC Futures Screener. Run from project root.
set -e
PROJECT_DIR="${1:-/opt/ultimate-screener}"
mkdir -p "$PROJECT_DIR"/{data/cache,logs,config}
if [ ! -f "$PROJECT_DIR/.env" ]; then
  echo "Create $PROJECT_DIR/.env from config/.env.example and set TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID"
  exit 1
fi
# Use venv so systemd runs with project dependencies (python-dotenv, ccxt, etc.)
if [ ! -d "$PROJECT_DIR/.venv" ]; then
  echo "Creating venv and installing dependencies..."
  python3 -m venv "$PROJECT_DIR/.venv"
  "$PROJECT_DIR/.venv/bin/pip" install -r "$PROJECT_DIR/requirements.txt"
fi
SERVICE_FILE="$(dirname "$0")/mexc-screener.service"
sed "s|/opt/ultimate-screener|$PROJECT_DIR|g" "$SERVICE_FILE" | sudo tee /etc/systemd/system/mexc-screener.service > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable mexc-screener
sudo systemctl start mexc-screener
echo "Service installed. Check: sudo journalctl -u mexc-screener -f"
