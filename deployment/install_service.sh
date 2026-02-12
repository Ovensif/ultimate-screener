#!/bin/bash
# Install systemd service for MEXC Futures Screener. Run from project root.
set -e
PROJECT_DIR="${1:-/opt/crypto_futures_screener}"
mkdir -p "$PROJECT_DIR"/{data/cache,logs,config}
if [ ! -f "$PROJECT_DIR/.env" ]; then
  echo "Create $PROJECT_DIR/.env from config/.env.example and set TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID"
  exit 1
fi
SERVICE_FILE="$(dirname "$0")/mexc-screener.service"
sed "s|/opt/crypto_futures_screener|$PROJECT_DIR|g" "$SERVICE_FILE" | sudo tee /etc/systemd/system/mexc-screener.service > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable mexc-screener
sudo systemctl start mexc-screener
echo "Service installed. Check: sudo journalctl -u mexc-screener -f"
