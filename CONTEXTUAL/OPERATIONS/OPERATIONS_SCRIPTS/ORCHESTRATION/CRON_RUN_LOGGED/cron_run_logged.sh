#!/usr/bin/env bash
# Purpose: Run a scheduled command, log its output, and record its exit status.

# Walk up from this file to find the checkout unless DATAFLOW_ROOT is set.
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
# Run a cron command while avoiding empty destination logs.

set -uo pipefail

if [[ $# -lt 3 || "$2" != "--" ]]; then
  echo "Usage: cron_run_logged.sh LOG_PATH -- COMMAND [ARG ...]" >&2
  exit 2
fi

log_path="$1"
shift 2

started_epoch="$(date +%s)"
started_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
command_text="$(printf '%q ' "$@")"
marker_path="$(mktemp "${TMPDIR:-/tmp}/dataflow_cron_run_output.XXXXXX")"
trap 'rm -f "$marker_path"' EXIT

/usr/bin/env CRON_LOG_PATH="$log_path" "$@" 2>&1 |
  {
    first_line=true
    while IFS= read -r line || [[ -n "$line" ]]; do
      if $first_line; then
        printf '1\n' >"$marker_path"
        mkdir -p "$(dirname "$log_path")"
        printf '%s [CRON_RUN] command=%s\n' "$started_at" "$command_text" >>"$log_path"
        first_line=false
      fi
      printf '%s [CRON_OUTPUT] %s\n' "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" "$line" >>"$log_path"
    done
  }
rc="${PIPESTATUS[0]}"

silent_expected_lock_contention=false
if [[ $rc -eq 1 && ! -s "$marker_path" && "${1:-}" == */flock ]]; then
  silent_expected_lock_contention=true
fi

finished_epoch="$(date +%s)"
elapsed_seconds=$((finished_epoch - started_epoch))
if [[ "$silent_expected_lock_contention" != true && ( $rc -ne 0 || -s "$marker_path" ) ]]; then
  mkdir -p "$(dirname "$log_path")"
  if [[ ! -s "$marker_path" ]]; then
    printf '%s [CRON_RUN] command=%s\n' "$started_at" "$command_text" >>"$log_path"
  fi
  run_status=ok
  if [[ $rc -ne 0 ]]; then run_status=failed; fi
  printf '%s [CRON_RUN] status=%s exit_code=%d elapsed_seconds=%d command=%s\n' \
    "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" "$run_status" "$rc" "$elapsed_seconds" "$command_text" >>"$log_path"
elif [[ ! -s "$marker_path" && -f "$log_path" && ! -s "$log_path" ]]; then
  rm -f "$log_path"
fi

# One atomic latest-result CSV per scheduled job. The existing error finder
# still owns issue classification; these files provide current exit status.
runtime_root="${DATAFLOW_ROOT}/CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME"
case "$log_path" in
  "$runtime_root/CRON_LOGS/"*) relative="${log_path#"$runtime_root/CRON_LOGS/"}" ;;
  *) relative="$(basename -- "$log_path")" ;;
esac
status_file="$runtime_root/CRON_STATUS/${relative%.log}.csv"
mkdir -p "$(dirname -- "$status_file")"
status_tmp="$(mktemp "${status_file}.XXXXXX")"
status=ok
if [[ $rc -ne 0 ]]; then status=failed; fi
if [[ "$silent_expected_lock_contention" == true ]]; then status=skipped_lock; fi
printf 'started_at_utc,finished_at_utc,exit_code,status\n%s,%s,%d,%s\n' \
  "$started_at" "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$rc" "$status" >"$status_tmp"
chmod 0600 "$status_tmp"
mv -f -- "$status_tmp" "$status_file"

exit "$rc"
