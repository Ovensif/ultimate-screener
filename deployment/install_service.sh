#!/bin/bash
# Install systemd service for MEXC Futures Screener. Run from project root.
set -e
PROJECT_DIR="${1:-/opt/ultimate-screener}"
mkdir -p "$PROJECT_DIR"/{data/cache,logs,config}
if [ ! -f "$PROJECT_DIR/.env" ]; then
  echo "Create $PROJECT_DIR/.env from config/.env.example and set TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID"
  exit 1
fi
echo "Setting up virtual environment (venv)..."
if [ ! -d "$PROJECT_DIR/.venv" ]; then
  python3 -m venv "$PROJECT_DIR/.venv"
  echo "Installing Python packages into venv..."
  "$PROJECT_DIR/.venv/bin/python" -m pip install -r "$PROJECT_DIR/requirements.txt"
else
  echo "Venv exists. Updating packages..."
  "$PROJECT_DIR/.venv/bin/python" -m pip install -r "$PROJECT_DIR/requirements.txt"
fi
SERVICE_FILE="$(dirname "$0")/mexc-screener.service"
sed "s|/opt/ultimate-screener|$PROJECT_DIR|g" "$SERVICE_FILE" | sudo tee /etc/systemd/system/mexc-screener.service > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable mexc-screener
sudo systemctl start mexc-screener
echo "Service installed. Check: sudo journalctl -u mexc-screener -f"
