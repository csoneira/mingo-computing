#!/usr/bin/env bash
# Purpose: Auto clear swap if idle.

set -euo pipefail

USAGE_HELP=$(
cat <<'DOC'
Usage notes:
  - This script expects to run as the regular pipeline user (mingo) while calling
    swapoff/swapon via passwordless sudo.
  - Ensure sudoers (e.g. /etc/sudoers.d/swap-clear) contains:
        mingo ALL=(root) NOPASSWD:/usr/sbin/swapoff,/usr/sbin/swapon
    (Adjust paths if your binaries live elsewhere.)
  - Test with `sudo -n /usr/sbin/swapoff -a` from the shell. Once that works,
    cron can invoke this script without prompting for a password.
DOC
)

LOG_TAG="swap-autoclear"

# Thresholds (adjust to taste)
MIN_MEM_AVAILABLE_KB=4000000   # ~4 GiB; only clear swap if we have at least this much available
MIN_SWAP_USED_KB=100000        # ~100 MiB; only act if at least this amount is used
MAX_LOAD_AVG=3                 # 1-minute load average must be below this to be considered "idle"

# Emergency override:
# If swap is critically high and enough RAM headroom exists, clear swap even under high load.
CRITICAL_SWAP_USED_PCT=85
MIN_MEM_HEADROOM_AFTER_CLEAR_KB=1500000  # ~1.5 GiB must remain available after swapping pages back in

# Read memory info
mem_avail_kb=$(awk '/MemAvailable/ {print $2}' /proc/meminfo)
swap_total_kb=$(awk '/SwapTotal/ {print $2}' /proc/meminfo)
swap_free_kb=$(awk '/SwapFree/  {print $2}' /proc/meminfo)
swap_used_kb=$((swap_total_kb - swap_free_kb))
swap_used_pct=0
if [ "$swap_total_kb" -gt 0 ]; then
    swap_used_pct=$((100 * swap_used_kb / swap_total_kb))
fi

# Read 1-minute load average
load_avg_1=$(awk '{print $1}' /proc/loadavg)

# Check whether load is below the configured maximum
load_ok=$(awk -v load="$load_avg_1" -v max="$MAX_LOAD_AVG" \
    'BEGIN { if (load < max) print "yes"; else print "no"; }')

# Conditions:
# 1) Enough available memory
if [ "$mem_avail_kb" -lt "$MIN_MEM_AVAILABLE_KB" ]; then
    # Not enough free RAM; do nothing
    echo "Not enough available memory (${mem_avail_kb}kB); skipping swap clear"
    exit 0
fi

# 2) Swap usage high enough to care
if [ "$swap_used_kb" -lt "$MIN_SWAP_USED_KB" ]; then
    # Swap usage is small; do nothing
    echo "Swap usage low (${swap_used_kb}kB); skipping swap clear"
    exit 0
fi

# 3) Low CPU load -> system "idle"
#    If not idle, allow an emergency clear only when swap is critically high
#    and there is enough memory headroom to safely pull swapped pages back.
emergency_clear="no"
mem_headroom_after_clear_kb=$((mem_avail_kb - swap_used_kb))
if [ "$load_ok" != "yes" ]; then
    if [ "$swap_used_pct" -ge "$CRITICAL_SWAP_USED_PCT" ] && [ "$mem_headroom_after_clear_kb" -ge "$MIN_MEM_HEADROOM_AFTER_CLEAR_KB" ]; then
        emergency_clear="yes"
    else
        echo "System load high (Load1=${load_avg_1}) and no emergency condition (SwapUsed=${swap_used_pct}% MemHeadroomAfterClear=${mem_headroom_after_clear_kb}kB); skipping swap clear"
        exit 0
    fi
fi

run_swap_cmd() {
    local -a cmd=("$@")
    if [[ ${EUID:-0} -eq 0 ]]; then
        "${cmd[@]}"
    else
        if ! sudo -n "${cmd[@]}"; then
            logger -t "$LOG_TAG" "Failed to run ${cmd[*]} via sudo (passwordless sudo required)"
            echo "Failed to execute ${cmd[*]} via sudo; ensure passwordless sudo is configured."
            exit 1
        fi
    fi
}

# All conditions satisfied: clear swap
if [ "$emergency_clear" = "yes" ]; then
    logger -t "$LOG_TAG" "Clearing swap (emergency override): MemAvailable=${mem_avail_kb}kB SwapUsed=${swap_used_kb}kB (${swap_used_pct}%) MemHeadroomAfterClear=${mem_headroom_after_clear_kb}kB Load1=${load_avg_1}"
else
    logger -t "$LOG_TAG" "Clearing swap: MemAvailable=${mem_avail_kb}kB SwapUsed=${swap_used_kb}kB (${swap_used_pct}%) Load1=${load_avg_1}"
fi
SWAPOFF_BIN=${SWAPOFF_BIN:-$(command -v swapoff 2>/dev/null || echo /sbin/swapoff)}
SWAPON_BIN=${SWAPON_BIN:-$(command -v swapon 2>/dev/null || echo /sbin/swapon)}
run_swap_cmd "$SWAPOFF_BIN" -a
run_swap_cmd "$SWAPON_BIN" -a
logger -t "$LOG_TAG" "Swap cleared: SwapUsed was ${swap_used_kb}kB (${swap_used_pct}%)"
