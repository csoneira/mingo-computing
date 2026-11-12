#!/usr/bin/env bash
# Purpose: Stop and restart the Telegram bot process.

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

set -euo pipefail

BOT_SCRIPT="${DATAFLOW_ROOT}/CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/NOTIFICATIONS/TELEGRAM_BOT/mingo_analysis_bot.py"
WATCHDOG_SCRIPT="${DATAFLOW_ROOT}/CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/NOTIFICATIONS/TELEGRAM_BOT/persistent_telegram_bot_check.sh"
PROCESS_PATTERN='[/]mingo_analysis_bot\.py([[:space:]]|$)'

if [[ ! -f "$BOT_SCRIPT" || ! -f "$WATCHDOG_SCRIPT" ]]; then
  echo "Telegram bot or watchdog script is missing." >&2
  exit 1
fi

mapfile -t pids < <(pgrep -f "$PROCESS_PATTERN" || true)
if ((${#pids[@]})); then
  kill "${pids[@]}" 2>/dev/null || true
  for _ in {1..10}; do
    sleep 1
    mapfile -t pids < <(pgrep -f "$PROCESS_PATTERN" || true)
    ((${#pids[@]} == 0)) && break
  done
  if ((${#pids[@]})); then
    echo "Bot did not stop gracefully; terminating remaining process(es): ${pids[*]}" >&2
    kill -KILL "${pids[@]}" 2>/dev/null || true
    sleep 1
  fi
fi

# Reuse the active startup and configuration checks used by cron.
exec /bin/bash "$WATCHDOG_SCRIPT"
