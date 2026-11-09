# INFERENCE_DICTIONARY_VALIDATION

*We do simulations like this: we choose a point in the parameter space, generate a dataset simulated with those parameters, then we analyze the resulting datafile and that analysis outputs a point in the feature space. But since we know the origina parameter set, we have a bijective relation established from parameter space to feature space. So, for a file that we dont know the parameter set that generated it, the idea is that we calculate distances in the feature space, maybe with 1 or with n neighbours, or with all the neighbours, then we use that set of results to calcualte to go back to the parameter space and, in that space, calculate a representative point for the tested entry. It's the concept of a continous function: if we know where the points around a point go, we can estimate where that point goes. in this case the function has its domain in the feature space and goes to the parameter (of simulation space).*

*In other words. We construct a mapping between simulation parameter space and analysis feature space by generating simulated datasets at selected points in the parameter space and processing each dataset through the same analysis chain used for real data. Each simulation therefore produces a corresponding point in feature space, while its generating parameter vector is known by construction. In this way, the simulation set defines a sampled correspondence from parameters to features, and, equivalently, an empirical inverse relation from features back to parameters. For an input data file whose generating parameters are unknown, we first extract its feature-space coordinates and then compare this point with the simulated entries in feature space, for example using the single nearest neighbour, the n nearest neighbours, or a weighted combination of all neighbours. The associated parameter-space points of those neighbouring simulations are then used to infer the most representative parameter vector for the unknown file. The underlying idea is continuity: if nearby points in feature space arise from nearby points in parameter space, then the local structure of the simulated sample can be used to estimate the parameter-space origin of a previously unseen observation.*

Validation pipeline for the MINGO simulation-based inference method.
Given a dictionary of simulated detector responses, the pipeline tests
whether the matching procedure can reliably recover the physical
parameters (cosmic-ray flux and detection efficiency) from topology-count
observables alone.

## Pipeline overview

```
STEP 1.1  Collect simulated metadata and simulation parameters
STEP 1.2  Transform feature space
STEP 1.3  Build dictionary + holdout
STEP 1.4  Enforce continuity and filter discontinuities
STEP 1.5  Tune feature-distance definition

STEP 2.1  Estimate parameters on holdout/dataset
STEP 2.2  Validate estimates vs simulation truth
STEP 2.3  Build uncertainty LUT

STEP 3.1  Create synthetic parameter time series
STEP 3.2  Build synthetic dataset from dictionary + trajectory
STEP 3.3  Apply inference correction + LUT on synthetic data

STEP 4.1  Collect real metadata (station/task/date windows)
STEP 4.2  Infer real parameters and attach uncertainties
```

For the shortest explanation of the method itself, see:

- [DOCS/CORE_METHOD.md](DOCS/CORE_METHOD.md)

### Shared libraries (not steps — imported by the scripts above)

| File | Purpose |
|---|---|
| `MODULES/simulation_validation_utils.py` | Common helpers: logging, config, parsing, scoring, plotting, geometry, uncertainty |
| `MODULES/feature_space_config.py` | Shared feature-space catalog/config resolution helpers |
| `MODULES/uncertainty_lut.py` | LUT loader + interpolation helpers used by downstream inference |

## Directory layout

Each step lives in its own directory (`STEP_N_<NAME>/`). Step-owned configs
live in an `INPUTS/` subdirectory and generated artifacts go to `OUTPUTS/`:

```
STEP_N_<NAME>/
  script.py
  INPUTS/
    config_step_X.Y_*.json      first-consumed config files for that step
  OUTPUTS/
    FILES/               CSVs, JSONs, markdown reports
    PLOTS/               PNG figures
```

## Running

### Full pipeline (current runner)

```bash
./run_new_pipeline.sh                     # all steps (1.1 → 4.2)
./run_new_pipeline.sh 1.1 1.2 1.3        # selected steps
./run_new_pipeline.sh --from 2.1         # run from a step onward
./run_new_pipeline.sh --list             # show step IDs and descriptions
```

Each step writes to `STEP_*/.../OUTPUTS/{FILES,PLOTS}`.

## Configuration

Each step reads parameters in this priority order:

```
CLI argument  >  STEP-local `INPUTS/config_step_1.1_runtime.json` override  >  STEP-local `INPUTS/config_step_1.1_plots.json` key  >  STEP-local `INPUTS/config_step_1.1_columns.json` key  >  STEP-local `INPUTS/config_step_1.1_method.json` key  >  hardcoded default
```

Main configuration files now live in the `INPUTS/` directory of the first step that consumes them:

- `STEPS/STEP_1_SETUP/STEP_1_1_COLLECT_DATA/INPUTS/config_step_1.1_method.json`
- `STEPS/STEP_1_SETUP/STEP_1_1_COLLECT_DATA/INPUTS/config_step_1.1_columns.json`
- `STEPS/STEP_1_SETUP/STEP_1_1_COLLECT_DATA/INPUTS/config_step_1.1_plots.json`
- `STEPS/STEP_1_SETUP/STEP_1_1_COLLECT_DATA/INPUTS/config_step_1.1_runtime.json`
- `STEPS/STEP_1_SETUP/STEP_1_2_TRANSFORM_FEATURE_SPACE/INPUTS/config_step_1.2_feature_space.json`
- `STEPS/STEP_1_SETUP/STEP_1_5_TUNE_DISTANCE_DEFINITION/INPUTS/config_step_1.5_feature_groups.json`
- `STEPS/STEP_2_INFERENCE/STEP_2_1_ESTIMATE_PARAMS/INPUTS/config_step_2.1_columns.json`
- `.ATTIC/config_legacy.json`: deprecated keys kept only as reference

Current STEP 1 contract:

- STEP 1.1 defines column roles only: simulation parameters and general non-feature columns.
- STEP 1.2 defines the transformed feature space only: primary features, ancillary columns, and derived columns.
- STEP 1.2 also emits `STEP_1_SETUP/STEP_1_2_TRANSFORM_FEATURE_SPACE/OUTPUTS/FILES/feature_space_manifest.json`, which is the authoritative partition of the transformed table into primary features, ancillary columns, and passthrough columns for downstream STEP 1.3 / STEP 4.1 reuse.
- STEP 1.3 and STEP 4.1 should consume that manifest instead of re-deriving column families independently.

`config.json` has been retired.

## Dependencies

- Python 3.10+
- pandas, numpy, matplotlib
- scipy (optional — used for griddata interpolation and distance transforms)
