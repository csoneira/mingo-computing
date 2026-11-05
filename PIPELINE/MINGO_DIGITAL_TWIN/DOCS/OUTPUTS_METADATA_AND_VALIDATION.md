---
title: Outputs, Metadata, and Validation
description: Output file formats, reproducibility metadata, and validation tooling for MINGO_DIGITAL_TWIN.
last_updated: 2026-02-24
status: active
supersedes:
  - station_dat_format.md
  - metadata_and_reproducibility.md
  - tools_and_validation.md
---

# Outputs, Metadata, and Validation

## Table of contents
- [Primary outputs](#primary-outputs)
- [Station `.dat` format](#station-dat-format)
- [Metadata and lineage model](#metadata-and-lineage-model)
- [Chunking conventions](#chunking-conventions)
- [Reproducibility notes](#reproducibility-notes)
- [Validation and maintenance tools](#validation-and-maintenance-tools)

## Primary outputs
- Interstep artifacts under `SIMULATION_OUTPUTS/INTERSTEPS/STEP_N_TO_N+1/SIM_RUN_*`.
- Final station files under `SIMULATION_OUTPUTS/SIMULATED_DATA/FILES/mi00YYDDDHHMMSS.dat`.
- Output registries:
  - `SIMULATION_OUTPUTS/SIMULATED_DATA/step_final_output_registry.json`
  - `SIMULATION_OUTPUTS/SIMULATED_DATA/step_final_simulation_params.csv`

## Station `.dat` format
Per-event line structure:
1. timestamp header (7 fields):
- `YYYY MM DD HH MM SS 1`
2. payload (64 fields):
- plane order `4,3,2,1`
- field order `T_front, T_back, Q_front, Q_back`
- strip order `1,2,3,4`

Optional file-level header line:
- `# param_hash=<sha256>`

Formatting:
- non-finite values serialized as `0.0`
- positive numbers zero-padded to width 9 with 4 decimals
- negatives keep minus sign and 4 decimals

## Metadata and lineage model

### Interstep metadata
Per output (single-file or chunk manifest):
- `created_at`, `step`, `sim_run`
- config snapshot + runtime config snapshot
- `config_hash`, `upstream_hash`
- optional row counts
- nested upstream provenance

Lineage fields commonly propagated:
- `step_1_id` ... `step_10_id`
- `param_row_id`, `param_set_id`, `param_date`
- `param_mesh_path`

### Registry files
`step_final_output_registry.json` tracks emitted files and selection details.

`step_final_simulation_params.csv` maps emitted files to full parameter rows and hash values. This file is critical for downstream geometry resolution in MASTER STEP_1. New sequential simulations also include `particle_crossing_rate_hz` and `trigger_rate_unit_efficiency_hz` beside the existing `trigger_rate_hz`; historical rows are intentionally nullable because removed intersteps cannot be reconstructed reliably.

## Chunking conventions
When chunking is enabled:
- data directory: `<stem>_chunks/part_0000.(pkl|csv)` etc.
- manifest: `<stem>_chunks.chunks.json`

Manifest includes:
- `version`
- `chunks`
- `row_count`
- `metadata`

## Reproducibility notes
- Most stochastic behavior uses configured seeds and `np.random.default_rng(seed)`.
- `T_thick_s` generation may be non-deterministic unless explicitly seeded in current step logic.
- `input_sim_run: random` can alter selection order depending on seed and filesystem state.
- Chunk ordering is manifest-driven; stale or incomplete manifests can break deterministic replay.

## Validation and maintenance tools

### Operational checks
- `PIPELINE/MINGO_DIGITAL_TWIN/ORCHESTRATOR/diagnostics/check_param_mesh_consistency.py`
- `PIPELINE/MINGO_DIGITAL_TWIN/ORCHESTRATOR/diagnostics/size_and_expected_report.py`
- `PIPELINE/MINGO_DIGITAL_TWIN/ORCHESTRATOR/maintenance/sanitize_sim_runs.py`
- `PIPELINE/MINGO_DIGITAL_TWIN/ORCHESTRATOR/maintenance/ensure_sim_hashes.py`

### Quick validation entrypoints
```bash
make validate-quick
# or
./PIPELINE/MINGO_DIGITAL_TWIN/VALIDATION/validate_quick.sh
```

### Hash integrity workflow
```bash
python3 PIPELINE/MINGO_DIGITAL_TWIN/ORCHESTRATOR/maintenance/repair_orphan_hashes.py
python3 PIPELINE/MINGO_DIGITAL_TWIN/ORCHESTRATOR/maintenance/repair_orphan_hashes.py --apply
python3 PIPELINE/MINGO_DIGITAL_TWIN/ORCHESTRATOR/maintenance/ensure_sim_hashes.py
```

Warning:
- Scripts with `--apply` may delete or rewrite simulation artifacts by design; run dry checks first.
