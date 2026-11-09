---
title: Simulation Troubleshooting Runbook
description: Consolidated troubleshooting guide for missing intersteps, fixed-z behavior, and scheduler stalls.
last_updated: 2026-02-24
status: active
supersedes:
  - ../TROUBLESHOOT_STEP_3_missing_intersteps.md
  - simulation_fixed_z_priority_troubleshooting_2026-02-13.md
---

# Simulation Troubleshooting Runbook

## Table of contents
- [Symptom patterns](#symptom-patterns)
- [Core diagnostics](#core-diagnostics)
- [Incident patterns and fixes](#incident-patterns-and-fixes)
- [Recovery playbooks](#recovery-playbooks)
- [Preventive hardening](#preventive-hardening)

## Symptom patterns
1. STEP_3 appears idle for pending `param_mesh.csv` rows.
2. Scheduler loops but does not create missing upstream `SIM_RUN_<step1>_<step2>` directories.
3. STEP_2 fails with unsupported input format or missing manifests.
4. Fixed `z_positions` objective is blocked by strict line closure policy.

## Core diagnostics

```bash
# Pending rows for a target prefix
rg -n "^0,087,006" PIPELINE/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/INTERSTEPS/STEP_0_TO_1/param_mesh.csv

# Upstream presence checks
ls -1 PIPELINE/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/INTERSTEPS/STEP_2_TO_3/

# Work cache and scheduler state
cat /tmp/mingo_digital_twin_run_step_work_cache.csv
cat /tmp/mingo_digital_twin_run_step_state.csv

# Consistency checker
PYTHONPATH=. python3 PIPELINE/MINGO_DIGITAL_TWIN/ORCHESTRATOR/diagnostics/check_param_mesh_consistency.py \
  --mesh PIPELINE/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/INTERSTEPS/STEP_0_TO_1/param_mesh.csv \
  --intersteps PIPELINE/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/INTERSTEPS --step 3
```

One-liner to detect pending rows missing STEP_2 upstreams:

```bash
awk -F, '$1==0 {printf "%03d %03d\n", $2, $3}' PIPELINE/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/INTERSTEPS/STEP_0_TO_1/param_mesh.csv \
  | while read s1 s2; do
      d="PIPELINE/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/INTERSTEPS/STEP_2_TO_3/SIM_RUN_${s1}_${s2}"
      [[ -d "$d" ]] || echo "MISSING_UPSTREAM: ${s1},${s2}"
    done
```

## Incident patterns and fixes

### Pattern A: pending param rows but missing STEP_2 upstreams
Root cause:
- `param_mesh` rows marked `done=0` but required upstream run directories absent.
- With `RUN_STEP_STRICT_LINE_CLOSURE=1`, scheduler may refuse to open new lines for automatic remediation.

Fix options:
- targeted manual STEP_2 then STEP_3 run, or
- scheduler run with appropriate bootstrap settings.

### Pattern B: fixed-z priority conflicts with strict closure
Root cause:
- active open STEP_1 line contains pending rows irrelevant to fixed `z_positions` objective.
- strict closure blocks opening useful lines.

Relevant helper:
- `ORCHESTRATOR/maintenance/close_unproductive_fixed_z_lines.py`

Control flag:
- `RUN_STEP_OBLITERATE_UNINTERESTING_STEP1_LINES=1`

Use with care because it mutates mesh completion state.

### Pattern C: STEP_2 crashes on incomplete inputs
Root cause:
- chunk directories exist but `.chunks.json` manifest missing.

Fix:
- defensive skipping of incomplete candidates in STEP_2,
- explicit cleanup or regeneration of malformed `SIM_RUN_*` directories.

## Recovery playbooks

### 1) Recover missing STEP_3 outputs for a prefix
1. Identify pending `(step_1_id, step_2_id)` pairs in mesh.
2. Verify absence in `SIMULATION_OUTPUTS/INTERSTEPS/STEP_2_TO_3/`.
3. Generate missing STEP_2 upstreams.
4. Run STEP_3 and confirm `SIMULATION_OUTPUTS/INTERSTEPS/STEP_3_TO_4/` outputs appear.
5. Re-run consistency checker until zero mismatches.

### 2) Fixed-z blocked pipeline
1. Confirm fixed-z config in `MASTER_STEPS/STEP_2/config_step_2_physics.yaml`.
2. Inspect strict-closure state cache (`/tmp/mingo_digital_twin_run_step_state.csv`).
3. If policy allows, run:

```bash
python3 PIPELINE/MINGO_DIGITAL_TWIN/ORCHESTRATOR/maintenance/close_unproductive_fixed_z_lines.py --apply
```

4. Re-run cycle and verify progress beyond STEP_2.

### 3) Incomplete STEP_1_TO_2 manifests
1. Detect malformed runs:

```bash
for d in PIPELINE/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/INTERSTEPS/STEP_1_TO_2/SIM_RUN_*; do
  for base in "$d"/muon_sample_*; do
    [ -d "$base/chunks" ] || continue
    [ -f "${base}.chunks.json" ] || echo "INCOMPLETE: $base"
  done
done
```

2. Remove or regenerate invalid runs.
3. Re-run STEP_2 and monitor for sustained progress.

## Preventive hardening
- Keep `check_param_mesh_consistency.py` in regular ops checks.
- Add tests for scheduler decisions around strict closure and missing upstreams.
- Prefer explicit bootstrap policy flags over hidden behavior.
- Keep debug instrumentation temporary; remove once incidents are resolved.

Open TODO flags:
- Add explicit CI test for "pending mesh row without upstream" failure visibility.
- Define allowed use-cases for line-obliteration helper to reduce accidental misuse.
