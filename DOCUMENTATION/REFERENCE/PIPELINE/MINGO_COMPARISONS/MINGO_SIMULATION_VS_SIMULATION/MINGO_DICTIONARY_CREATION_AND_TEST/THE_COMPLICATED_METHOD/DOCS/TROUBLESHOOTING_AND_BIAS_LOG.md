---
title: Troubleshooting and Bias Log
description: Consolidated development issues, fixes, and validation guidance for the inference dictionary pipeline.
last_updated: 2026-02-24
status: active
supersedes:
  - TROUBLESHOOTING/troubleshooting.md
  - TROUBLESHOOTING/BIAS_CORRECTIONS.md
  - TROUBLESHOOTING/STEP_3_ISSUES_LOG.md
---

# Troubleshooting and Bias Log

## Table of contents
- [Refactor summary](#refactor-summary)
- [Validation guidance](#validation-guidance)
- [Resolved bias and behavior issues](#resolved-bias-and-behavior-issues)
- [Open technical debt](#open-technical-debt)

## Refactor summary
Key modernization performed:
- shared utility extraction to `MODULES/simulation_validation_utils.py`
- structured logging adoption (`setup_logger()` patterns)
- consistent config resolution (`CLI > config > default`)
- standardized output layout (`OUTPUTS/FILES`, `OUTPUTS/PLOTS`)

## Validation guidance
Use these checkpoints:
1. Dictionary integrity
- verify join-key uniqueness,
- inspect coverage over `(flux, cos_n, efficiencies, z positions)`.

2. Estimation correctness
- residuals should reduce with event count,
- compare at least two scoring metrics.

3. Bias diagnostics
- stratify in-dictionary vs strict off-dictionary cases,
- inspect relation between error and dictionary distance.

4. Uncertainty calibration
- expected monotonic error decrease with event count until floor,
- coverage behavior near 1-sigma/2-sigma/3-sigma expectations.

## Resolved bias and behavior issues

### 2026-02-12: off-dictionary leakage
Problem:
- "off-dict" group included parameter sets already represented in dictionary (different event count only).

Fix:
- strict off-dict definition now excludes rows matching dictionary parameter sets via:
  - exact `param_hash` match when available,
  - fallback rounded true-parameter tuple match.

Result snapshot:
- in-dict: 74
- off-dict raw: 255
- excluded overlaps: 7
- off-dict strict: 248

### STEP_3 issue batch (resolved)
- config structure completion for STEP_3.2
- plot duplication and naming cleanup
- overlay readability fixes
- randomized highlight selection when no seed provided
- basis-source correction to dataset-centric behavior
- event-count conditioning reworked to tolerance-based logic
- multiplicity bias fix: one basis row per parameter set per target point

## Open technical debt
- [ ] Add unit tests for scoring/parsing helpers.
- [ ] Add type annotations for remaining utility functions.
- [ ] Formalize validity masks (`events >= N_min`, max dictionary distance thresholds).
- [ ] Run real-data comparison phase and document transferability limits.

Stale-note flag:
- Earlier entries that describe one-time plotting preferences without reproducibility criteria were not migrated; re-add only if they become part of formal validation requirements.
