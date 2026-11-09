# TT13 angle geometry and hit-map follow-up (2026-11-01)

This PDF compares angle-dependent conditional TT efficiencies before and after a four-plane geometric fiducial selection, shows normalized plane hit-position maps for MINGO00, MINGO01 and MINGO02 in each angle gate, and includes MINGO02 where acquisition intervals can be matched to voltage logs.

Definitions: e2|P4 hit = N1234/(N1234+N134); e2|P4 miss = N123/(N123+N13); closure = (1-e2|P4 miss)/(1-e2|P4 hit). These are conditional hit fractions, not universal intrinsic efficiencies. The comparison assumes the reference planes and P4 state do not introduce additional correlated selection effects.

No charge-amplitude cuts were used. Angle is reconstructed from P1/P3 x/y positions, and y is charge-weighted. Four-plane fiducial uses linear P1/P3 extrapolation and the configured ±116 × ±143.5 mm active rectangle; this is an approximate acceptance control.

MINGO02 selection uses 144 files with acquisition start/end timestamps that overlap station voltage logs, grouped into two LIP voltage groups. The remaining 552 Task-0-specific metadata rows have no acquisition interval and are not assigned HV using processing times. MINGO01 uses 175 files mapped to exact CAEN HV settings (one of 176 matching source records lacked a parquet).
