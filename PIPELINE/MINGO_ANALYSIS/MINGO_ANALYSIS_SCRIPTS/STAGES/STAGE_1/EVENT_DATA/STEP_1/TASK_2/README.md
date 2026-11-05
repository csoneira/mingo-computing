# Task 2 calibration river

```text
Create calibration subsample
        |
Apply initial row filters
(charge gate → topology → raw T_sum)
        |
Filtered main calibration subsample
        |
        +── fit_mask for calibration 1
        |       |
        |   temporary subsubsample
        |       |
        |   calculate calibration values
        |       |
        +───────+
        |
Apply calibration 1 values to the full main calibration subsample
        |
Apply calibration 1 post-filter to the full main calibration subsample
        |
        +── fit_mask for calibration 2
        |       |
        |   temporary subsubsample
        |       |
        |   calculate calibration values
        |       |
        +───────+
        |
Apply calibration 2 values to the full main calibration subsample
        |
Apply calibration 2 post-filter
        |
Repeat for QFB → Q–TDIF → T_sum → slewing
        |
Apply the final calibration values to the real working sample
        |
Apply the final calibrated-strip gate to working_df
(if one of Q_sum_cal/Q_dif_cal/T_sum_cal/T_dif_cal is outside its
configured limit, zero exactly those four values for that strip)
```

The `fit_mask` creates a temporary branch from the current state of the main
calibration subsample. That temporary subsubsample is used only to calculate
the calibration coefficients.

The resulting coefficients are applied to the full current calibration
subsample through the stage's broad `application_mask`. The stage's
`post_application_filter` is then applied to that full calibration subsample.
The following calibration therefore branches from the newly calibrated and
filtered state.

Charge limits never remove rows. Only the exact topology/plane-combination and
raw T-sum selections remove rows. Intermediate post-application
filters reject individual strips by zeroing their complete
`Q_sum`/`Q_dif`/`T_sum`/`T_dif` component blocks.

The final `working_sample.final_calibrated_strip_gate` is deliberately narrower:
it runs after slewing and changes only the four final calibrated columns of the
failing strip. It does not change any raw column, auxiliary derived column,
topology, plane combination, metadata, or row count.
