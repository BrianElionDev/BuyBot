#!/bin/bash
# Start Discord Bot Service
# Usage: bash scripts/start_discord_service.sh

set -e

PROJECT_DIR="/home/ngigi/Documents/Brayo/rubicon-trading-bot"
VENV_DIR="$PROJECT_DIR/venv"
LOG_DIR="$PROJECT_DIR/logs"
SERVICE_LOG="$LOG_DIR/discord_bot_service.log"

echo "=== Starting Discord Bot Service ==="

# Navigate to project directory
cd "$PROJECT_DIR"

# Check if virtual environment exists
if [ ! -d "$VENV_DIR" ]; then
    echo "❌ Virtual environment not found at $VENV_DIR"
    exit 1
fi

# Activate virtual environment
source "$VENV_DIR/bin/activate"

# Create logs directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Check if service is already running
if pgrep -f "discord_bot/main.py" > /dev/null; then
    echo "⚠️  Discord bot service is already running"
    echo "   PID: $(pgrep -f 'discord_bot/main.py')"
    echo "   To restart, run: bash scripts/restart_discord_service.sh"
    exit 0
fi

# Check if port 8001 is already in use
if netstat -tlnp 2>/dev/null | grep -q ":8001 "; then
    echo "❌ Port 8001 is already in use"
    echo "   Check what's using the port: netstat -tlnp | grep :8001"
    exit 1
fi

# Start the service
echo "🚀 Starting Discord Bot Service..."
echo "   Log file: $SERVICE_LOG"
echo "   Press Ctrl+C to stop the service"
echo ""

# Start the service (foreground for now, can be backgrounded later)
python3 discord_bot/main.py 2>&1 | tee "$SERVICE_LOG"




