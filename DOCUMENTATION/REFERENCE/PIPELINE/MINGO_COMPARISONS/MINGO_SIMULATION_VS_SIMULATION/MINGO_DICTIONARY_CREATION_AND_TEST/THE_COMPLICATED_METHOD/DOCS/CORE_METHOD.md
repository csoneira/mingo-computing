# Core Method

This project is simpler than the current code size suggests.

At the highest level it does four things:

1. Build a clean simulated table.
2. Turn that table into a dictionary in feature space.
3. Learn how to compare two feature-space points and how to go back from features to parameters.
4. Apply that estimator to synthetic and real data, then attach empirical uncertainties.

## The Pipeline In One Line

`simulation parameters -> simulated observables -> feature-space table -> dictionary + distance + inverse map -> estimated parameters -> uncertainty LUT`

## What Each Main Step Really Does

### STEP 1.1

Collect the simulation-aligned base table.

- `parameter_columns`: the true simulation quantities we want to estimate later
- `general_columns`: useful metadata that must survive runtime but is not part of the feature space

Output: one clean joined table with explicit column roles.

### STEP 1.2

Define the feature space.

- `kept`: feature columns that remain as they are
- `new`: derived feature columns computed from explicit expressions
- `ancillary`: useful non-feature columns kept for checks, plots, or diagnostics

This is the step that says what the estimator is allowed to use as observables.

Output: transformed feature-space table plus a manifest describing primary features, ancillary columns, and passthrough columns.

### STEP 1.3

Split the transformed table into:

- `dictionary.csv`: the support points used as candidate matches
- `dataset.csv`: the holdout/evaluation sample

### STEP 1.4

Filter the dictionary and dataset so the feature-to-parameter relation is locally usable.

This rejects problematic rows before tuning and inference.

### STEP 1.5

Tune the distance definition and the inverse-map runtime parameters.

This writes `distance_definition.json`, which is the contract used later by inference.

### STEP 2

Use the tuned estimator on simulated holdout data.

- STEP `2.1`: estimate parameters
- STEP `2.2`: compare estimates against simulation truth
- STEP `2.3`: build the empirical uncertainty LUT

### STEP 3

Apply the same inference pipeline to a synthetic time series, as a full worked example.

### STEP 4

Apply the same inference pipeline to real data.

## The Core Tools

### 1. Feature-space distance

Two rows are compared in feature space, not in parameter space.

The total distance is a weighted combination of distance terms:

- one-feature vectors: the old scalar case, now treated uniformly as 1D vectors
- grouped vectors: several columns produce one distance value together

Examples of grouped vectors:

- `rate_histogram`
- `efficiency_vectors`

The important point is that a grouped term produces:

`N feature columns -> 1 distance value`

So the histogram bins or efficiency-profile bins are not tuned independently as if they were unrelated scalar features.

### 2. Distance inside each term

Each term can use its own internal comparison rule.

Current examples:

- histogram-style ordered-vector distance
- efficiency-vector ordered-vector distance

Those term definitions live in:

- `config_step_1.5_feature_groups.json`

The term config controls things like:

- normalization
- `p` norm
- amplitude vs shape vs slope vs CDF contribution
- fiducial masking
- minimum valid bins
- reduction over sub-vectors

### 3. Weighting between terms

After each term produces one distance value, STEP `1.5` tunes the relative weight of the terms.

Example:

- `rate_histogram = 0.25`
- `efficiency_vectors = 1.0`

That means both terms contribute, but the efficiency-vector term is stronger in the final total distance.

### 4. Neighbor selection

Once distances are computed from one data row to all dictionary rows, the code selects candidate neighbors.

Main choices:

- `nearest`
- `knn`
- `all`

If `knn` is used, then `k` is the number of neighbors kept.

### 5. Neighbor weighting

After the neighbors are selected, they are weighted before estimating parameters.

Main modes:

- `uniform`
- `inverse_distance`
- `softmax`

This controls how strongly the best matches dominate the estimate.

### 6. Inverse map

The inverse map converts matched dictionary neighbors back into estimated parameters.

Main modes:

- `weighted_mean`
- `weighted_median`
- `local_linear`

Interpretation:

- `weighted_mean`: smooth average in parameter space
- `weighted_median`: robust average in parameter space
- `local_linear`: local affine regression around the query point

This is the key distinction:

- distance defines who is close
- weighting defines how much each close point matters
- inverse map defines how the final parameter estimate is computed from those points

### 7. Uncertainty LUT

STEP `2.3` does not change the estimate.

It learns an empirical lookup table of expected errors as a function of:

- estimated flux
- estimated efficiency
- event count

That LUT is then applied in STEP `3.3` and STEP `4.2`.

## The Current Hard Contracts

These are the important safety rules that should not be violated.

### Complete primary feature space only

Rows with incomplete primary feature vectors must not be used for:

- dictionary construction
- continuity filtering
- distance tuning
- inference

Missing primary features are not ordinary NaNs. They mean the point does not exist in the declared feature space.

### Exact STEP 1.5 alignment at runtime

Runtime inference must use the same feature-space contract that STEP `1.5` tuned.

So:

- missing STEP `1.5` artifact is an error
- projected-subset alignment is an error
- silent fallback to a generic z-score distance is an error

### No silent feature-space substitution

If explicit configured feature columns are missing, or if a catalog selects nothing, the runtime must fail.

It must not silently switch to:

- the intersection of available columns
- an automatic feature selection fallback

## The Main Artifacts

These are the core outputs that define the method.

- STEP `1.2` manifest:
  `feature_space_manifest.json`
- STEP `1.4` selected features:
  `selected_feature_columns.json`
- STEP `1.5` tuned method:
  `distance_definition.json`
- STEP `2.3` uncertainty calibration:
  `uncertainty_lut.csv`

## If You Want To Reason About The Project Quickly

Think in this order:

1. What are the primary features?
2. How are they grouped into distance terms?
3. How is each term compared?
4. How are term distances weighted together?
5. How are neighbors selected and weighted?
6. How is the inverse estimate built from those neighbors?
7. How is uncertainty attached afterward?

If those seven questions are answered clearly, the project is understandable.
