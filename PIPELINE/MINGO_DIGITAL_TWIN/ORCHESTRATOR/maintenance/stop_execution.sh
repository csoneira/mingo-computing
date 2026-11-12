#!/usr/bin/env bash
# Purpose: Stop runaway or duplicate digital-twin processes and clear stale scheduler locks.

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
# Emergency process guard for cron:
# if the pipeline accumulates too many duplicated/pending jobs, stop them.

set -u

BASE_DIR="${DATAFLOW_ROOT}"
LOCK_FILE="${BASE_DIR}/CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/LOCKS/cron/stop_execution.lock"
LOG_DIR="${BASE_DIR}/CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/CRON_LOGS/ANCILLARY/CLEANERS"
INTERNAL_LOG="${LOG_DIR}/stop_execution_internal.log"

# When launched through cron_run_logged.sh, stdout is already retained in the
# declared cron log. Keep the internal file only for standalone invocations.
if [[ -n "${CRON_LOG_PATH:-}" ]]; then
  INTERNAL_LOG="/dev/stdout"
else
  mkdir -p "${LOG_DIR}"
fi
mkdir -p "$(dirname "${LOCK_FILE}")"

{
  flock -n 9 || exit 0

  ts="$(date '+%Y-%m-%d %H:%M:%S')"
  user_name="${USER:-$(id -un)}"
  proc_threshold="${PROC_THRESHOLD:-25}"
  dup_threshold="${DUP_THRESHOLD:-5}"
  load_factor="${LOAD_FACTOR:-2.0}"
  grace_seconds="${GRACE_SECONDS:-6}"
  dry_run="${DRY_RUN:-0}"

  cpu_count="$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 1)"
  load_1m="$(awk '{print $1}' /proc/loadavg 2>/dev/null || echo 0)"
  # Cron may inherit a locale whose decimal separator is a comma. Keep both
  # formatting and comparison in the C numeric locale.
  load_trigger="$(LC_ALL=C awk -v c="${cpu_count}" -v f="${load_factor}" 'BEGIN { printf "%.2f", c * f }')"

  cleanup_dead_run_step_lock() {
    local lock_dir="${BASE_DIR}/CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/LOCKS/simulation/run_step_continuous.lock"
    local pid_file="${lock_dir}/pid"
    local lock_pid=""
    local lock_mtime=""
    local lock_age_s=0
    local now_epoch
    local reason="missing_pid"

    [ -d "${lock_dir}" ] || return 0

    lock_mtime="$(stat -c %Y "${lock_dir}" 2>/dev/null || true)"
    if [[ "${lock_mtime}" =~ ^[0-9]+$ ]]; then
      now_epoch="$(date +%s)"
      lock_age_s=$(( now_epoch - lock_mtime ))
      [ "${lock_age_s}" -lt 0 ] && lock_age_s=0
    fi

    if [ -f "${pid_file}" ]; then
      lock_pid="$(tr -d '[:space:]' < "${pid_file}" 2>/dev/null || true)"
    else
      # Avoid racing with run_step right after mkdir but before writing pid.
      [ "${lock_age_s}" -lt 120 ] && return 0
    fi

    if [[ -n "${lock_pid}" && "${lock_pid}" =~ ^[0-9]+$ ]] && kill -0 "${lock_pid}" 2>/dev/null; then
      return 0
    fi

    if [[ -n "${lock_pid}" ]]; then
      if [[ "${lock_pid}" =~ ^[0-9]+$ ]]; then
        reason="dead_pid=${lock_pid}"
      else
        # Also avoid racing with partial writes to pid file.
        [ "${lock_age_s}" -lt 120 ] && return 0
        reason="invalid_pid=${lock_pid}"
      fi
    fi

    rm -f "${pid_file}" 2>/dev/null || true
    rmdir "${lock_dir}" 2>/dev/null || rm -rf "${lock_dir}" 2>/dev/null || true
    echo "[${ts}] Cleaned stale run_step lock (${reason}, age_s=${lock_age_s}) path=${lock_dir}"
  }

  # Self-heal dead run_step lock dirs so continuous simulation can resume.
  cleanup_dead_run_step_lock

  cmd_invokes_pattern() {
    local cmd="$1"
    local pattern="$2"
    local c1="" c2="" c3="" c4=""

    read -r c1 c2 c3 c4 _ <<< "${cmd}"

    [ "${c1}" = "${pattern}" ] && return 0

    if [[ "${c1}" == */bash || "${c1}" == "bash" ]]; then
      [ "${c2:-}" = "${pattern}" ] && return 0
      return 1
    fi

    if [[ "${c1}" == *python* ]]; then
      if [[ "${c2:-}" == -* ]]; then
        [ "${c3:-}" = "${pattern}" ] && return 0
      else
        [ "${c2:-}" = "${pattern}" ] && return 0
      fi
      return 1
    fi

    if [[ "${c1}" == */env || "${c1}" == "env" ]]; then
      if [[ "${c2:-}" == *python* ]]; then
        if [[ "${c3:-}" == -* ]]; then
          [ "${c4:-}" = "${pattern}" ] && return 0
        else
          [ "${c3:-}" = "${pattern}" ] && return 0
        fi
      fi
      return 1
    fi

    return 1
  }

  declare -a patterns=(
    "${DATAFLOW_ROOT}/PIPELINE/MINGO_DIGITAL_TWIN/ORCHESTRATOR/core/run_step.sh"
    "${DATAFLOW_ROOT}/PIPELINE/MINGO_DIGITAL_TWIN/MASTER_STEPS/STEP_0/step_0_setup_to_blank.py"
    "${DATAFLOW_ROOT}/PIPELINE/MINGO_DIGITAL_TWIN/MASTER_STEPS/STEP_FINAL/step_final_daq_to_station_dat.py"
    "${DATAFLOW_ROOT}/PIPELINE/MINGO_DIGITAL_TWIN/ORCHESTRATOR/maintenance/sim_maintenance.py"
  )

  declare -A pid_to_cmd=()
  declare -A pid_to_key=()
  for pattern in "${patterns[@]}"; do
    while IFS= read -r line; do
      [ -z "${line}" ] && continue
      pid="${line%% *}"
      cmd="${line#* }"
      [ -z "${pid}" ] && continue
      if ! cmd_invokes_pattern "${cmd}" "${pattern}"; then
        continue
      fi
      pid_to_cmd["${pid}"]="${cmd}"
      # Keep duplicate accounting tied to the actual pipeline target that matched
      # this PID, not to wrapper executables like resource_gate.sh.
      [ -z "${pid_to_key[${pid}]-}" ] && pid_to_key["${pid}"]="${pattern}"
    done < <(pgrep -u "${user_name}" -f -a "${pattern}" || true)
  done

  unset "pid_to_cmd[$$]" 2>/dev/null || true
  unset "pid_to_cmd[$PPID]" 2>/dev/null || true
  unset "pid_to_key[$$]" 2>/dev/null || true
  unset "pid_to_key[$PPID]" 2>/dev/null || true

  declare -A dup_counts=()
  for pid in "${!pid_to_cmd[@]}"; do
    key="${pid_to_key[${pid}]-}"
    if [ -z "${key}" ]; then
      cmd="${pid_to_cmd[${pid}]}"
      read -r a1 a2 a3 a4 _ <<< "${cmd}"
      key="${a1}"
      if [[ "${a1}" == *python* ]]; then
        if [[ "${a2:-}" == -* ]]; then
          key="${a3:-${a1}}"
        else
          key="${a2:-${a1}}"
        fi
      elif [[ "${a1}" == */bash || "${a1}" == "bash" ]]; then
        if [ "${a2:-}" = "-c" ]; then
          if [[ "${a3:-}" == */bash || "${a3:-}" == "bash" ]]; then
            key="${a4:-${a1}}"
          else
            key="${a3:-${a1}}"
          fi
        else
          key="${a2:-${a1}}"
        fi
      fi
      [[ "${key}" == -* || -z "${key}" ]] && key="${a1}"
    fi
    dup_counts["${key}"]=$(( ${dup_counts["${key}"]:-0} + 1 ))
  done

  dup_trip=0
  dup_summary=""
  for key in "${!dup_counts[@]}"; do
    count="${dup_counts[${key}]}"
    if [ "${count}" -ge "${dup_threshold}" ]; then
      dup_trip=1
      dup_summary="${dup_summary}${key}=${count}; "
    fi
  done

  match_count="${#pid_to_cmd[@]}"
  load_trip="$(LC_ALL=C awk -v l="${load_1m}" -v t="${load_trigger}" 'BEGIN {print (l >= t) ? 1 : 0}')"

  should_kill=0
  reasons=()
  if [ "${match_count}" -ge "${proc_threshold}" ]; then
    should_kill=1
    reasons+=("match_count=${match_count}>=${proc_threshold}")
  fi
  if [ "${load_trip}" -eq 1 ] && [ "${match_count}" -gt 0 ]; then
    should_kill=1
    reasons+=("load_1m=${load_1m}>=${load_trigger}")
  fi
  if [ "${dup_trip}" -eq 1 ]; then
    should_kill=1
    reasons+=("duplicates>=${dup_threshold}: ${dup_summary}")
  fi

  if [ "${should_kill}" -eq 0 ]; then
    echo "[${ts}] Healthy: matched=${match_count}, load_1m=${load_1m}, cpu=${cpu_count}"
    exit 0
  fi

  echo "[${ts}] Triggered emergency stop (${reasons[*]})"
  if [ "${match_count}" -eq 0 ]; then
    echo "[${ts}] No matching processes found after trigger; exiting."
    exit 0
  fi

  pids=( "${!pid_to_cmd[@]}" )
  IFS=$'\n' pids=( $(printf '%s\n' "${pids[@]}" | sort -n) )
  unset IFS

  echo "[${ts}] Candidate PID count: ${#pids[@]}"
  for pid in "${pids[@]}"; do
    echo "[${ts}] PID=${pid} CMD=${pid_to_cmd[${pid}]}"
  done

  if [ "${dry_run}" = "1" ]; then
    echo "[${ts}] DRY_RUN=1, no process terminated."
    exit 0
  fi

  kill -TERM "${pids[@]}" 2>/dev/null || true
  sleep "${grace_seconds}"

  still_running=()
  for pid in "${pids[@]}"; do
    if kill -0 "${pid}" 2>/dev/null; then
      still_running+=( "${pid}" )
    fi
  done

  if [ "${#still_running[@]}" -gt 0 ]; then
    echo "[${ts}] Escalating to SIGKILL for ${#still_running[@]} PIDs."
    kill -KILL "${still_running[@]}" 2>/dev/null || true
  fi

  # If run_step was terminated abruptly, remove stale pid lock promptly.
  cleanup_dead_run_step_lock

  echo "[${ts}] stop_execution.sh completed."
} 9>"${LOCK_FILE}" >> "${INTERNAL_LOG}" 2>&1
