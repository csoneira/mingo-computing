# Simulation Orchestrator

This directory owns scheduling and operational control of the MINGO digital
twin. Physics transformations remain under `MASTER_STEPS/`.

## Supported Entrypoints

- Cron cycle: `core/run_main_simulation_cycle.sh`
- Manual/single-step execution: `core/run_step.sh`
- State-changing maintenance: `maintenance/sim_maintenance.py`
- Read-only inspection: scripts under `diagnostics/`

`run_main_simulation_cycle.sh` is the only supported cron entrypoint for the
simulation cycle. It owns enqueue policy, processing locking, and STEP_FINAL
policy. `run_step.sh` executes or schedules STEP_1 through STEP_10; STEP_FINAL
is disabled when called by the cron cycle and remains available for explicit
manual execution.

## Directory Ownership

```text
core/           cron cycle and step scheduling
maintenance/    state-changing operations and their stable CLI
diagnostics/    read-only consistency and size reports
notifications/  operational alerts
helpers/        scheduler-internal implementation helpers only
lib/            shared Python path and orchestration utilities
tests/          orchestrator tests
```

Destructive helpers do not belong under `helpers/`. Maintenance operations
default to their implementation's dry-run behavior where supported. Use
`--apply` only after reviewing the dry-run output.

## Maintenance CLI

```bash
python3 PIPELINE/MINGO_DIGITAL_TWIN/ORCHESTRATOR/maintenance/sim_maintenance.py \
  sanitize-runs

python3 PIPELINE/MINGO_DIGITAL_TWIN/ORCHESTRATOR/maintenance/sim_maintenance.py \
  sanitize-runs --apply --min-age-seconds 300

python3 PIPELINE/MINGO_DIGITAL_TWIN/ORCHESTRATOR/maintenance/sim_maintenance.py \
  cascade-cleanup --intersteps PIPELINE/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/INTERSTEPS \
  --mesh PIPELINE/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/INTERSTEPS/STEP_0_TO_1/param_mesh.csv --dry-run
```

The individual Python files under `maintenance/` are implementation modules and
temporary compatibility entrypoints. New callers must use `sim_maintenance.py`.

The symlinks currently under `helpers/` for moved diagnostics, notifications,
and maintenance tools are temporary compatibility shims for simulation
processes started before this reorganization. New callers must not use them;
they can be removed after all long-running scheduler processes have restarted.

## Runtime State

Runtime logs, locks, state snapshots, and diagnostics belong under:

```text
CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/
```

The scheduler writes work-state snapshots beneath
`CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/STATE/run_step/`. Persistent diagnostics must
not be written to `/tmp`.

## Recovery

1. Inspect the simulation cron and structured logs.
2. Run diagnostics without modifying state.
3. Run the relevant maintenance command without `--apply`.
4. Review its output, then repeat with `--apply` only when required.
5. Do not remove active locks or INTERSTEPS data while the processing lock is
   held.
