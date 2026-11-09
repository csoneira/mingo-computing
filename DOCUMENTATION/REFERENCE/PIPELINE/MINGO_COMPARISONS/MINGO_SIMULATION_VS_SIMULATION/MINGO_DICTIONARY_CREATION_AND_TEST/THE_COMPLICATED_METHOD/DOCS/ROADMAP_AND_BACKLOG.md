---
title: Dictionary Roadmap and Backlog
description: Consolidated workflow design and active tasks for INFERENCE_DICTIONARY_VALIDATION.
last_updated: 2026-02-24
status: active
supersedes:
  - NEW_ORGANIZATION.md
  - TASKS/to_do.md
  - TASKS/to_do_new.md
  - TASKS/more_urgent.md
---

# Dictionary Roadmap and Backlog

## Table of contents
- [Workflow design](#workflow-design)
- [Active backlog](#active-backlog)
- [Method options under evaluation](#method-options-under-evaluation)
- [Completed items](#completed-items)
- [Stale or underspecified TODOs](#stale-or-underspecified-todos)

## Workflow design

### STEP_1: dataset and dictionary construction
1. Collect simulation-aligned metadata from STEP_1 task outputs.
- Source metadata: `PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO00/STAGE_1/EVENT_DATA/STEP_1/TASK_*/METADATA/task_*_metadata_specific.csv`
- Join with: `PIPELINE/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/SIMULATED_DATA/step_final_simulation_params.csv`

2. Apply controlled geometry selection.
- filter on chosen `z_plane` configuration,
- if unspecified, choose one valid configuration explicitly (do not silently mix all geometries).

3. Build two views:
- `data`: broad filtered sample,
- `dictionary`: high-quality subset with one representative per parameter set (prefer highest event count).

### STEP_2: inverse problem and validation
1. Implement reusable estimator function:
- input: dictionary path + dataset path + metric/config
- output: estimated parameter vectors

2. Validate estimator:
- estimated vs true parameters,
- relative errors vs event count,
- parameter-space error maps (for example flux/efficiency surfaces).

3. Produce uncertainty LUTs:
- bin across parameter dimensions and event count,
- compute quantiles,
- interpolate LUT uncertainty for new estimates.

## Active backlog

### P0
- [ ] Expand collection beyond task 1 (`task_ids: [1,2,3,4,5]`) where methodologically valid.
- [ ] Finalize production-grade estimator API for reuse on non-simulated data.
- [ ] Apply method to a bounded real-data validation window.

### P1
- [ ] Compare metrics (`l2_zscore`, `chi2`, Poisson-style scoring) by regime.
- [ ] Evaluate reduced feature subsets vs full trigger-rate vectors.
- [ ] Add automated LUT monotonicity checks vs event count.
- [ ] Add cross-validation (K-fold or leave-one-out) for uncertainty stability.

### P2
- [ ] Write end-to-end user guide for dictionary pipeline execution.

## Method options under evaluation
- Alternative distance metrics for nearest-neighbor/interpolation matching.
- Feature-selection strategies to improve robustness and reduce degeneracy.
- Validity masks based on event count and dictionary-distance thresholds.

## Completed items
- [x] Figure prefixes standardized by step and output order.
- [x] Refactoring extracted shared utilities into `MODULES/simulation_validation_utils.py`.
- [x] Logging/config/path handling standardized across step scripts.
- [x] Multiple STEP_3 plotting and contributor-selection issues corrected.

## Stale or underspecified TODOs
- [ ] "Calculate the quantiles right in ..." entry from older notes is incomplete; rewrite with target script, output schema, and acceptance criteria.
- [ ] Historical notes referring to old path `INFERENCE_DICTIONARY_VALIDATION/to_do.md` are superseded by this file.
