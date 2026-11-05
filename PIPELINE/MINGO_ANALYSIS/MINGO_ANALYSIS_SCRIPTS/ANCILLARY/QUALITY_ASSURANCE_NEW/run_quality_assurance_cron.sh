#!/usr/bin/env bash
set -euo pipefail

MODE="often"
if [[ "${1:-}" == "often" || "${1:-}" == "plot" || "${1:-}" == "qa-plot" ]]; then
  MODE="$1"
  shift
fi

QA_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$QA_ROOT/LOGS"
mkdir -p "$LOG_DIR"

LOCK_FILE="$LOG_DIR/quality_assurance.lock"
LOG_FILE="$LOG_DIR/quality_assurance_${MODE}.log"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  printf '[%s] QUALITY_ASSURANCE_NEW %s already running; skipping.\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$MODE" >> "$LOG_FILE"
  exit 0
fi

{
  printf '[%s] QUALITY_ASSURANCE_NEW %s started.\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$MODE"
  python3 "$QA_ROOT/orchestrate_quality_assurance.py" --mode "$MODE" "$@"
  printf '[%s] QUALITY_ASSURANCE_NEW %s finished.\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$MODE"
} >> "$LOG_FILE" 2>&1
