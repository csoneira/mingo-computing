# Monitoring and quality assurance

*Last updated: March 2026*

Keeping an eye on both the hardware state and the data output is key to
long‑term station reliability.  This page describes the daily report, visual
checks and data‑driven diagnostics used for miniTRASGO.

## Daily PDF report

A cron job generates a PDF each night containing:

- Environment logs (temperature, humidity, pressure) for the past month.
- Trigger rates and multiplexer statistics for the last 4 days.
- Count and charge maps in both coincidence and self‑trigger modes.
- Mean charge per strip and streamer fraction plots.

The report is created by `/home/rpcuser/gate/bin/createReport.sh` and sent via
email with `/home/rpcuser/gate/bin/sendReport.sh`.  You can run these
manually for on‑demand checks.

The scripts merge `.mat` files stored under
`~/gate/system/devices/RPC0<n>/data/dcData/data` (one subfolder per RPC).
Modify the number of days included by editing
`software/conf/loadconfiguration.m` (`time2Show = <days>*24`).

## Visual hardware checks

- Blue LED on the underside of the PC blinks according to CPU load.
- PC chassis fan should spin continuously; a stalled fan indicates failure.
- Inspect all cables and gas lines for tight connections and lack of kinks.

## Data‑based diagnostics

All of the plots generated for the daily report can also be produced
interactively by the Python tools in `~/gate/bin/` and
`PIPELINE/MINGO_DIGITAL_TWIN/PLOTTERS/`.

### Time/charge correlations

Scatter plots of front vs back time and charge for each strip are a rapid
health check.  Ideal behaviour:

- Times: slope ≈ 1, narrow dispersion across the strip length.
- Charges: slope ≈ 1, few points on the axes (indicating missing channels).

Deviations point to wiring faults, bad connectors or electronics issues.

### Spatial maps

Heatmaps of event counts and mean charge across the 4×4 strip grid reveal
hotspots or dead regions.  A uniform count distribution (apart from the wide
strip) is expected; significant variations suggest problematic strips.  Mean
charge maps should be flat; persistent high‑charge spots often correspond to
streamer‑prone areas.

### Charge spectra

Histograms of calibrated charge should show a bimodal distribution: a low-
charge peak (normal avalanches) and a high‑charge tail (streamers).  The first
bin must be near zero; a shift indicates an offset calibration error.  Monitor
the streamer fraction and keep it at 1–2 % (never exceed 10 %).

### Log file alerts

The `checkFlow.py` script (hourly) monitors gas flow and will shut off HV if
flow < 100 AU.  Integrate this with the MATLAB alarm routine to email the
operator on shutdown.  Other log‑based checks include:

- HV voltage/current stability.
- Environment sensors within reasonable ranges.
- Trigger rates in self and coincidence modes.

## Automation and alarms

The station crontab includes tasks to auto‑clear swap, solve stale locks and
flush old logs (see `CONTEXTUAL/CONFIG/CONTENTS/cron/analysis_pc.crontab`).  There is also a
`persistent_telegram_bot_check.sh` script that ensures the Telegram notification
bot is running; failures are logged under `CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/CRON_LOGS/ANCILLARY/TELEGRAM_BOT`.

Operators should review the `error_finder.py` output periodically to catch
Python tracebacks or abnormal log entries.

## When to escalate

- HV current suddenly jumps >20 µA with no change in voltage.
- More than 5 % of events are classified as streamers for an extended period.
- Environment logs show temperature drift >5 °C or pressure anomalies.
- Daily report fails to generate or is missing data.

---

_Local preview: run `mkdocs serve` in the `DOCUMENTATION/` root._

