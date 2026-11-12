# Contextual operations script usage audit

This is an evidence-based inventory for deciding which scripts should remain
in the active operations tree. “No in-repository caller found” does not mean
“unused”: interactive and emergency tools may be invoked manually, and this
repository does not contain shell history for those calls.

## Evidence checked

- Active (non-commented) command paths in
  `CONTEXTUAL/CONFIG/CONTENTS/cron/analysis_pc.crontab`.
- Calls between scripts, shell startup helpers, setup/recovery code, and
  tracked documentation.
- The local ignored cron logs present during this audit. Several scheduled
  Contextual jobs had logs updated on 2026-11-10. This confirms recent use on
  this checkout, but the logs are runtime state and are not repository source.
- Git history only as a maintenance signal. Recent commits mostly reflect the
  November repository reorganization, so commit dates alone do not establish
  that a script was executed.

## Active scheduled or scheduled-through-a-helper

These are named in the active cron template, or are called by something that
is. Keep them in the live tree unless the cron workflow is intentionally
changed.

| Script | Evidence |
| --- | --- |
| `DATA_MAINTENANCE/FILE_FLOW_TRACKER/file_flow_realtime.py` | Active cron entry; local runtime log updated Nov 10. |
| `DATA_MAINTENANCE/FILE_FLOW_TRACKER/file_flow_tracker.py` | Active cron entry; local runtime log updated Nov 10. |
| `DATA_MAINTENANCE/FIX_METADATA_FILES/fix_event_metadata_files.py` | Active cron entry; local runtime log updated Nov 10. |
| `DATA_MAINTENANCE/FLUSH_FROM_UNPROCESSED/flush_from_unprocessed.sh` | Active cron entry; local runtime log updated Nov 10. |
| `DATA_MAINTENANCE/REMOTE_LOG_BACKUP/run_log_backup.sh` | Active cron entry; local runtime log updated Nov 10; calls the history-pruning helper below. |
| `DATA_MAINTENANCE/REMOTE_SYNC/sync_station_scripts.sh` | Active station-specific cron entries; local logs updated Nov 10. |
| `MAINTENANCE/AUTO_CLEAR_SWAP/auto_clear_swap_if_idle.sh` | Active cron entry; local runtime log updated Nov 10. |
| `MAINTENANCE/CLEANERS/clean_dataflow.sh` | Active cron entry; wrapper for `clean_dataflow.py`; local runtime log updated Nov 10. |
| `MAINTENANCE/ERASE_ALL_CRON_LOGS/erase_cron_logs.sh` | Active nightly cron entry; local runtime log updated Nov 9. |
| `NOTIFICATIONS/TELEGRAM_BOT/persistent_telegram_bot_check.sh` | Active cron watchdog; starts `mingo_analysis_bot.py`; local logs exist. |
| `NOTIFICATIONS/TELEGRAM_BOT/mingo_analysis_bot.py` | Started by the active bot watchdog; local bot log updated Nov 10. |
| `OBSERVABILITY/FOLLOW_COLUMNS/generate_columns_review.py` | Active hourly cron entry; local runtime log updated Nov 10. |
| `OBSERVABILITY/SEARCH_FOR_ERRORS/error_finder.py` | Active cron entry; local runtime log updated Nov 10. |
| `OBSERVABILITY/VERSION_CONTROL/snapshot_config.py` | Active hourly cron entry; local runtime log updated Nov 10. |
| `ORCHESTRATION/CRON_RUN_LOGGED/cron_run_logged.sh` | Shared launcher used by many active cron entries. |
| `ORCHESTRATION/RESOURCE_GATE/resource_gate.sh` | Wraps many active pipeline cron entries. |
| `ORCHESTRATION/SOLVE_STALE_LOCKS/solve_stale_locks.py` | Active cron entry; local runtime log updated Nov 10. |
| `ORCHESTRATION/WATCHDOG_PROCESS_COUNTS/watchdog_process_counts.sh` | Active cron entry; local runtime log updated Nov 10. |

## Required helpers and documented manual tools

These are not all direct cron targets, but have a clear caller or documented
interactive purpose.

| Script(s) | Evidence / relationship |
| --- | --- |
| `DATA_MAINTENANCE/FILE_FLOW_TRACKER/watch_file_flow.sh`, `watch_file_flow_engine.sh` | `watch_file_flow` is installed as a shell helper and used by the tmux monitor; the wrapper delegates to the engine. This is a frontend/engine pair, not a duplicate. |
| `DATA_MAINTENANCE/REMOTE_LOG_BACKUP/prune_log_backup_history.py` | Called by `run_log_backup.sh`; has its own unit tests. |
| `MAINTENANCE/CLEANERS/clean_dataflow.py`, `check_parquet_lake_consistency.sh` | The shell launcher calls the Python cleaner; the cleaner invokes the consistency checker. |
| `OBSERVABILITY/AUDIT_PIPELINE_STATES/run_audit_pipeline_states.sh`, `audit_pipeline_states.py` | Shell launcher for the Python audit tool. Keep together if the audit tool remains. |
| `DATA_MAINTENANCE/OFFLOAD_PARQUET_LAKE/offload_parquet_lake.py` | Has maintained operator documentation and an explicit `--apply` path. |
| `DATA_MAINTENANCE/OFFLOAD_SIM_INTERSTEPS/offload_sim_intersteps.py` | Has maintained operator documentation; relocation is opt-in with `--activate`. |
| `DEVELOPER_TOOLS/standardize_script_headers.py` | Referenced by the essential script-header guide. |
| `DEVELOPER_TOOLS/dirtree.py` | Installed as the `dirtree` shell command; lists files and directories by default, with `--dirs-only` for directory-only trees. |
| `DATA_MAINTENANCE/REMOTE_LOG_BACKUP/tests/*`, `DATA_MAINTENANCE/FILE_FLOW_TRACKER/tests/*`, `MAINTENANCE/CLEANERS/tests/*` | Tests for retained operational tools; keep with their owning code. |

## Manual and emergency tools without cron entries

I found no active cron path or non-self in-repository caller for these during
this pass. Some are potentially valuable manual or emergency tools. The
proposed disposition is deliberately conservative.

| Script(s) | Evidence / proposed decision |
| --- | --- |
| `ORCHESTRATION/KILL_RUNNING_PROCESSES/kill_pipeline_execution_processes.sh` | Manual emergency process tool; retained by operator decision. |
| `OBSERVABILITY/EXECUTION_TOP_OFFENDERS/execution_top_offenders.sh` | Standalone diagnostic with no active cron caller; retained by operator decision. |
| `NOTIFICATIONS/TELEGRAM_BOT/kill_bot_and_restart.sh` | Invoked by the bot’s `/restart_bot` command; stops the polling process and hands startup back to the active watchdog. |
| `MAINTENANCE/CLEANERS/top_large_dirs.sh`, `MISCELLANEOUS_TOOLS/EXPORT_TO_PDF/export_markdown_to_pdf.py` | Standalone operator utilities without tracked callers; retained by operator decision. |
| `NOTIFICATIONS/STATUS_GUI/*.py` | Four standalone status GUIs; retained by operator decision. |

The following tools have been relocated by operator decision:

- `move_completed_to_unprocessed.sh` is under
  `legacy/CONTEXTUAL_OPERATIONS/RETIRED_TOOLS/COMPLETED_TO_UNPROCESSED/`.
- `sync_latest_step1_pdfs.sh` and its dedicated config are under
  `legacy/CONTEXTUAL_OPERATIONS/RETIRED_TOOLS/QUICK_CHECK_PLOTS/`. Its cron
  entry was disabled; the stale command and runtime-directory declarations
  were removed.
- `interstep_simulation_cleaner.sh` is now under
  `PIPELINE/MINGO_DIGITAL_TWIN/ANCILLARY/`, alongside Digital Twin ancillary
  operations.
- `update_execution_csvs.sh` is under
  `legacy/CONTEXTUAL_OPERATIONS/RETIRED_TOOLS/UPDATE_EXECUTION_CSVS/`.

Only the `update_execution_csvs.sh` wrapper moved: the neighboring
`UPDATE_EXECUTION_CSVS/OUTPUT_FILES/` directory remains live because the file
flow tracker, reprocessing code, and unprocessed-file cleaner still use those
CSVs.

`NOTIFICATIONS/TELEGRAM_BOT/build_mingo01_telegram_recent.py` also has no
cron reference or tracked caller found. I have not classified it as obsolete;
it appears to be a manual message-building utility and needs operator review.

## Current proposal

For the remaining review candidates, decide whether they belong in the active tree as
documented manual tools or in
`legacy/CONTEXTUAL_OPERATIONS/` as preserved inactive code. Do not remove
runtime logs or state as part of source cleanup; those are locally ignored
operational data with their own retention needs.

The unreferenced `build_mingo01_telegram_recent.py` plot builder was moved to `legacy/CONTEXTUAL_OPERATIONS/RETIRED_TOOLS/TELEGRAM_BOT/` by operator decision. The active bot and watchdog remain in place.

The unreferenced `ensure_cron_log_paths.sh` helper was moved to `legacy/CONTEXTUAL_OPERATIONS/RETIRED_TOOLS/CRON_LOG_PATHS/` by operator decision. Cron log directories are created lazily by `cron_run_logged.sh` when a job emits output or fails.

The unreferenced, read-only `rank_parquet_lake_candidates.py` helper was moved to `legacy/CONTEXTUAL_OPERATIONS/RETIRED_TOOLS/CLEANERS/` by operator decision. It emitted ranked Parquet paths but did not delete files and was not called by `clean_dataflow.py`.

`vscode_server_audit.sh` was moved to `legacy/CONTEXTUAL_OPERATIONS/RETIRED_TOOLS/OBSERVABILITY/` by operator decision. The now-empty source directory was removed.
