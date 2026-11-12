#!/usr/bin/env bash
# Purpose: Deploy managed station scripts after validating the changes with a dry run.

set -euo pipefail

station="${1:?usage: sync_station_scripts.sh STATION_NUMBER}"
case "$station" in 1|2|3|4) ;; *) echo "Invalid station number" >&2; exit 2 ;; esac
mode="${2:-}"
case "$mode" in ''|--dry-run|--allow-delete) ;; *) echo "Unknown option: $mode" >&2; exit 2 ;; esac

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../../.." && pwd -P)"
alias="mingo0${station}"
remote_dir=/home/rpcuser/station_automation_scripts
source_dir="$repo_root/FOR_MINGO_SYSTEMS/station_automation_scripts/"
excludes="$repo_root/CONTEXTUAL/CONFIG/CONTENTS/rsync/station-deploy-excludes.list"
ssh_command=(ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10)

# Check the destination before any command with --delete. Offline stations
# fail this job without affecting the other stations or the simulation.
"${ssh_command[@]}" "$alias" "test \"\$(id -un)\" = rpcuser && test -d '$remote_dir' && command -v rsync >/dev/null" || {
    echo "Station $alias is unavailable or its deployment path/user is wrong" >&2
    exit 1
}
dry_run_output="$(rsync -avzn --delete --itemize-changes --exclude-from="$excludes" -e "${ssh_command[*]}" \
    "$source_dir" "rpcuser@$alias:$remote_dir/")" || {
    echo "Station $alias deployment dry-run failed; no files transferred" >&2
    exit 1
}
deletions="$(printf '%s\n' "$dry_run_output" | grep -c '^\*deleting' || true)"
echo "Station $alias deployment dry-run passed; proposed deletions=$deletions"
if [[ "$mode" == --dry-run ]]; then
    printf '%s\n' "$dry_run_output"
    exit 0
fi
if (( deletions > 0 )) && [[ "$mode" != --allow-delete ]]; then
    echo "Review proposed deletions with --dry-run before using --allow-delete manually" >&2
    exit 1
fi
rsync -avz --delete --exclude-from="$excludes" -e "${ssh_command[*]}" \
    "$source_dir" "rpcuser@$alias:$remote_dir/"
"${ssh_command[@]}" "$alias" "bash '$remote_dir/trigger/install_selftrigger_cron.sh'"
