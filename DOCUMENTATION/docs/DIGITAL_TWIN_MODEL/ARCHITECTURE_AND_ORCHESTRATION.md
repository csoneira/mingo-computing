---
title: Architecture and Orchestration
description: End-to-end simulation pipeline flow, scheduling, backpressure, and housekeeping behavior.
last_updated: 2026-02-24
status: active
supersedes:
  - simulation_orchestration.md
  - BACKPRESSURE_PIPELINE_DETAILS.md
---

# Architecture and Orchestration

## Table of contents
- [Pipeline flow](#pipeline-flow)
- [Runtime scheduling and locks](#runtime-scheduling-and-locks)
- [Backpressure and frequency gates](#backpressure-and-frequency-gates)
- [Housekeeping sequence](#housekeeping-sequence)
- [Core scripts and responsibilities](#core-scripts-and-responsibilities)
- [Operational checks](#operational-checks)
- [Known risk points](#known-risk-points)

## Pipeline flow
1. STEP_0 (`STEP_0/setup_to_blank`) appends new rows into `SIMULATION_OUTPUTS/INTERSTEPS/STEP_0_TO_1/param_mesh.csv`.
2. STEP_1 to STEP_10 process `SIM_RUN_*` chains under `SIMULATION_OUTPUTS/INTERSTEPS/STEP_N_TO_N+1`.
3. STEP_FINAL formats station-style `.dat` files under `SIMULATION_OUTPUTS/SIMULATED_DATA/FILES/` and updates `step_final_simulation_params.csv`.
4. MASTER ingestion pulls `.dat` into station processing queues.
5. Housekeeping prunes finished mesh rows, sanitizes broken/stale runs, and keeps registries aligned.

## Runtime scheduling and locks
Primary orchestration entrypoint:
- `PIPELINE/MINGO_DIGITAL_TWIN/ORCHESTRATOR/core/run_main_simulation_cycle.sh`

Typical locking model:
- `sim_main_pipeline.lock` guards the full cycle.
- internal stage locks prevent overlapping STEP_FINAL and maintenance collisions.
- `flock -n` skips are normal under overlap; repeated long lock occupancy is not.

The cron-facing schedule is maintained in `CONTEXTUAL/CONFIG/CONTENTS/cron/analysis_pc.crontab`.

## Backpressure and frequency gates
Configuration file:
- `PIPELINE/MINGO_DIGITAL_TWIN/CONFIG_FILES/ORCHESTRATOR/sim_main_pipeline_frequency.conf`

Key parameters:
- `SIM_MAIN_CYCLE_MIN_INTERVAL_SECONDS`: throttle interval for STEP_0 enqueue phase.
- `SIM_MAX_UNPROCESSED_FILES`: backpressure cap for pending downstream files.

Backpressure counts include pending files in:
- `SIMULATION_OUTPUTS/SIMULATED_DATA/*.dat`
- `SIMULATION_OUTPUTS/SIMULATED_DATA/FILES/*.dat`
- station `INPUT_FILES/UNPROCESSED_DIRECTORY`
- station `INPUT_FILES/PROCESSING_DIRECTORY`

If pending count reaches threshold, STEP_0 is skipped (`backpressure_gate status=blocked`).
This is intentional flow control, not a code error.

## Housekeeping sequence
Within each cycle (non-fatal unless noted):
1. Optional mesh ID repair:
- `ORCHESTRATOR/maintenance/repair_param_mesh_step_ids.py`
2. Step execution:
- `run_step.sh all --no-plots`
3. Final formatting:
- `MASTER_STEPS/STEP_FINAL/step_final_daq_to_station_dat.py`
4. Mesh pruning:
- `ORCHESTRATOR/maintenance/prune_completed_param_mesh_rows.py`
5. Final params pruning:
- `ORCHESTRATOR/maintenance/prune_step_final_params.py`
6. Cascade cleanup of consumable `SIM_RUN_*` directories
7. Sanitization:
- `ORCHESTRATOR/maintenance/sanitize_sim_runs.py`

Daily/periodic maintenance outside cycle:
- `ORCHESTRATOR/maintenance/ensure_sim_hashes.py`

## Core scripts and responsibilities
- `ORCHESTRATOR/core/run_main_simulation_cycle.sh`: orchestrator with gate/lock logic.
- `ORCHESTRATOR/core/run_step.sh`: step dispatcher for STEP_1..STEP_10/FINAL.
- `MASTER_STEPS/STEP_0/step_0_setup_to_blank.py`: param mesh extension.
- `MASTER_STEPS/STEP_FINAL/step_final_daq_to_station_dat.py`: final `.dat` emission + parameter registry updates.
- `ORCHESTRATOR/diagnostics/check_param_mesh_consistency.py`: validates upstream availability for pending mesh rows.
- `ORCHESTRATOR/diagnostics/size_and_expected_report.py`: expected-run and storage diagnostics.

## Operational checks

```bash
# Process + cycle status
pgrep -af "run_main_simulation_cycle.sh|run_step.sh -c|step_final_daq_to_station_dat.py"
tail -n 80 CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/CRON_LOGS/SIMULATION/RUN/sim_main_pipeline_cycle.log

# Backpressure state (example)
rg -n "backpressure_gate|cycle status" CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/CRON_LOGS/SIMULATION/RUN/sim_main_pipeline_cycle.log

# Param-mesh consistency for STEP_3 upstreams
PYTHONPATH=. python3 PIPELINE/MINGO_DIGITAL_TWIN/ORCHESTRATOR/diagnostics/check_param_mesh_consistency.py \
  --mesh PIPELINE/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/INTERSTEPS/STEP_0_TO_1/param_mesh.csv \
  --intersteps PIPELINE/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/INTERSTEPS --step 3
```

## Known risk points
- Backpressure thresholds that are too small can permanently suppress STEP_0 in high-backlog conditions.
- Incomplete chunk manifests in upstream intersteps can cause step-selection failures if not skipped defensively.
- Strict line closure (`RUN_STEP_STRICT_LINE_CLOSURE=1`) can preserve consistency but may delay upstream generation for missing prefixes.
- Any scheduling behavior change should be reflected in this file and the central cron template.
