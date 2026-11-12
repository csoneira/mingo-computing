#!/usr/bin/env bash
# Purpose: Kill running bash/python scripts referenced in the managed analysis-PC cron template without touching unrelated processes.

# Kill running bash/python scripts referenced in the managed analysis-PC cron template without touching unrelated processes.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR"
while [[ "$REPO_ROOT" != "/" && ! -f "$REPO_ROOT/CONTEXTUAL/CONFIG/CONTENTS/cron/analysis_pc.crontab" ]]; do
  REPO_ROOT="$(dirname "$REPO_ROOT")"
done

if [[ "$REPO_ROOT" == "/" ]]; then
  echo "Unable to locate repository root from: $SCRIPT_DIR" >&2
  exit 1
fi

CRON_FILE="$REPO_ROOT/CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/SETUP/analysis_pc.crontab"
this_pid=$$

if [[ ! -f "$CRON_FILE" ]]; then
  echo "Cron file not found: $CRON_FILE" >&2
  exit 1
fi

strip_cron_fields() {
  awk '{ $1=$2=$3=$4=$5=""; sub(/^ +/,""); print }' <<<"$1"
}

clean_token() {
  local token="$1"
  token="${token//$'\r'/}"
  token="${token#\"}"
  token="${token%\"}"
  token="${token#\'}"
  token="${token%\'}"
  while [[ "$token" == [\(\[\{]* ]]; do
    token="${token:1}"
  done
  while [[ "$token" == *[\)\]\}\,\;] ]]; do
    token="${token%?}"
  done
  printf '%s' "$token"
}

expand_path_token() {
  local token="$1"
  local expanded="$token"
  if [[ "$expanded" == *'$'* ]]; then
    expanded="$(eval "printf '%s' \"$expanded\"")"
  fi
  if [[ "$expanded" != /* && "$expanded" == */* ]]; then
    expanded="$REPO_ROOT/$expanded"
  fi
  printf '%s' "$expanded"
}

declare -A scripts=()
declare -A script_names=()

while IFS= read -r line; do
  trimmed="${line#"${line%%[![:space:]]*}"}"
  [[ -z "$trimmed" || "$trimmed" == \#* ]] && continue

  if [[ "$trimmed" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]]; then
    eval "export $trimmed"
    continue
  fi

  command="$(strip_cron_fields "$trimmed")"
  [[ -z "$command" ]] && continue

  read -ra parts <<<"$command"
  for part in "${parts[@]}"; do
    token="$(clean_token "$part")"
    [[ -z "$token" ]] && continue
    if [[ "$token" != *.sh && "$token" != *.py ]]; then
      continue
    fi
    expanded="$(expand_path_token "$token")"
    scripts["$expanded"]=1
    script_names["$(basename "$expanded")"]=1
  done
done < "$CRON_FILE"

if (( ${#scripts[@]} == 0 )); then
  echo "No target scripts found in $CRON_FILE."
  exit 0
fi

declare -A kill_list=()
for script in "${!scripts[@]}"; do
  [[ -z "$script" || "$script" == *'$'* ]] && continue
  while IFS= read -r pid; do
    [[ -z "$pid" || "$pid" == "$this_pid" ]] && continue
    kill_list["$pid"]="$script"
  done < <(pgrep -f -- "$script" || true)
done

for script_name in "${!script_names[@]}"; do
  [[ -z "$script_name" ]] && continue
  while IFS= read -r pid; do
    [[ -z "$pid" || "$pid" == "$this_pid" ]] && continue
    cmdline="$(ps -p "$pid" -o args= 2>/dev/null || true)"
    [[ -z "$cmdline" ]] && continue
    if [[ "$cmdline" == *"/$script_name"* || "$cmdline" == *" $script_name "* || "$cmdline" == *" $script_name" ]]; then
      kill_list["$pid"]="${kill_list[$pid]:-$script_name}"
    fi
  done < <(pgrep -f -- "$script_name" || true)
done

if (( ${#kill_list[@]} == 0 )); then
  echo "No matching processes found for scripts in $CRON_FILE."
  exit 0
fi

for pid in "${!kill_list[@]}"; do
  script="${kill_list[$pid]}"
  if kill "$pid" 2>/dev/null; then
    echo "Sent SIGTERM to PID $pid (script match: $script)"
  else
    echo "Failed to kill PID $pid (script match: $script)" >&2
  fi
done
