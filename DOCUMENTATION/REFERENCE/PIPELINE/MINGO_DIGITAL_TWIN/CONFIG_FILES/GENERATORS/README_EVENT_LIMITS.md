# Efficiency-Dependent Event Limits

`event_limits_by_min_efficiency.csv` controls how many tracks STEP 1 generates
for new parameter-mesh rows.

STEP 0 calculates:

```text
minimum_efficiency = min(eff_p1, eff_p2, eff_p3, eff_p4)
```

It selects the matching efficiency interval and stores its
`recommended_n_tracks` value in the new parameter-mesh row. STEP 1 then uses
that row-specific value instead of the fixed runtime fallback.

The lookup ratio is:

```text
requested_over_original_ratio = requested_rows / original_rows
```

The recommended limit uses the configured ratio quantile and safety factor.
This avoids sizing generation from an unusually favorable simulation.

Regenerate the lookup after enough new STEP FINAL observations accumulate:

```bash
python3 PIPELINE/MINGO_DIGITAL_TWIN/CONFIG_FILES/GENERATORS/generate_event_limits_by_min_efficiency.py
```

The generator also writes:

```text
PIPELINE/MINGO_DIGITAL_TWIN/CONFIG_FILES/GENERATORS/event_limits_by_min_efficiency.csv
PIPELINE/MINGO_DIGITAL_TWIN/CONFIG_FILES/GENERATORS/event_limits_by_min_efficiency.png
PIPELINE/MINGO_DIGITAL_TWIN/CONFIG_FILES/GENERATORS/event_limits_by_min_efficiency.pdf
```

The diagnostic figure shows individual ratios, per-bin medians, the selected
ratio quantile, the explicit safety margin, recommended track limits, and the
number of observations supporting each efficiency bin.

Existing parameter-mesh rows without `n_tracks` retain the fallback value so
their existing `step_1_id` mapping remains stable. New rows receive the
efficiency-dependent limit.
