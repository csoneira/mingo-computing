# Cron consolidation review

This is a review of the active cron source templates, not the archived crontab
snapshots under `OPERATIONS_RUNTIME`. No cron entries or scripts were changed
for this review.

## Scope and counts

- `CONFIG/CONTENTS/cron/analysis_pc.crontab`: 40 active entries, including
  boot entries; 36 commands use `cron_run_logged.sh`, 6 also use
  `resource_gate.sh`, and 10 use `flock` (these wrapper counts overlap).
- `FOR_MINGO_SYSTEMS/station_automation_scripts/add_to_crontab_mingo.info`:
  24 active station entries. They run on the station host and directly reference
  station-installed software, so they should be reviewed separately from the
  analysis-PC schedule.

Commented and explicitly disabled entries are not counted as active.

## Keep as separate responsibilities

- The `@reboot` and five-minute `start-dataflow-tmux` entries start the monitor
  at boot and then recover it if it stops.
- `file_flow_tracker.py` is the 15-minute deep reconciliation and repair pass;
  `file_flow_realtime.py` refreshes dashboards each minute from cached metadata
  and live file positions. The latter depends on the former's snapshots.
- Stage 0 reprocessing prepare, bring, and unpack jobs are staggered. Their
  schedule expresses the pipeline order, and their locks and logs are
  independent.
- `cron_run_logged.sh`, `resource_gate.sh`, and `flock` have distinct jobs:
  output/status capture, resource admission, and mutual exclusion. Their
  nesting is repetitive in the crontab but not currently duplicate behavior.
- Station-specific sync, Copernicus, and data-processing invocations pass
  different station IDs and have separate schedules/logs. A common script is
  already reused; combining the cron lines would reduce text but couple their
  failures and logging.

## Candidates for simplification review

### 1. Two simulation process guards

`watchdog_process_counts.sh` runs every five minutes and kills processes above
per-command/per-station limits. `MINGO_DIGITAL_TWIN/ORCHESTRATOR/maintenance/stop_execution.sh`
runs every two minutes and can stop Digital Twin work when total matching
processes, duplicates, or system load exceed thresholds. Both inspect process
trees and can terminate simulation jobs. The overlap is specifically around
`run_step.sh`, Step 0 setup, and STEP_FINAL; the watchdog caps each at one active
process by default.

**Recommendation:** keep both scheduled guards separate for now. The watchdog
also caps Stage 0, reprocessing, and Copernicus groups. `stop_execution.sh`
provides the distinct system-load/total-count emergency stop and cleans the
Digital Twin run-step lock after it terminates work. The narrower duplicate
trigger in `stop_execution.sh` (default `DUP_THRESHOLD=5`) appears redundant
with the watchdog's per-command cap of one. If simplifying this area, first
remove or disable only that duplicate trigger, then retain the load/total-count
stop and lock cleanup. Do not combine the two scheduled jobs until their
different recovery behavior is covered by one explicit policy.

### 2. Repeated station parameterizations

`sync_station_scripts.sh` is scheduled four times with station IDs 1–4 at
01:00–04:00. Other stage scripts are also called with station-specific
arguments. The implementations are already shared; the repetition is in the
cron declarations. A batch runner could reduce lines, but would need to retain
per-station logs, locks, schedules, and failure isolation. This is a modest
readability improvement, not yet a clear reduction in system complexity.

### 3. Reprocessing inbox cron entry — resolved

The Stage 0 petition worker now uses `$DATAFLOW_ROOT`, `$MASTER_STAGE_ROOT`,
and `$PYTHON_BIN`, and runs through `cron_run_logged.sh`. Its output and exit
status follow the shared cron logging path. The worker's own nonblocking inbox
lock remains in place.

### 4. Station DCS startup and periodic schedule

The station crontab starts `dcs_om.sh` once after reboot from
`/media/externalDisk/gate/bin/`, then periodically from
`/home/rpcuser/gate/bin/` with `RPCSYSTEM` and `RPCRUNMODE` set. These may be
intentional startup and periodic modes, but the different executable paths and
environments deserve confirmation before any consolidation.

## Areas not suitable for line-count-only merging

The MINGO01 CAEN monitor is a separate installed controller at
`/home/rpcuser/CAEN/monitor.py`; station automation contains callers and related
HV tools, but does not deploy the controller itself. The hourly backup,
log cleanup, file-flow, and notification jobs also have separate inputs and
retention rules. Combining them solely to shorten the cron file would reduce
traceability.

## Suggested order for decisions

1. Decide ownership and boundary between the two simulation process guards.
2. Correct the reprocessing inbox command's root/logging consistency.
3. Confirm whether the station DCS reboot and periodic commands intentionally
   use different paths/modes.
4. Consider a station-batch runner only if separate logs and failure isolation
   can be preserved without adding more configuration.
