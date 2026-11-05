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
# Script: CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/NOTIFICATIONS/TELEGRAM_BOT/persistent_telegram_bot_check.sh
# Purpose: Ensures mingo_analysis_bot.py is running. If not, starts it detached and logs the.
# Owner: DATAFLOW_v3 contributors
# Sign-off: csoneira <csoneira@ucm.es>
# Last Updated: 2026-03-02
# Runtime: bash
# Usage: bash CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/NOTIFICATIONS/TELEGRAM_BOT/persistent_telegram_bot_check.sh [options]
# Inputs: CLI args, config files, environment variables, and/or upstream files.
# Outputs: Files, logs, or process-level side effects.
# Notes: Keep behavior configuration-driven and reproducible.
# =============================================================================

#
# Ensures mingo_analysis_bot.py is running. If not, starts it detached and logs the
# outcome so cron invocations stay silent unless something fails.

set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-${DATAFLOW_ROOT}/.venv/bin/python3}"
BOT_SCRIPT="${BOT_SCRIPT:-${DATAFLOW_ROOT}/CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/NOTIFICATIONS/TELEGRAM_BOT/mingo_analysis_bot.py}"
LOG_DIR="${LOG_DIR:-${DATAFLOW_ROOT}/CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/CRON_LOGS}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/bot_analysis.log}"
# Match the bot script path regardless of whether an older checkout path is
# still in the running command line. The bracket expression avoids matching
# this pgrep command itself.
PROCESS_PATTERN="[/]mingo_analysis_bot\.py([[:space:]]|$)"

timestamp() {
  date --iso-8601=seconds
}

log() {
  local line
  line="$(printf '%s %s' "$(timestamp)" "$*")"
  if [[ -z "${CRON_LOG_PATH:-}" ]]; then
    mkdir -p "$LOG_DIR"
    printf '%s\n' "$line" >>"$LOG_FILE"
  fi
  printf '%s\n' "$line"
}

if [[ ! -x "$PYTHON_BIN" ]]; then
  log "ERROR: python binary not found at $PYTHON_BIN"
  exit 1
fi

if [[ ! -f "$BOT_SCRIPT" ]]; then
  log "ERROR: bot script missing at $BOT_SCRIPT"
  exit 1
fi

if ! "$PYTHON_BIN" "$BOT_SCRIPT" --check-config >/dev/null 2>&1; then
  log "ERROR: bot configuration is missing or invalid; startup skipped"
  exit 1
fi

if /usr/bin/pgrep -f "$PROCESS_PATTERN" >/dev/null 2>&1; then
  # Healthy watchdog checks remain silent so cron creates no routine log.
  exit 0
fi

log "Bot not running; launching..."
mkdir -p "$LOG_DIR"
nohup "$PYTHON_BIN" "$BOT_SCRIPT" >>"$LOG_FILE" 2>&1 &
pid=$!
log "Bot started with PID $pid."

exit 0
