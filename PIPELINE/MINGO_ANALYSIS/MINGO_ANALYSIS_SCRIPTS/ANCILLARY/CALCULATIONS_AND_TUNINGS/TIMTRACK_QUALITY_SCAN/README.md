# TimTrack Quality Scan

This utility automates convergence scans for Stage 1 Task 4 TimTrack fitting.
By default it **does not launch Task 4**. It only rotates convergence parameters
and regenerates plots from metadata produced by your normal automatic pipeline.

## Files

- `run_timtrack_quality_scan.sh`: scan orchestrator (parameter cycling + Task 4 runs + plot refresh).
- `CONFIGS/timtrack_quality_scan.conf`: runtime config (`station`, interval, paths, etc.).
- `timtrack_quality_scan_plotter.py`: metadata plotter used by the orchestrator.

## Quick start

```bash
# Plot existing metadata only (no Task 4 run, no parameter changes)
PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/ANCILLARY/TIMTRACK_QUALITY_SCAN/run_timtrack_quality_scan.sh --plot-only

# Run one cycle (first enabled profile), then exit
PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/ANCILLARY/TIMTRACK_QUALITY_SCAN/run_timtrack_quality_scan.sh --once
```

## Continuous scan

```bash
PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/ANCILLARY/TIMTRACK_QUALITY_SCAN/run_timtrack_quality_scan.sh
```

The script:
1. Generates the next profile from config (`cocut_min..cocut_max` with `cocut_step`) using fixed `d0` and fixed `iter_max`.
2. Updates Task 4 convergence parameters in `config_parameters_task_4.csv`.
3. Waits `interval_minutes` (metadata-only mode) while external Task 4 runs happen.
4. Appends a row to `OUTPUT/timtrack_quality_scan_log.csv`.
5. Appends a run definition row (basenames for that cycle) to `OUTPUT/timtrack_quality_scan_run_reference.csv`.
6. Regenerates scan plots and grouped summaries in `OUTPUT/`.

`--plot-only` runs only the plotting step.

## Plot selection by run

By default the plotter uses the **latest defined run** from the run-reference log
(`plot_run_back=0` in config). A run is defined by the set of `filename_base`
values detected in that cycle.

To select an older run, edit:

- `plot_run_back=1` for previous run
- `plot_run_back=2` for two runs back
- `plot_run_back=-1` to disable run filtering and use row-based plotting

If you explicitly want this script to launch Task 4 itself, use:

```bash
PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/ANCILLARY/TIMTRACK_QUALITY_SCAN/run_timtrack_quality_scan.sh --run-task4
```

## Config pattern requested

Set these in `timtrack_quality_scan.conf`:

- `fixed_d0=<value>` (single chosen value, not scanned)
- `fixed_iter_max=<value>` (single chosen value, not scanned)
- `cocut_min=<value>`
- `cocut_max=<value>`
- `cocut_step=<value>`

This creates a cocut scan only.  
If you set `use_cocut_range=false`, provide `profiles_csv=<path>` explicitly.

## Finite planned run + default restore

For a one-pass planned sweep that stops automatically (without `--max-cycles`), set:

- `stop_after_profile_sweep=true`
- `restore_default_after_sweep=true`
- `default_d0=<value>`
- `default_cocut=<value>`
- `default_iter_max=<value>`

Behavior:
1. The script runs each configured profile once.
2. After the last profile, it restores the configured defaults in `config_parameters_task_4.csv`.
3. The script exits.
