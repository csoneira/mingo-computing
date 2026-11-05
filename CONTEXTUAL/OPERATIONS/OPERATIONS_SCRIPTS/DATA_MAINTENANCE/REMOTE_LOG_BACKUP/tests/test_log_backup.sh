#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNNER_PATH="$(cd "$SCRIPT_DIR/.." && pwd)/run_log_backup.sh"

fail() {
  echo "TEST FAILED: $*" >&2
  exit 1
}

assert_file_exists() {
  local path="$1"
  [[ -f "$path" ]] || fail "Expected file to exist: $path"
}

assert_dir_exists() {
  local path="$1"
  [[ -d "$path" ]] || fail "Expected directory to exist: $path"
}

assert_file_contains() {
  local path="$1"
  local needle="$2"
  grep -Fq "$needle" "$path" || fail "Expected '$needle' in $path"
}

assert_trees_equal() {
  local left="$1"
  local right="$2"
  diff -r "$left" "$right" >/dev/null || fail "Trees differ: $left vs $right"
}

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

source_root="$tmpdir/source"
backup_root="$tmpdir/backup"

mkdir -p \
  "$source_root/mingo01/done" \
  "$source_root/mingo02/done"

printf 'daq-v1\n' > "$source_root/mingo01/daq_restart.log"
printf 'clean-v1\n' > "$source_root/mingo01/clean_Flow0.txt"
printf 'flow-v1\n' > "$source_root/mingo01/Flow0_2026-04-23.log"
printf 'done-v0\n' > "$source_root/mingo01/done/Flow0_2026-04-22.log"
printf 'rates-v1\n' > "$source_root/mingo02/rates_2026-04-23.log"

LOG_BACKUP_ROOT="$backup_root" \
LOG_BACKUP_SOURCE_BASE="$source_root" \
LOG_BACKUP_HOSTS="mingo01 mingo02" \
LOG_BACKUP_RUN_TIMESTAMP="20260423T090000Z" \
bash "$RUNNER_PATH"

assert_trees_equal "$source_root/mingo01" "$backup_root/hosts/mingo01/current"
assert_trees_equal "$source_root/mingo02" "$backup_root/hosts/mingo02/current"
assert_file_exists "$backup_root/hosts/mingo01/current_manifest.tsv"
assert_dir_exists "$backup_root/hosts/mingo01/run_logs"
[[ -L "$backup_root/hosts/mingo01/latest" ]] || fail "Expected latest symlink for mingo01"

printf 'daq-v2\n' > "$source_root/mingo01/daq_restart.log"
mv "$source_root/mingo01/Flow0_2026-04-23.log" "$source_root/mingo01/done/Flow0_2026-04-23.log"
rm -f "$source_root/mingo01/clean_Flow0.txt"
printf 'new-v1\n' > "$source_root/mingo01/new_file.log"
printf 'rates-v2\n' > "$source_root/mingo02/rates_2026-04-23.log"

LOG_BACKUP_ROOT="$backup_root" \
LOG_BACKUP_SOURCE_BASE="$source_root" \
LOG_BACKUP_HOSTS="mingo01 mingo02" \
LOG_BACKUP_RUN_TIMESTAMP="20260423T210000Z" \
bash "$RUNNER_PATH"

assert_trees_equal "$source_root/mingo01" "$backup_root/hosts/mingo01/current"
assert_trees_equal "$source_root/mingo02" "$backup_root/hosts/mingo02/current"
assert_file_exists "$backup_root/hosts/mingo01/history/20260423T210000Z/daq_restart.log"
assert_file_exists "$backup_root/hosts/mingo01/history/20260423T210000Z/Flow0_2026-04-23.log"
assert_file_exists "$backup_root/hosts/mingo01/history/20260423T210000Z/clean_Flow0.txt"
assert_file_contains "$backup_root/hosts/mingo01/history/20260423T210000Z/daq_restart.log" "daq-v1"
assert_file_contains "$backup_root/hosts/mingo01/history/20260423T210000Z/Flow0_2026-04-23.log" "flow-v1"
assert_file_contains "$backup_root/hosts/mingo02/history/20260423T210000Z/rates_2026-04-23.log" "rates-v1"

find "$source_root/mingo01" -mindepth 1 -delete

LOG_BACKUP_ROOT="$backup_root" \
LOG_BACKUP_SOURCE_BASE="$source_root" \
LOG_BACKUP_HOSTS="mingo01 mingo02" \
LOG_BACKUP_RUN_TIMESTAMP="20260424T090000Z" \
bash "$RUNNER_PATH"

assert_trees_equal "$source_root/mingo01" "$backup_root/hosts/mingo01/current"
assert_trees_equal "$source_root/mingo02" "$backup_root/hosts/mingo02/current"
assert_file_exists "$backup_root/hosts/mingo01/history/20260424T090000Z/daq_restart.log"
assert_file_exists "$backup_root/hosts/mingo01/history/20260424T090000Z/done/Flow0_2026-04-22.log"
assert_file_exists "$backup_root/hosts/mingo01/history/20260424T090000Z/done/Flow0_2026-04-23.log"
assert_file_exists "$backup_root/hosts/mingo01/history/20260424T090000Z/new_file.log"

summary_file="$backup_root/runtime/run_summaries/20260424T090000Z.tsv"
assert_file_exists "$summary_file"
assert_file_contains "$summary_file" $'20260424T090000Z\tmingo01\tsuccess'
assert_file_contains "$summary_file" $'20260424T090000Z\tmingo02\tsuccess'

echo "All LOG_BACKUP tests passed."
