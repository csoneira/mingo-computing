# Configurable repository cleaner

The hourly cron job runs `clean_dataflow.sh --apply --force --compact`. It reads
[cleaner_config.json](../../../../../../../CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/MAINTENANCE/CLEANERS/cleaner_config.json) beside the script on every invocation.
The shell launcher retains the existing path; deletion planning is in
`clean_dataflow.py`. No third-party Python packages are needed.

Each category has `enabled`, `min_age_hours`, and `keep_newest`:

| Category | Scope | Enabled by default |
|---|---|---|
| `plots` | Generated station, simulation and ancillary plot directories; all figure formats | yes |
| `pdfs` | PDF files in those plot directories | no |
| `pngs` | PNG files in those plot directories | no |
| `temps` | Stage-0 unpacker `daqData/varData`, removed/done buffers | yes |
| `completed_data` | Files beneath COMPLETED / COMPLETED_DIRECTORY in station trees | yes |
| `error_data` | Old files beneath ERROR / ERROR_DIRECTORY in station trees | yes |
| `unprocessed_data` | Files beneath UNPROCESSED / UNPROCESSED_DIRECTORY in station trees | no |
| `parquet_lake` | Station STAGE_1_PRODUCTS/EVENT_DATA/PARQUET_LAKE parquets | no |
| `simulation_intermediates` | Complete SIM_RUN groups in simulation intersteps | no |
| `simulation_junk` | Files under checkout-local SIMULATION_DATA_JUNK | no |

`plots` includes PDF and PNG. To clean only PDFs, disable `plots` and enable
`pdfs`. Overlapping switches are deduplicated, with `plots` taking precedence.
Recent runtime figure directories and FINAL_PLOTS/TASK_N/parquet-stem reports
are retained as complete runs (five by default), not five individual images.
A report is eligible only when its newest file is older than the configured age.
Loose files and data are ranked per immediate parent directory. After an applied
plot cleanup, empty descendant folders inside generated `DEBUG_PLOTS` and
`FIGURE_DIRECTORY` trees are removed, along with either root when it becomes
empty. Other empty structural folders are preserved. Age and retention apply
even with `--force`.

Discovery handles TASK_1_SELFTRIGGER, TASK_2_SELFTRIGGER, nested minimal/maximal
FINAL plots, historical figure folders, all station stages and the current lake.
Ancillary/simulation plotting is restricted to named generated plot directories;
documentation figures are excluded. External .safe-mingo-computing and sibling junk
storage are no longer scanned implicitly.

```bash
# Review configured categories without deleting; emit exact candidate paths/sizes.
bash CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/MAINTENANCE/CLEANERS/clean_dataflow.sh \
  --dry-run --force --compact --report /tmp/cleaner-candidates.csv

# Explicit one-off override, even when the category is disabled in the config.
bash CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/MAINTENANCE/CLEANERS/clean_dataflow.sh \
  --dry-run --force --select pdfs

# Apply the configured selection.
bash CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/MAINTENANCE/CLEANERS/clean_dataflow.sh \
  --apply --force --compact
```

Without `--apply` the command is a dry run. `--config PATH` selects another config.
`--select` overrides enabled flags; `completed` is a compatibility alias for
`completed_data`. `error_data` retains the configured newest files and age
window before pruning stale failed inputs. `--select all` is rejected: name destructive data categories
explicitly. `--keep-final` preserves all completed data without a pressure override.
The old `--kill-lock-holder` option is removed; a busy lock always causes a skip.
A persistent shared lock prevents concurrent cleaners. Symlinks, processing trees,
metadata, tracked files, and basenames currently in processing queues are protected.
Changed files are rechecked before deletion. Simulation cleanup requires exclusive
simulation enqueue/processing/final locks. Data categories can still erase useful
pending scientific work when deliberately enabled; review their dry run first.

There are no unconditional sidecar removals, simulation-junk removals, QA-based
queue purges, or emergency archive deletions outside the configured selection.
The previous read-only lake consistency report is retained in its own helper and
runs after apply when `check_archive_consistency` is true. Nightly cron-log
truncation remains handled by its existing separate cron job. The simulation
controller's independent disk-pressure reset policy is not changed by this config.

Tests: `python3 -m unittest discover -s CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/MAINTENANCE/CLEANERS/tests -v`.
