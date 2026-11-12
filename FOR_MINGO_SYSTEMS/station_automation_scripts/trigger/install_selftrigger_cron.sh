#!/usr/bin/env bash
# Purpose: Install the managed hourly self-trigger cron entry while preserving unrelated entries.

set -euo pipefail

# Install only the managed hourly self-trigger entry, preserving every other
# station crontab line. This is safe to run repeatedly after station-script sync.
current_cron="$(mktemp)"
updated_cron="$(mktemp)"
trap 'rm -f "$current_cron" "$updated_cron"' EXIT

crontab -l >"$current_cron" 2>/dev/null || :

# Remove both the current station-automation entry and legacy trigger paths,
# including commented-out old schedules, then append one canonical schedule.
awk '
    index($0, "activateST.sh") == 0 { print }
' "$current_cron" >"$updated_cron"

cat >>"$updated_cron" <<'CRON'
# SelfTrigger for 1 minute each hour. Minute 17 avoids the DAQ watchdog at :00/:30.
17 * * * * /home/rpcuser/station_automation_scripts/trigger/activateST.sh
CRON

crontab "$updated_cron"

count="$(crontab -l | awk '
    $1 == "17" && $2 == "*" && $3 == "*" && $4 == "*" && $5 == "*" &&
    $0 ~ /\/station_automation_scripts\/trigger\/activateST\.sh$/ { count++ }
    END { print count + 0 }
')"
if [[ "$count" != 1 ]]; then
    echo "Expected exactly one hourly self-trigger cron entry; found $count" >&2
    exit 1
fi

echo "Installed one-minute hourly self-trigger schedule at minute 17."
