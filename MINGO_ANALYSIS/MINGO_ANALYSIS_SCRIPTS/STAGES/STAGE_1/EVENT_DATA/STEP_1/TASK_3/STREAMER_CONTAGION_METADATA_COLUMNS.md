# Task 3 Streamer Contagion Metadata Columns

This document defines the streamer-related columns added to
`task_3_metadata_specific.csv` by
`MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_1/EVENT_DATA/STEP_1/TASK_3/script_3_cal_to_list.py`.

## Hypothesis Being Tested

The streamer contagion analysis is designed to answer these three conditional questions:

1. Given a streamer in one strip, is a streamer in another strip more likely?
1. Given a streamer in one strip, is a remarkable (high-charge) hit in another strip more likely?
1. Given a streamer in one strip, is any activation (any non-zero charge) in another strip more likely?

In probability notation (source strip `i`, target strip `j`, and TT slice):

- Streamer to streamer: `P(S_j | S_i)`
- Streamer to high charge: `P(H_j | S_i)`
- Streamer to activation: `P(A_j | S_i)`

where:

- `S_k`: strip `k` is streamer-like (`Q_k > streamer_threshold_selected`)
- `H_k`: strip `k` is high-charge (`Q_k > streamer_high_charge_threshold_selected`)
- `A_k`: strip `k` is active (`Q_k > 0`)

## Core Threshold Columns

- `streamer_threshold_selected`
  - Auto-detected avalanche-streamer boundary from pooled `P*_Q_sum_final` values.
  - Unit: same as `Q_sum_final` (charge units used by Task 3).

- `streamer_high_charge_threshold_selected`
  - Remarkable-charge threshold used to probe correlations above the low-charge regime,
    while still below the streamer boundary.
  - Defined as `0.2 * streamer_threshold_selected`.

## Per-Plane Streamer Rate Columns

- `P1_streamer_rate`, `P2_streamer_rate`, `P3_streamer_rate`, `P4_streamer_rate`
  - For each plane `p`:
  - `P<plane>_streamer_rate = N(Q_sum_p > streamer_threshold_selected) / N(Q_sum_p > 0)`
  - Empty if threshold cannot be determined or plane data is unavailable.

## Per-TT Strip Contagion Matrix Families

All families are conditional probabilities at strip level and are TT-conditioned.
Rows are the "given/source" strip and columns are the "target" strip.

### Family A: Streamer -> Streamer

- Prefix: `streamer_contagion_streamer_to_streamer_...`
- Meaning: `P(target strip streamer | given strip streamer)`

### Family B: Streamer -> Active

- Prefix: `streamer_contagion_streamer_to_signal_...`
- Meaning: `P(target strip active (Q > 0) | given strip streamer)`

### Family C: Streamer -> High Charge

- Prefix: `streamer_contagion_streamer_to_highcharge_...`
- Meaning: `P(target strip high-charge | given strip streamer)`
- High-charge condition: `Q_target > streamer_high_charge_threshold_selected`.

## Column Templates Per Family

For each `<family_prefix>` in:

- `streamer_contagion_streamer_to_streamer`
- `streamer_contagion_streamer_to_signal`
- `streamer_contagion_streamer_to_highcharge`

and each selected TT panel `<tt>`:

- `<family_prefix>_selected_tts`
  - Comma-separated list of TT values included in the matrix export.

- `<family_prefix>_tt<tt>_event_count`
  - Number of events in that TT slice used for the matrix.

- `<family_prefix>_tt<tt>_given_count_<src_label>`
  - Denominator count for source strip `<src_label>` (for example `P1S1`, `P3S4`).

- `<family_prefix>_tt<tt>_<src_label>_to_<dst_label>`
  - Conditional probability value in the matrix cell:
  - `N(source && target && TT=tt) / N(source && TT=tt)`

## Notes

- TT selection follows the same plotting policy used by Task 3:
  - TT >= 10
  - At least 30 events in the TT slice
  - Up to 6 most populated TTs
- Empty values indicate undefined probabilities (for example zero denominator).
