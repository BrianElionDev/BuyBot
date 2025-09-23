#!/usr/bin/env bash
set -euo pipefail

# Trade famine monitor: checks endpoint activity in the last 12 hours.
# If no hits, sends a Telegram message using TELEGRAM_BOT_TOKEN and TELEGRAM_NOTIFICATION_CHAT_ID.

# Resolve project root from this script's location (scripts/maintenance/ -> project root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_DIR="$PROJECT_ROOT/logs"

# Optional: load values from .env if not set in the environment
load_from_env_file() {
  local var_name="$1"
  local env_file="$PROJECT_ROOT/.env"
  if [[ -z "${!var_name-}" && -f "$env_file" ]]; then
    # shellcheck disable=SC2162
    while IFS='=' read key value; do
      # skip comments and empty lines
      [[ -z "$key" ]] && continue
      [[ "$key" =~ ^# ]] && continue
      if [[ "$key" == "$var_name" ]]; then
        # strip surrounding quotes if present
        value="${value%\r}"
        value="${value%\n}"
        value="${value%"\""}"
        value="${value#"\""}"
        export "$var_name"="$value"
        break
      fi
    done < "$env_file"
  fi
}

load_from_env_file TELEGRAM_BOT_TOKEN
load_from_env_file TELEGRAM_NOTIFICATION_CHAT_ID

if [[ -z "${TELEGRAM_BOT_TOKEN-}" || -z "${TELEGRAM_NOTIFICATION_CHAT_ID-}" ]]; then
  echo "[monitor_trade_famine] Missing TELEGRAM_BOT_TOKEN or TELEGRAM_NOTIFICATION_CHAT_ID" >&2
  exit 1
fi

# Compute cutoff epoch for last 12 hours
CUTOFF_EPOCH=$(date -u -d '12 hours ago' +%s)

# Aggregate endpoint hits from logs
if ! compgen -G "$LOG_DIR/endpoints_*.log" > /dev/null; then
  HITS=0
else
  # Patterns to match endpoint activity lines; adjust if needed
  PATTERN_REGEX='signal|follow[-_ ]?up|update|discord_endpoint|/api/v1/discord/signal'

  HITS=$(grep -hE "$PATTERN_REGEX" "$LOG_DIR"/endpoints_*.log 2>/dev/null | \
    awk -v cutoff="$CUTOFF_EPOCH" '
      {
        # Expected timestamps like: 2025-09-16 11:00:19 - ...
        ts = $1; t2 = $2; gsub(/,/, "", t2);
        if (ts == "") next;
        iso = ts;
        if (index(ts, "T") == 0 && t2 != "-") { iso = ts "T" t2 }
        gsub(/Z$/, "", iso);
        cmd = "date -u -d \"" iso "\" +%s";
        cmd | getline epoch;
        close(cmd);
        if (epoch >= cutoff) { print }
      }
    ' | wc -l | tr -d ' ')
fi

echo "[monitor_trade_famine] Endpoint hits in last 12h: ${HITS:-0}"

if [[ "${HITS:-0}" -eq 0 ]]; then
  MSG="Trade famine: Kindly check discord to confirm everything is fine"
  curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
    -d chat_id="${TELEGRAM_NOTIFICATION_CHAT_ID}" \
    --data-urlencode text="$MSG" >/dev/null || true
  echo "[monitor_trade_famine] Alert sent to Telegram chat_id=${TELEGRAM_NOTIFICATION_CHAT_ID}"
else
  echo "[monitor_trade_famine] Activity detected; no alert sent."
fi


