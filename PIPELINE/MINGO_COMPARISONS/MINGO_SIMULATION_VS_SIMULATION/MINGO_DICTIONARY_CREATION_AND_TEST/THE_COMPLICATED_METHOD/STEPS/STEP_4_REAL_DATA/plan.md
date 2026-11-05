# STEP_4_REAL_DATA — Plan

Apply the inference pipeline to real MINGO detector data.
STEP 1–3 build the dictionary from simulated data and calibrate
uncertainties.  STEP 4 feeds real observables through that same machinery:
collect metadata, run the estimator, attach uncertainties, and plot the
time series.

---

## 1. Position in the pipeline

```
STEP 1   Build dictionary           (simulated data)
STEP 2   Validate + uncertainty LUT (simulated data)
STEP 3   Synthetic time-series demo (simulated data)
                 ↓
STEP 4   REAL DATA                  ← this step
  4.1    Collect real data
  4.2    Infer, assign uncertainties, plot time series
```

STEP 4 reads `dictionary.csv` (STEP 1.2) and the uncertainty LUT
(STEP 2.3) as read-only inputs.  It never writes back to prior steps.

---

## 2. Directory layout

```
STEP_4_REAL_DATA/
├── plan.md
│
├── STEP_4_1_COLLECT_REAL_DATA/
│   ├── collect_real_data.py
│   └── OUTPUTS/
│       ├── FILES/
│       │   ├── real_collected_data.csv
│       │   └── real_collection_summary.json
│       └── PLOTS/
│           ├── STEP_4_1_1_event_count_histogram.png
│           └── STEP_4_1_2_timeline_coverage.png
│
└── STEP_4_2_ANALYZE/
    ├── analyze.py
    └── OUTPUTS/
        ├── FILES/
        │   ├── real_results.csv
        │   └── real_analysis_summary.json
        └── PLOTS/
            ├── STEP_4_2_1_flux_vs_time.png
            ├── STEP_4_2_2_efficiency_vs_time.png
            ├── STEP_4_2_3_distance_vs_time.png
            └── STEP_4_2_4_coverage_fraction_over_time.png
```

`OUTPUTS/` directories are created automatically; old plots are cleared
before each run (same convention as STEP 1–3).



---

## 4. STEP 4.1 — Collect real data

Same logic as STEP 1.1, but now instead of choosing MINGO00, use any station indicated in the config file: MINGO01, for example (load `task_*_metadata_specific.csv` per task, aggregate by `filename_base` keeping latest execution, concatenate)
**without** the join against simulation parameters — no ground truth exists.

Filter by date range (`date_from`, `date_to` in config) and task IDs (`task_ids` list in config).

Which tasks are loaded is controlled by the existing `task_ids` list:
`[1]`, `[3, 5]`, `[1, 2, 3, 4, 5]`, etc.


**Outputs:** `real_collected_data.csv`, `real_collection_summary.json`,
time series of some key columns.

---

## 5. STEP 4.2 — Analyze

Single script: estimate physical parameters, attach uncertainties,
produce time-series plots.

### Process

1. Load `real_collected_data.csv` and `dictionary.csv`.
2. Resolve feature columns (`"auto"` → `*_tt_*_rate_hz` columns present
   in both DataFrames, same logic as `step_2_1`), note that each task has its own preffix for the `*_tt_*_rate_hz` columns.
3. Run the estimator (`STEP_2_INFERENCE/estimate_parameters.py`, imported
   directly) on every row → `est_flux_cm2_min`, `est_eff_sim_1..4`,
   `est_cos_n`, `best_distance`, `n_candidates`.
