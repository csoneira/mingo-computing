# Stage 0 to Parquet Lake file-flow tracker

`file_flow_tracker.py` provides one current, machine-readable view of every
datafile as it moves from `STAGE_0_TO_1` through Stage 1 Tasks 0–5 and into the
station's `PARQUET_LAKE`.

## Authority and safety rules

The Parquet Lake is the durable archive and the only final-completion
authority. A basename is put in the legacy `MINGOxx_processed_basenames.csv`
list only when a Parquet with valid leading and trailing `PAR1` markers exists
in that station's lake. Stage 2 products or Stage 1 metadata cannot mark an
unarchived file as processed.

The default invocation is report-only:

```bash
python3 file_flow_tracker.py
```

`--apply` enables conservative reconciliation:

```bash
python3 file_flow_tracker.py --apply
```

Repairs are restricted to the date ranges selected in
`PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/SUPPORT/CONFIG_FILES/config_selection.yaml`.
An empty effective range is report-only; it never means full history. Use
`--all-dates` only for an intentional full-history repair. Repairs are also deferred when `/home` is at or above 94% usage.

The reconciler follows these rules:

- A valid final Parquet is never removed.
- Active reprocessing, fresh processing files, fresh task outputs, and metadata
  written within the last six hours are left untouched.
- A stale `PROCESSING_DIRECTORY` file is returned to the same task's
  `UNPROCESSED_DIRECTORY`.
- A stranded task output or completed input is resumed from the latest safe
  task. Metadata at that task and later tasks is removed so it cannot suppress
  the retry.
- If neither a final Parquet nor a recoverable intermediate exists, Stage 1
  metadata and the Stage 0 acquisition/reprocessing guards are removed. This
  lets the normal Stage 0 jobs fetch the source again.
- Invalid final Parquets are moved to the runtime quarantine, not destroyed.
- Error and out-of-date queues require manual review unless `--retry-errors`
  is explicitly used.

Every removed CSV row is journaled before its atomic source rewrite and preserved
as JSON in `removed_metadata_rows.csv.gz`, including malformed extra fields, its
source path, and the repair reason.

## Live tracking outputs

The current snapshots are written under:

```text
CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/FILE_FLOW_TRACKER/
```

The main files are:

- `MINGOxx_file_flow_latest.csv`: one row per datafile and station, with every
  queue state, lake validity, metadata presence, anomalies, and current paths.
- `summary_latest.csv`: compact station totals suitable for a CLI dashboard.
- `actions_latest.csv`: mutations made by the most recent run.
- `removed_metadata_rows.csv.gz`: append-only gzip-compressed recovery ledger.
- `QUARANTINE/MINGOxx/`: invalid lake files moved out of authoritative storage.

The station CSV is intentionally flat so a future terminal UI can refresh it
without scanning the data tree.

## One-minute real-time snapshots

`file_flow_realtime.py` provides the inexpensive view intended for a live CLI
or dashboard. It runs every minute and:

- reads the most recent deep `MINGOxx_file_flow_latest.csv` as a metadata cache;
- scans only Stage 0 files, Stage 1 queues and outputs, active-reprocessing
  state, and Parquet Lake files;
- validates the inexpensive leading/trailing Parquet magic bytes;
- never reads the large working metadata CSV tree;
- never repairs, deletes, moves, or rewrites pipeline data or metadata.

It writes:

- `MINGOxx_file_flow_realtime.csv`: current per-file artifact and lifecycle
  state, with cached metadata facts;
- `realtime_summary.csv`: compact station-level state and scan timing.

The `deep_snapshot_observed_at_utc` and `deep_snapshot_age_seconds` columns make
the age of cached metadata explicit. The full `file_flow_tracker.py --apply`
continues every 15 minutes as the authoritative consistency and repair pass.
Use the real-time CSVs for display and the deep CSVs for reconciliation audits.

## Useful options

```text
--stations 1 2          only inspect selected stations
--processed-lists-only  refresh lake-backed reject lists without repair
--stale-hours 12        change the in-flight protection window
--all-dates             allow repair outside configured date ranges
--retry-errors          allow explicit retry of manual-review queues
--max-repair-disk-percent 93
```

The script uses a non-blocking lock. Overlapping cron runs therefore cannot
mutate the same metadata concurrently.
