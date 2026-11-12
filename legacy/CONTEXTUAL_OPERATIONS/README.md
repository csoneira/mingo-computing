# Archived Contextual operations material

This directory holds historical Contextual operations records that are no
longer part of the live configuration or execution paths. The dated bundle
below preserves the repository cleanup and storage-recovery work from late
October and early November 2026.

- `2026-10-30_stage1-products-tests/`: migration snapshots, dry-run reports,
  recovery scripts, logs, and the November 2 station cleanup manifest.
- `RETIRED_TOOLS/UPDATE_EXECUTION_CSVS/update_execution_csvs.sh`: deprecated
  command wrapper retired after operator confirmation. The live
  `UPDATE_EXECUTION_CSVS/OUTPUT_FILES/` directory remains in Contextual because
  the pipeline and file-flow tools still read and write its processed-basename
  CSVs.
- `RETIRED_TOOLS/COMPLETED_TO_UNPROCESSED/`: manual file-move utility retired
  from the active operations tree.
- `RETIRED_TOOLS/QUICK_CHECK_PLOTS/`: disabled quick-plot PDF collector and
  its private configuration.

The scripts and records here are archival evidence. Do not run them as current
maintenance commands without first reviewing their paths and assumptions.
Active operational configuration and scripts remain under `CONTEXTUAL/`.
- `RETIRED_TOOLS/TELEGRAM_BOT/`: unreferenced rolling Telegram plot builder, archived by operator decision; the active bot and watchdog remain live.
- `RETIRED_TOOLS/CRON_LOG_PATHS/`: unreferenced helper for pre-creating and pruning cron log paths; active cron logging creates paths lazily.
- `RETIRED_TOOLS/CLEANERS/`: unreferenced Parquet lake candidate-ranking helper, archived by operator decision.
- `RETIRED_TOOLS/OBSERVABILITY/`: unreferenced VS Code server process audit tool, archived by operator decision.
- `CRON_BACKUPS/`: dated snapshots of installed cron state retained for recovery and change traceability.
