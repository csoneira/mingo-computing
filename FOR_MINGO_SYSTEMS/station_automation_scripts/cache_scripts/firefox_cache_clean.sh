#!/usr/bin/env bash
# Purpose: Conservative Firefox cache cleanup to avoid inode exhaustion.

# Conservative Firefox cache cleanup to avoid inode exhaustion.
# Only touches files under $HOME/.cache/mozilla/firefox/*/cache2/entries/

PATH=/usr/bin:/bin

TAG="firefox-cache-clean"
LOCK_FILE="/tmp/firefox-cache-clean.lock"
SAMPLE_MAX=5

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
  shift
fi
if [[ $# -ne 0 ]]; then
  printf 'Usage: %s [--dry-run]\n' "${0##*/}" >&2
  exit 2
fi

log() {
  logger -t "$TAG" -- "$*"
}

echo_if() {
  if (( DRY_RUN == 1 )); then
    printf '%s\n' "$*"
  fi
}

# Single-instance lock to avoid concurrent runs.
exec 200>"$LOCK_FILE" || { log "Failed to open lock file: $LOCK_FILE"; exit 1; }
if ! flock -n 200; then
  log "Another instance is running; exiting."
  exit 0
fi

# Defensive HOME checks.
if [[ -z "${HOME:-}" || "$HOME" == "/" ]]; then
  log "Refusing to run: HOME is empty or '/' (HOME='$HOME')."
  exit 1
fi
if [[ ! -d "$HOME" ]]; then
  log "Refusing to run: HOME does not exist (HOME='$HOME')."
  exit 1
fi

# Skip if we cannot confidently check for Firefox.
if ! command -v pgrep >/dev/null 2>&1; then
  log "pgrep not available; skipping cleanup."
  exit 0
fi
if pgrep -u "$(id -u)" -x firefox >/dev/null 2>&1; then
  log "Firefox is running for uid $(id -u); skipping cleanup."
  exit 0
fi

# Build list of cache entries directories (do not follow symlinks).
shopt -s nullglob
entries_dirs=( "$HOME/.cache/mozilla/firefox"/*/cache2/entries )
shopt -u nullglob

valid_dirs=()
for dir in "${entries_dirs[@]}"; do
  if [[ -d "$dir" && ! -L "$dir" ]]; then
    valid_dirs+=("$dir")
  fi
done

if [[ ${#valid_dirs[@]} -eq 0 ]]; then
  log "Refusing to run: no cache2/entries directories found."
  exit 1
fi

sanitize_int() {
  local name="$1"
  local default="$2"
  local min="$3"
  local max="$4"
  local val="${!name:-$default}"

  if [[ ! "$val" =~ ^[0-9]+$ ]]; then
    log "Invalid $name='$val'; using default $default."
    val="$default"
  fi
  if (( val < min || val > max )); then
    log "Out-of-range $name='$val'; using default $default."
    val="$default"
  fi

  printf '%s' "$val"
}

FIREFOX_CACHE_DAYS="$(sanitize_int FIREFOX_CACHE_DAYS 7 1 3650)"
FIREFOX_INODE_THRESHOLD="$(sanitize_int FIREFOX_INODE_THRESHOLD 95 1 100)"
FIREFOX_CACHE_KEEP_NEWEST="$(sanitize_int FIREFOX_CACHE_KEEP_NEWEST 5000 1 100000000)"

DELETE_FLAG=1
if (( DRY_RUN == 1 )); then
  DELETE_FLAG=0
fi

log "Starting cleanup (dry-run=$DRY_RUN, days=$FIREFOX_CACHE_DAYS, threshold=${FIREFOX_INODE_THRESHOLD}%, keep_newest=$FIREFOX_CACHE_KEEP_NEWEST)."

process_find() {
  local label="$1"
  local delete_flag="$2"
  shift 2

  local count=0
  local -a sample=()

  while IFS= read -r -d '' path; do
    ((count++))
    if (( ${#sample[@]} < SAMPLE_MAX )); then
      sample+=("$path")
    fi
    if (( delete_flag == 1 )); then
      rm -f -- "$path"
    fi
  done < <(find -P "${valid_dirs[@]}" -mindepth 1 -maxdepth 1 -type f "$@" -print0)

  log "$label: matched $count file(s)."
  if (( DRY_RUN == 1 )); then
    echo_if "$label: $count file(s) would be deleted."
    if (( ${#sample[@]} > 0 )); then
      echo_if "Sample paths:"
      for s in "${sample[@]}"; do
        echo_if "  $s"
      done
    fi
  fi
}

get_inode_usage() {
  local use
  use=$(df -Pi "$HOME" 2>/dev/null | awk 'NR==2 {gsub(/%/,"",$5); print $5}')
  if [[ "$use" =~ ^[0-9]+$ ]]; then
    printf '%s' "$use"
  else
    printf ''
  fi
}

cleanup_keep_newest() {
  local label="Inode pressure cleanup (keep newest $FIREFOX_CACHE_KEEP_NEWEST)"
  local total=0
  local deleted=0
  local -a sample=()

  while IFS= read -r -d '' line; do
    ((total++))
    if (( total <= FIREFOX_CACHE_KEEP_NEWEST )); then
      continue
    fi
    local path="${line#* }"
    ((deleted++))
    if (( ${#sample[@]} < SAMPLE_MAX )); then
      sample+=("$path")
    fi
    if (( DELETE_FLAG == 1 )); then
      rm -f -- "$path"
    fi
  done < <(find -P "${valid_dirs[@]}" -mindepth 1 -maxdepth 1 -type f -printf '%T@ %p\0' | sort -z -nr)

  log "$label: deleted $deleted file(s) after keeping newest $FIREFOX_CACHE_KEEP_NEWEST (total $total)."
  if (( DRY_RUN == 1 )); then
    echo_if "$label: $deleted file(s) would be deleted after keeping newest $FIREFOX_CACHE_KEEP_NEWEST (total $total)."
    if (( ${#sample[@]} > 0 )); then
      echo_if "Sample paths:"
      for s in "${sample[@]}"; do
        echo_if "  $s"
      done
    fi
  fi
}

# Policy A: age-based cleanup (default 7 days).
process_find "Age-based cleanup (> ${FIREFOX_CACHE_DAYS} days)" "$DELETE_FLAG" -mtime "+${FIREFOX_CACHE_DAYS}"

# Policy B: inode pressure mode.
inode_use="$(get_inode_usage)"
if [[ -z "$inode_use" ]]; then
  log "Unable to determine inode usage; skipping inode pressure mode."
  exit 0
fi

if (( inode_use >= FIREFOX_INODE_THRESHOLD )); then
  log "Inode usage ${inode_use}% >= ${FIREFOX_INODE_THRESHOLD}%; entering pressure mode."
  process_find "Inode pressure cleanup (> 1 day)" "$DELETE_FLAG" -mtime "+1"

  if (( DRY_RUN == 1 )); then
    echo_if "Dry-run: would re-check inode usage after deletion."
    echo_if "If still >= ${FIREFOX_INODE_THRESHOLD}%, would delete all but newest ${FIREFOX_CACHE_KEEP_NEWEST} files."
    exit 0
  fi

  inode_use="$(get_inode_usage)"
  if [[ -z "$inode_use" ]]; then
    log "Unable to determine inode usage after cleanup; skipping keep-newest step."
    exit 0
  fi

  if (( inode_use >= FIREFOX_INODE_THRESHOLD )); then
    cleanup_keep_newest
  else
    log "Inode usage after cleanup is ${inode_use}%; below threshold."
  fi
fi

exit 0
