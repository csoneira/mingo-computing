#!/usr/bin/env bash

# Resolve the checkout from this script's location when the caller did not provide it.
if [[ -z "${DATAFLOW_ROOT:-}" ]]; then
  _repo_probe="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
  while [[ "$_repo_probe" != "/" && ! -f "$_repo_probe/CONTEXTUAL/CONFIG/CONTENTS/environment/dataflow.sh" ]]; do
    _repo_probe="$(dirname -- "$_repo_probe")"
  done
  if [[ -f "$_repo_probe/CONTEXTUAL/CONFIG/CONTENTS/environment/dataflow.sh" ]]; then
    # shellcheck source=/dev/null
    source "$_repo_probe/CONTEXTUAL/CONFIG/CONTENTS/environment/dataflow.sh"
  else
    echo "Could not locate repository root from ${BASH_SOURCE[0]}" >&2
    exit 2
  fi
fi
unset _repo_probe
# =============================================================================
# DATAFLOW_v3 Script Header v1
# Script: CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/NOTIFICATIONS/TELEGRAM_BOT/kill_bot_and_restart.sh
# Purpose: kill_bot_and_restart.sh.
# Owner: DATAFLOW_v3 contributors
# Sign-off: csoneira <csoneira@ucm.es>
# Last Updated: 2026-03-02
# Runtime: bash
# Usage: bash CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/NOTIFICATIONS/TELEGRAM_BOT/kill_bot_and_restart.sh [options]
# Inputs: CLI args, config files, environment variables, and/or upstream files.
# Outputs: Files, logs, or process-level side effects.
# Notes: Keep behavior configuration-driven and reproducible.
# =============================================================================

# kill_bot_and_restart.sh
# Edit SERVICE_NAME or BOT_CMD / BOT_NAME below to match your bot setup.

set -euo pipefail

# ----- CONFIGURE BELOW -----
SERVICE_NAME=""                          # e.g. my-telegram-bot.service (leave empty if not using systemd)
BOT_CMD="/bin/bash ${DATAFLOW_ROOT}/CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/NOTIFICATIONS/TELEGRAM_BOT/persistent_telegram_bot_check.sh"   # full command to start the bot (used when SERVICE_NAME is empty)
BOT_NAME="mingo_analysis_bot.py"                # pattern used to find running bot with pgrep -f (fallback if BOT_CMD is not unique)
LOG_FILE="${DATAFLOW_ROOT}/CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/NOHUP_LOGS/kill_bot_nohup.log"      # where nohup will append logs
WAIT_SEC=1                               # seconds to wait for graceful shutdown
# ----------------------------

die(){ echo "$*" >&2; exit 1; }

if [ -n "$SERVICE_NAME" ] && command -v systemctl >/dev/null 2>&1; then
    echo "Restarting systemd service: $SERVICE_NAME"
    sudo systemctl restart "$SERVICE_NAME"
    exit 0
fi

# Ensure BOT_CMD is set if not using systemd
if [ -z "$BOT_CMD" ]; then
    die "BOT_CMD is not configured. Edit the script and set BOT_CMD or SERVICE_NAME."
fi

PATTERN="$BOT_NAME"
if [ -z "$PATTERN" ]; then
    PATTERN="$BOT_CMD"
fi

# find running pids
pids=$(pgrep -f "$PATTERN" || true)

if [ -n "$pids" ]; then
    echo "Stopping bot processes matching '$PATTERN': $pids"
    kill $pids || true

    # wait for graceful shutdown
    for i in $(seq 1 "$WAIT_SEC"); do
        sleep 1
        remaining=$(pgrep -f "$PATTERN" || true)
        [ -z "$remaining" ] && break
    done

    remaining=$(pgrep -f "$PATTERN" || true)
    if [ -n "$remaining" ]; then
        echo "Processes still running after ${WAIT_SEC}s, forcing kill: $remaining"
        kill -9 $remaining || true
    fi
else
    echo "No running bot processes found for pattern: '$PATTERN'"
fi

# # ensure log file directory exists
# mkdir -p "$(dirname "$LOG_FILE")"
# touch "$LOG_FILE"

# echo "Starting bot with command: $BOT_CMD"
# # start in background and detach
# nohup bash -c "$BOT_CMD" >>"$LOG_FILE" 2>&1 &

# echo "Bot restarted. Logs appended to: $LOG_FILE"
