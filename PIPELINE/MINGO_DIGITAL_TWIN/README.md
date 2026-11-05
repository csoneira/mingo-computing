# MINGO_DIGITAL_TWIN

## Overview
MINGO_DIGITAL_TWIN is a parameterized digital twin for RPC detector data that walks a muon event
from idealized generation through gas-gap response, strip induction, front-end electronics, DAQ,
and station-style .dat formatting. The pipeline is designed for traceability and reproducibility:
intermediate data products are saved per step, and each output is annotated with metadata that
records configuration, upstream lineage, and sim-run identities.

Key design goals:
- Deterministic step boundaries between physics, readout, and electronics domains.
- Independent active-gas acceptance (STEP 2/3) and per-plane strip collection geometry (STEP 4), including inactive gaps.
- Explicit parameter mesh for scanning geometry/efficiency/flux configurations.
- Per-step artifacts (.pkl/.csv or chunked manifests) with metadata and sim-run registry tracking.

## Scope and boundaries
Physical vs electronics domains are split explicitly by step:
- MUONS (primary particle + transport): STEP 1, STEP 2
- RPC Active Volume (gas gap microphysics): STEP 3
- RPC Induction + Readout Plane: STEP 4, STEP 5, STEP 6
- Electronics + DAQ: STEP 7, STEP 8, STEP 9, STEP 10
- Output formatting only: STEP FINAL

Boundary markers (first appearance of each effect):
- Detector response begins at STEP 3.
- Readout coupling begins at STEP 4; it does not alter active-volume avalanche production.
- Electronics effects begin at STEP 8.
- Trigger-based event definition begins at STEP 9.
- Digitization artifacts begin at STEP 10.
- Formatting-only operations occur at STEP FINAL.

## Pipeline overview (Mermaid)
```mermaid
flowchart TB

subgraph SETUP["SETUP"]
  S0["STEP 0: Parameter mesh creation\n- Sample cos_n, flux, efficiencies, z-planes\n- Assign step IDs\nOutput: SIMULATION_OUTPUTS/INTERSTEPS/STEP_0_TO_1/param_mesh.csv"]:::setup
end

subgraph MU["MUONS (primary particle + transport)"]
  direction TB
  S1["STEP 1: Muon generation\n- Sample (x,y,z), (theta,phi), thick-time\nOutput: muon_sample_<N>"]:::mu
  S2["STEP 2: Plane crossings\n- Straight-line transport\n- Per-plane (x,y,z,t) + tt_crossing\nOutput: step_2"]:::mu
end

subgraph RPC["RPC (detector response)"]
  direction TB
  S3["STEP 3: Ionization + avalanche\n- Efficiencies, ions, avalanche size\nOutput: step_3"]:::rpc
  S4["STEP 4: Induction + strip coupling\n- Charge sharing across strips\nOutput: step_4"]:::rpc
  S5["STEP 5: Strip observables\n- T_diff, q_diff\nOutput: step_5"]:::rpc
  S6["STEP 6: Front/back endpoints\n- T_front/T_back, Q_front/Q_back\nOutput: step_6"]:::rpc
end

subgraph ELEC["ELECTRONICS + DAQ"]
  direction TB
  S7["STEP 7: Cable/connector offsets\nOutput: step_7"]:::elec
  S8["STEP 8: FEE model\n- Jitter, time-walk, threshold\nOutput: step_8"]:::elec
  S9["STEP 9: Trigger\n- Plane coincidence selection\nOutput: step_9"]:::elec
  S10["STEP 10: TDC/DAQ smear\n- TDC sigma + event jitter\nOutput: step_10"]:::elec
end

subgraph OUT["OUTPUT (representation only)"]
  direction TB
  SF["STEP FINAL: Station .dat formatting\nOutput: SIMULATION_OUTPUTS/SIMULATED_DATA/FILES/mi00YYDDDHHMMSS.dat"]:::fmt
end

S0 --> S1 --> S2 --> S3 --> S4 --> S5 --> S6 --> S7 --> S8 --> S9 --> S10 --> SF

classDef setup fill:#f2f2f2,stroke:#333333,stroke-width:1px,color:#0b2233;
classDef mu fill:#eef7ff,stroke:#1b4965,stroke-width:1px,color:#0b2233;
classDef rpc fill:#eafaf1,stroke:#2d6a4f,stroke-width:1px,color:#0b2233;
classDef elec fill:#fff7e6,stroke:#8a5a00,stroke-width:1px,color:#0b2233;
classDef fmt fill:#f2f2f2,stroke:#333333,stroke-width:1px,color:#0b2233;
```

## Directory layout
- `MASTER_STEPS/STEP_<X>`: per-step scripts and configs.
- `MASTER_STEPS/STEP_SHARED`: shared utilities (sim-run registry, chunked I/O, geometry helpers).
- `SIMULATION_OUTPUTS/INTERSTEPS/STEP_<X>_TO_<Y>`: per-step outputs and sim-run registries.
- `SIMULATION_OUTPUTS/INTERSTEPS/STEP_0_TO_1`: parameter mesh (param_mesh.csv) for step-ID selection.
- `SIMULATED_DATA`: step_final registries and metadata.
- `SIMULATION_OUTPUTS/SIMULATED_DATA/FILES`: station-style .dat outputs.
- `DOCS`: technical documentation, data dictionary, and interface contracts.

## Running the pipeline
Step 0 (parameter mesh):
```
python3 MASTER_STEPS/STEP_0/step_0_setup_to_blank.py \
  --config MASTER_STEPS/STEP_0/config_step_0_physics.yaml
```

Step-by-step or all steps:
```
./run_step.sh 1
./run_step.sh all
./run_step.sh --from 4 --no-plots
```

Each step script accepts:
- `--config` (physics parameters)
- `--runtime-config` (I/O, chunking, plots)
- `--plot-only` or `--no-plots`
- `--force` to overwrite an existing SIM_RUN

## Data products and metadata
- Outputs are either single files (`.pkl` or `.csv`) or chunked manifests (`*.chunks.json`).
- Every output has metadata (sidecar `.meta.json` or manifest `metadata`), including:
  `step`, `config`, `runtime_config`, `sim_run`, `config_hash`, `upstream_hash`, and lineage.
- Each step maintains a `sim_run_registry.json` in its INTERSTEPS directory.

## Documentation map
- Methods and modeling details: `DOCS/methods_overview.md`
- Data dictionary and column definitions: `DOCS/data_dictionary.md`
- Configuration reference: `DOCS/config_reference.md`
- Metadata and reproducibility: `DOCS/metadata_and_reproducibility.md`
- Parameter mesh specification: `DOCS/param_mesh.md`
- Coordinate and timing conventions: `DOCS/coordinate_and_timing_conventions.md`
- Station .dat format: `DOCS/station_dat_format.md`
- Tooling and validation: `DOCS/tools_and_validation.md`
- Per-step interface contracts: `DOCS/contracts/`
