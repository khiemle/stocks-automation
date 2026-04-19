#!/bin/bash
# watchdog.sh — restart trading_bot.py if it crashes.
# Usage: bash watchdog.sh [--once]
#   --once  run the bot once without restart loop (for testing)

set -euo pipefail

BOT_CMD="python trading_bot.py start"
LOG_FILE="logs/watchdog.log"
RESTART_DELAY=30  # seconds before restart

mkdir -p logs

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

if [[ "${1:-}" == "--once" ]]; then
    log "watchdog: running in --once mode"
    $BOT_CMD
    exit $?
fi

log "watchdog: started (PID=$$)"

while true; do
    log "watchdog: launching bot"
    $BOT_CMD >> logs/bot.log 2>&1 || true
    EXIT_CODE=$?
    log "watchdog: bot exited with code $EXIT_CODE — restarting in ${RESTART_DELAY}s"
    sleep "$RESTART_DELAY"
done
