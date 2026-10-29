# Calibration procedures

*Last updated: March 2026*

Periodic calibrations ensure that timing, charge and flow measurements from
the RPC stack are accurate and stable.  Perform these whenever a detector is
reconfigured or at the start of a measurement campaign.

## 1. Time‑to‑position calibration

The signal propagation velocity along each strip, as well as electronic
offsets introduced by varying cable lengths, must be calibrated so that the
time difference between front and back endpoints maps linearly to position.

### Quantile method (default)

Collect a large set of cosmic events and compute the 50th and 95th percentiles
of the `t_front - t_back` distribution for each strip.  The mid‑point of these
quantiles is used as the per‑strip time offset.

```bash
# run the calibration helper (example script placeholder)
~/bin/calibrate_time.sh --method quantile --input /path/to/hlds --output offsets.csv
```

### Regression method (alternative)

Perform a linear regression of `t_front` versus `t_back` for each strip; the
intercept gives the offset and the slope provides an effective velocity.

Both methods produce a `time_offsets.csv` file that is loaded by the
analysis pipeline and by the online monitoring scripts.

## 2. Gas flow meter calibration

Each flow meter reports an arbitrary unit (AU) with a device‑specific
offset.  Verify the offset by flowing a known rate and recording the meter
reading; store the calibration constant in
`~/gate/system/lookUpTables/flow_calibration.txt`.

These meters are primarily used for leak detection rather than absolute rate
measurements; a sustained drop below the nominal threshold (100 AU) should
automatically trigger HV shutdown (see [Monitoring](monitoring.md)).

## 3. Efficiency/plateau scan

Determine the optimal HV plateau by scanning voltage while recording detector
efficiency and streamer rate.  Use the included script:

```bash
~/bin/HV/plateau.sh --start 4.5 --stop 5.8 --step 0.05 --duration 60
```

The script produces a PDF summarising efficiency, charge and streamer
fraction.  Choose the operating voltage where the efficiency curve flattens
and streamers remain at 1–2 %.

## 4. TDC calibration

The TRB3sc TDCs require a multi‑point calibration to convert raw counts into
nanoseconds.  This is normally performed by running the `tdc_calibration.py`
scripts located in `~/trbsoft/` (consult Alberto Blanco for details).  Errors
in this calibration manifest as non‑integer values in the `c801` register and
should be addressed before taking physics data.

## 5. Charge calibration

The front‑end electronics produce a Time‑Over‑Threshold (TOT) pulse width
proportional to deposited charge.  The relationship is nonlinear; calibrate
it using a known charge injection source or by fitting the width spectrum.

Two components:

1. **Offset** – determine the zero point of the TOT measurement (use quiet
   runs with no incoming particles).
2. **Conversion curve** – map TOT width to Coulombs.  The script
   `~/bin/calibrate_charge.sh` produces a lookup table used by the offline
   analysis to convert raw widths to charge units.



## 6. Other calibrations

- **Flow meter linearity**: verify that all four channels have similar
  response slopes; discrepancies indicate a leaking or clogged pipe.
- **Temperature sensors**: compare internal and external bus readings and
  recalibrate if offsets exceed 0.5 °C.

---

_Local preview: run `mkdocs serve` in the `DOCUMENTATION/` root._

