# QUALITY_ASSURANCE_NEW

This is the simplified QA workspace for Stage 1 metadata.


## Canonical inputs and cleanup lifecycle

QA reads metadata only from the published Stage 1 product tree:

- `MINGO_ANALYSIS_STATIONS/MINGOYY/STAGE_1_PRODUCTS/EVENT_DATA/METADATA/TASK_N/`

Before every non-aggregate QA run, the orchestrator takes a shared lock on each
live Task metadata CSV and atomically rebuilds its product snapshot. A row is
published only when `postprocessed_<basename>.parquet` already exists in that
station Parquet Lake and has valid leading and trailing `PAR1` markers. If
reprocessing produced multiple rows for one basename, only the row with the
newest `execution_timestamp` is published. Thus this product metadata tree is
a tracker of completely analyzed, archived files; incomplete working metadata
remains only below `STAGE_1/EVENT_DATA/STEP_1`. Unchanged snapshots are skipped.

The hourly `clean_dataflow.sh --select ...completed...` job uses
`qa_all_stations_reprocessing_quality.csv` as its cleanup authority. A Stage 1
intermediate is removable only when the basename has `quality_status=pass`, the
station lake contains `postprocessed_<basename>.parquet`, and the intermediate
is not newer than the QA summary. Completed directories are still cleared
unconditionally. Error and rejected files are retained unless they satisfy the
same lake-plus-explicit-pass rule. The parquet lake and product metadata are
never targets of this verified intermediate cleanup.

Current policy:

- Only the Task 2 calibration columns matching `*_Q_B` and `*_Q_F` are quality-enabled.
- Every other metadata family is configured as `plot_only` or `ignore`.
- Metadata time-series plots use unconnected points; lines are not drawn between consecutive observations.
- Plot-generating runs leave active `OUTPUTS` trees clean. Immediately before rerunning, the complete previous generation is moved to the centralized `ARCHIVED_RUN_OUTPUTS/PREVIOUS_RUN` tree. This retained generation is replaced on the next plot run; table-only `often` runs do not rotate outputs.

## Passing limits and plotted bands

QA reference populations come from the lake-gated product metadata under
`MINGO_ANALYSIS_STATIONS/MINGOYY/STAGE_1_PRODUCTS/EVENT_DATA/METADATA/TASK_N`.
The orchestrator publishes a metadata row there only after a valid final Parquet
exists in that station Parquet Lake, and keeps the newest execution per basename.

For the currently enabled calibration QA, each QF/QB value is compared within its
matched detector-configuration epoch. `STEP_1_CALIBRATIONS/config.yaml` currently
uses the epoch median, requires at least 8 values, and accepts the inclusive
interval `median * (1 - 2/100) <= value <= median * (1 + 2/100)`. The percentage
is configured in human units:

```yaml
quality_rules:
  "*_Q_[BF]":
    center_method: median
    tolerance_mode: relative_pct
    tolerance_percent: 2.0
    min_samples: 8
```

`tolerance_percent: 2.0` means 2%, not 300%; asymmetric limits can use
`lower_tolerance_percent` and `upper_tolerance_percent`. YAML `quality_rules`
override legacy threshold fields from the column-rule CSV. The translucent B/F
bands in `q_sides` are drawn from the exact persisted `lower_bound` and
`upper_bound` values used for classification. A file passes only when all 32 QF/QB
observables pass and none has a QA warning; any failed observable fails the file.

In quality plots, ordinary B/F-coloured circles are passing values. A red `x`
marks a failing value whose file is still queued for QA reprocessing. A purple
diamond marks a failing value whose retry has already been admitted and is in
flight. After successful reprocessing, the newest calibration replaces the old
point and returns to an ordinary B/F circle.

Only columns resolved as `quality_and_plot` or `quality_only` can place a
basename in the reprocessing manifest. `plot_only`, `ignore`, and QA warnings
such as `insufficient_reference` never trigger deletion.

The new package is built around three ideas:

1. One generic runner handles all metadata families.
2. Column behavior is controlled by one very small `columns.yaml` per step:

```yaml
quality_and_plot:
  - col1*

quality_only:
  - col2*

plot_only:
  - col3*

ignore:
  - param_hash
  - *topology*
```

If a column is not matched, it defaults to `plot_only`.

3. Plot layout is controlled separately in `plots.yaml`.
Columns named in `special` plots are plotted there first; any remaining plottable columns fall back to the default sequential plotting mode.
Special groups can also request shared axes such as `sharey: true` and fixed ranges such as `ylim: [0, 100]` when comparable scales are important.
For filter diagnostics there are three useful modes:

- `mode: columns`: one subplot per metadata column.
- `mode: overlay`: pattern-driven overlays where the same derived panel key is compared across several series.
- `mode: panels`: explicit overlay panels with hand-picked titles and columns, useful when scopes have asymmetric names but must be compared as the same filter variable.

## Layout

- Root config:
  - [config.yaml](/home/mingo/DATAFLOW_v3/PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/ANCILLARY/QUALITY_ASSURANCE_NEW/config.yaml)
  - [config_pipeline.yaml](/home/mingo/DATAFLOW_v3/PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/ANCILLARY/QUALITY_ASSURANCE_NEW/config_pipeline.yaml)
- Steps:
  - `STEPS/STEP_*/`
- Final aggregate:
  - `TOTAL_SUMMARY/`

Task outputs now live task by task:

- `STEPS/STEP_X/.../TASK_N/PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGOYY/OUTPUTS/FILES`
- `STEPS/STEP_X/.../TASK_N/PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGOYY/OUTPUTS/PLOTS`

Each task writes:

- `*_column_manifest.csv`: resolved category per column
- `*_pass.csv`
- `*_column_evaluations.csv` when quality is enabled
- `*_epoch_references.csv`
- `*_epoch_references_medians_wide.csv`
- `*_overwritten_metadata_rows.csv`: older duplicate basename rows that were superseded by the newest metadata row

Each step writes only summary tables under:

- `STEPS/STEP_X/OUTPUTS/MINGOYY/FILES`

`TOTAL_SUMMARY` rebuilds its own plots from its own aggregate files. It does not copy plots from the steps.

## TOTAL_SUMMARY outputs

Per station:

- `*_total_step_summary.csv`
- `*_total_quality_long.csv`
- `*_total_quality_wide.csv`
- `*_total_parameter_summary.csv`
- `*_total_step_scores.png`
- `*_total_quality_by_column*.png`
- `*_total_top_quality_failures.png`

All stations together:

- `qa_all_stations_step_summary.csv`
- `qa_all_stations_quality_long.csv`
- `qa_all_stations_quality_wide.csv`
- `qa_all_stations_parameter_summary.csv`
- `qa_all_stations_reprocessing_quality.csv`
- `qa_all_stations_overwritten_metadata_rows.csv`

Only quality-enabled columns appear in the quality tables.

## Run

```bash
python3 /home/mingo/DATAFLOW_v3/PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/ANCILLARY/QUALITY_ASSURANCE_NEW/orchestrate_quality_assurance.py --mode qa-plot
```

Examples:

```bash
python3 /home/mingo/DATAFLOW_v3/PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/ANCILLARY/QUALITY_ASSURANCE_NEW/orchestrate_quality_assurance.py --mode often --stations MINGO01
python3 /home/mingo/DATAFLOW_v3/PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/ANCILLARY/QUALITY_ASSURANCE_NEW/orchestrate_quality_assurance.py --mode qa-plot --steps STEP_1_CALIBRATIONS --stations MINGO01
python3 /home/mingo/DATAFLOW_v3/PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/ANCILLARY/QUALITY_ASSURANCE_NEW/orchestrate_quality_assurance.py --mode often --aggregate-only --stations MINGO01
```

`--mode often` updates QA tables without regenerating plots. `--mode qa-plot` updates the tables and plots only columns categorized as `quality_and_plot`; it excludes `plot_only` and `quality_only`. `--mode plot` updates the tables and plots every plottable column.

For cron usage there is also:

```bash
/home/mingo/DATAFLOW_v3/PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/ANCILLARY/QUALITY_ASSURANCE_NEW/run_quality_assurance_cron.sh often
/home/mingo/DATAFLOW_v3/PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/ANCILLARY/QUALITY_ASSURANCE_NEW/run_quality_assurance_cron.sh qa-plot
/home/mingo/DATAFLOW_v3/PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/ANCILLARY/QUALITY_ASSURANCE_NEW/run_quality_assurance_cron.sh plot
```

The wrapper keeps separate logs and a shared non-blocking lock under `QUALITY_ASSURANCE_NEW/LOGS`. The installed schedule is sourced from `CONTEXTUAL/CONFIG/add_to_crontab.info` and runs `qa-plot` hourly at minute 10. Its detailed log is `LOGS/quality_assurance_qa-plot.log`; the outer cron log is `CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/CRON_LOGS/ANCILLARY/QUALITY_ASSURANCE_NEW/quality_assurance_qa_plot.cron.log`.

The reprocessing authority table, `TOTAL_SUMMARY/OUTPUTS/FILES/qa_all_stations_reprocessing_quality.csv`, stays available during plot-output rotation and is replaced atomically after the new summary is complete. This prevents the five-minute Stage 0 retry-manifest jobs from observing a missing or partially written QA table.


## Problematic basenames and reprocessing

There are two user-facing scripts in this directory:

1. `build_problematic_basename_lists.py` reads the QA total summary and writes
   `PROBLEMATIC_BASENAMES/problematic_basenames.csv`, plus station/task text
   lists. The earliest Task containing an explicit quality failure is selected
   as the reprocessing boundary. The orchestrator runs this automatically after
   every total-summary rebuild.
2. `reprocess_problematic_basenames.py` removes matching artifacts and metadata
   from that Task through Task 5, rebuilds metadata indexes, and returns the
   input to the correct queue. It is always a dry run unless `--apply` is given.

The simplest review command processes the generated manifest:

```bash
python3 reprocess_problematic_basenames.py
```

After reviewing the complete plan:

```bash
python3 reprocess_problematic_basenames.py --apply
```

Manual station/task/list mode remains available:

```bash
python3 reprocess_problematic_basenames.py \
  --station 2 --task 2 \
  --basename-file PROBLEMATIC_BASENAMES/MINGO02_task_2_problematic_basenames.txt
```

If the selected Task input still exists, it is moved back to that Task
`UNPROCESSED` directory. If it has already been cleaned, the request is marked
for Stage 0 fallback. Stage 0 prioritizes that basename and bypasses the normal
already-brought and already-processed exclusions exactly for the active request.
The hourly QA run retires the request after a newer execution appears at the
selected starting Task.
