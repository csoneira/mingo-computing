#!/usr/bin/env bash
# Purpose: Back up remote station log trees into the local archive.

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
# Script: CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/DATA_MAINTENANCE/REMOTE_LOG_BACKUP/run_log_backup.sh
# Purpose: Maintain an append-safe backup of remote MINGO log trees.
# =============================================================================

set -euo pipefail

show_help() {
  cat <<'EOF'
run_log_backup.sh

Pulls /home/rpcuser/logs from mingo01..mingo04 into:
  CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/REMOTE_LOG_BACKUP/hosts/<host>/current/

Rules:
  - current/ is an exact mirror of the latest successful remote state.
  - history/<timestamp>/ temporarily stores files replaced or deleted from
    current/; selection-aware retention is applied after a successful run.
  - If a remote log tree becomes empty, the old logs are moved into history/
    before selection-aware history retention is applied.

Usage:
  bash run_log_backup.sh [options] [host ...]

Options:
  --host NAME           Backup only one host. Can be repeated.
  --root PATH           Override runtime backup root.
                        Default: repository-relative CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/REMOTE_LOG_BACKUP
  --source-base PATH    Local test source base; expects PATH/<host>/...
  --remote-user USER    Override remote SSH user. Default: rpcuser
  --remote-root PATH    Override remote log root. Default: /home/rpcuser/logs
  --no-history-prune    Do not prune history after successful backups.
  -h, --help            Show this help text.

Environment overrides:
  LOG_BACKUP_ROOT
  LOG_BACKUP_HOSTS
  LOG_BACKUP_SOURCE_BASE
  LOG_BACKUP_REMOTE_USER
  LOG_BACKUP_REMOTE_ROOT
  LOG_BACKUP_RUN_TIMESTAMP
  LOG_BACKUP_SSH_OPTIONS
  LOG_BACKUP_HISTORY_RETENTION_ENABLED
  LOG_BACKUP_SELECTION_CONFIG
  LOG_BACKUP_HISTORY_CONTEXT_MONTHS
EOF
}

log() {
  printf '[%s] %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*"
}

require_command() {
  local command_name="$1"
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Missing required command: $command_name" >&2
    exit 1
  fi
}

require_option_value() {
  local option_name="$1"
  local option_value="${2:-}"
  if [[ -z "$option_value" ]]; then
    echo "Missing value for $option_name" >&2
    exit 1
  fi
}

remove_empty_history_dir_tree() {
  local start_dir="$1"
  local stop_dir="$2"
  local current_dir="$start_dir"

  while [[ -n "$current_dir" && "$current_dir" != "/" ]]; do
    rmdir "$current_dir" 2>/dev/null || break
    if [[ "$current_dir" == "$stop_dir" ]]; then
      break
    fi
    current_dir="$(dirname "$current_dir")"
  done
}

write_current_manifest() {
  local current_dir="$1"
  local manifest_path="$2"
  local tmp_manifest

  tmp_manifest="$(mktemp)"
  {
    printf 'mtime_utc\tsize_bytes\trelative_path\n'
    if [[ -d "$current_dir" ]]; then
      LC_ALL=C find "$current_dir" -type f -printf '%TY-%Tm-%TdT%TH:%TM:%TS\t%s\t%P\n' | sort
    fi
  } > "$tmp_manifest"
  mv "$tmp_manifest" "$manifest_path"
}

prune_history_for_host() {
  local host="$1"
  local -a prune_cmd=(
    /usr/bin/env python3 "$HISTORY_PRUNER"
    --root "$BACKUP_ROOT"
    --config "$SELECTION_CONFIG"
    --context-months "$HISTORY_CONTEXT_MONTHS"
    --host "$host"
    --apply
  )

  if [[ "$HISTORY_RETENTION_ENABLED" != "1" ]]; then
    log "History retention disabled for $host"
    return 0
  fi
  if [[ ! -f "$HISTORY_PRUNER" ]]; then
    log "WARNING: history retention helper is missing; history left untouched: $HISTORY_PRUNER"
    return 0
  fi
  if ! "${prune_cmd[@]}"; then
    log "WARNING: history retention failed for $host; history left untouched where possible"
  fi
}

backup_one_host() {
  local host="$1"
  local host_dir="$BACKUP_ROOT/hosts/$host"
  local current_dir="$host_dir/current"
  local history_root="$host_dir/history"
  local history_run_dir="$history_root/$RUN_TIMESTAMP"
  local run_log_dir="$host_dir/run_logs"
  local state_dir="$host_dir/state"
  local latest_link="$host_dir/latest"
  local manifest_path="$host_dir/current_manifest.tsv"
  local partial_dir="$host_dir/.rsync-partial"
  local run_log_path="$run_log_dir/$RUN_TIMESTAMP.log"
  local source_spec=""
  local status=0
  local current_file_count=0
  local history_file_count=0
  local history_bytes=0

  mkdir -p "$current_dir" "$history_root" "$run_log_dir" "$state_dir" "$partial_dir"

  if [[ -n "$SOURCE_BASE" ]]; then
    source_spec="${SOURCE_BASE%/}/$host/"
    if [[ ! -d "${SOURCE_BASE%/}/$host" ]]; then
      printf '%s\t%s\tfailed\t0\t0\t0\tmissing local source\n' \
        "$RUN_TIMESTAMP" "$host" >> "$SUMMARY_FILE"
      log "Skipping $host: local test source not found at ${SOURCE_BASE%/}/$host"
      return 1
    fi
  else
    source_spec="${REMOTE_USER}@${host}:${REMOTE_ROOT%/}/"
  fi

  {
    printf 'run_timestamp=%s\n' "$RUN_TIMESTAMP"
    printf 'host=%s\n' "$host"
    printf 'source=%s\n' "$source_spec"
    printf 'destination=%s\n' "$current_dir"
    printf 'history_run_dir=%s\n' "$history_run_dir"
  } > "$run_log_path"

  log "Backing up $host"

  local -a rsync_cmd=(
    rsync
    -rlptz
    --checksum
    --delete
    --delete-delay
    --backup
    "--backup-dir=$history_run_dir"
    --partial
    "--partial-dir=$partial_dir"
    --itemize-changes
  )

  if [[ -z "$SOURCE_BASE" ]]; then
    rsync_cmd+=(-e "ssh $SSH_OPTIONS")
  fi

  rsync_cmd+=("$source_spec" "$current_dir/")

  local attempt=1
  local max_attempts=2
  while true; do
    if "${rsync_cmd[@]}" >> "$run_log_path" 2>&1; then
      break
    else
      status=$?
    fi

    if (( attempt < max_attempts )); then
      log "Rsync attempt $attempt failed for $host (exit $status); retrying once"
      printf 'retry_attempt=%s\nretry_exit=%s\n' "$((attempt + 1))" "$status" >> "$run_log_path"
      attempt=$((attempt + 1))
      sleep 2
      continue
    fi

    printf '%s\n' "$RUN_TIMESTAMP" > "$state_dir/last_failed_run.txt"
    printf '%s\t%s\tfailed\t0\t0\t0\trsync exit %s after %s attempts\n' \
      "$RUN_TIMESTAMP" "$host" "$status" "$attempt" >> "$SUMMARY_FILE"
    log "Backup failed for $host after $attempt attempts. See $run_log_path"
    return "$status"
  done

  write_current_manifest "$current_dir" "$manifest_path"
  ln -sfn "$current_dir" "$latest_link"
  printf '%s\n' "$RUN_TIMESTAMP" > "$state_dir/last_successful_run.txt"

  current_file_count=$(find "$current_dir" -type f | wc -l | tr -d ' ')
  prune_history_for_host "$host"
  if [[ -d "$history_run_dir" ]]; then
    history_file_count=$(find "$history_run_dir" -type f | wc -l | tr -d ' ')
    if [[ "$history_file_count" -gt 0 ]]; then
      history_bytes=$(du -sb "$history_run_dir" | awk '{print $1}')
    else
      remove_empty_history_dir_tree "$history_run_dir" "$history_root"
    fi
  fi

  printf '%s\t%s\tsuccess\t%s\t%s\t%s\tok\n' \
    "$RUN_TIMESTAMP" "$host" "$current_file_count" "$history_file_count" "$history_bytes" \
    >> "$SUMMARY_FILE"
  log "Backup completed for $host"
}

DEFAULT_BACKUP_ROOT="${DATAFLOW_ROOT}/CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/REMOTE_LOG_BACKUP"
DEFAULT_REMOTE_USER="rpcuser"
DEFAULT_REMOTE_ROOT="/home/rpcuser/logs"
DEFAULT_HOSTS=(mingo01 mingo02 mingo04)  # mingo03 is retired/unreachable
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
HISTORY_PRUNER="${LOG_BACKUP_HISTORY_PRUNER:-$SCRIPT_DIR/prune_log_backup_history.py}"
DEFAULT_SELECTION_CONFIG="${DATAFLOW_ROOT}/PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/SUPPORT/CONFIG_FILES/config_selection.yaml"

BACKUP_ROOT="${LOG_BACKUP_ROOT:-$DEFAULT_BACKUP_ROOT}"
REMOTE_USER="${LOG_BACKUP_REMOTE_USER:-$DEFAULT_REMOTE_USER}"
REMOTE_ROOT="${LOG_BACKUP_REMOTE_ROOT:-$DEFAULT_REMOTE_ROOT}"
SOURCE_BASE="${LOG_BACKUP_SOURCE_BASE:-}"
RUN_TIMESTAMP="${LOG_BACKUP_RUN_TIMESTAMP:-$(date -u '+%Y%m%dT%H%M%SZ')}"
SSH_OPTIONS="${LOG_BACKUP_SSH_OPTIONS:--o BatchMode=yes -o ConnectTimeout=20 -o ServerAliveInterval=30 -o ServerAliveCountMax=3}"
HISTORY_RETENTION_ENABLED="${LOG_BACKUP_HISTORY_RETENTION_ENABLED:-1}"
SELECTION_CONFIG="${LOG_BACKUP_SELECTION_CONFIG:-$DEFAULT_SELECTION_CONFIG}"
HISTORY_CONTEXT_MONTHS="${LOG_BACKUP_HISTORY_CONTEXT_MONTHS:-1}"

declare -a requested_hosts=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      require_option_value "$1" "${2:-}"
      requested_hosts+=("$2")
      shift 2
      ;;
    --root)
      require_option_value "$1" "${2:-}"
      BACKUP_ROOT="$2"
      shift 2
      ;;
    --source-base)
      require_option_value "$1" "${2:-}"
      SOURCE_BASE="$2"
      shift 2
      ;;
    --remote-user)
      require_option_value "$1" "${2:-}"
      REMOTE_USER="$2"
      shift 2
      ;;
    --remote-root)
      require_option_value "$1" "${2:-}"
      REMOTE_ROOT="$2"
      shift 2
      ;;
    --no-history-prune)
      HISTORY_RETENTION_ENABLED=0
      shift
      ;;
    -h|--help)
      show_help
      exit 0
      ;;
    --)
      shift
      while [[ $# -gt 0 ]]; do
        requested_hosts+=("$1")
        shift
      done
      ;;
    -*)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
    *)
      requested_hosts+=("$1")
      shift
      ;;
  esac
done

if [[ ${#requested_hosts[@]} -eq 0 ]]; then
  if [[ -n "${LOG_BACKUP_HOSTS:-}" ]]; then
    read -r -a requested_hosts <<< "${LOG_BACKUP_HOSTS}"
  else
    requested_hosts=("${DEFAULT_HOSTS[@]}")
  fi
fi

require_command rsync
require_command flock
if [[ -z "$SOURCE_BASE" ]]; then
  require_command ssh
fi

RUNTIME_DIR="$BACKUP_ROOT/runtime"
SUMMARY_DIR="$RUNTIME_DIR/run_summaries"
LOCK_DIR="$RUNTIME_DIR/locks"
LOCK_FILE="$LOCK_DIR/run_log_backup.lock"
SUMMARY_FILE="$SUMMARY_DIR/$RUN_TIMESTAMP.tsv"

mkdir -p "$BACKUP_ROOT/hosts" "$SUMMARY_DIR" "$LOCK_DIR"

exec {lock_fd}> "$LOCK_FILE"
if ! flock -n "$lock_fd"; then
  log "Another log-backup run is already in progress."
  exit 0
fi

{
  printf 'run_timestamp\thost\tstatus\tcurrent_files\thistory_files\thistory_bytes\tmessage\n'
} > "$SUMMARY_FILE"

failure_count=0
for host in "${requested_hosts[@]}"; do
  if [[ -z "$host" ]]; then
    continue
  fi
  if ! backup_one_host "$host"; then
    failure_count=$((failure_count + 1))
  fi
done

if [[ "$failure_count" -gt 0 ]]; then
  log "Finished with $failure_count host failure(s). Summary: $SUMMARY_FILE"
  exit 1
fi

log "Finished successfully. Summary: $SUMMARY_FILE"
