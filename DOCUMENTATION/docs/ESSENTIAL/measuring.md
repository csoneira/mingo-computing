# Data acquisition and measurement procedures

*Last updated: March 2026*

This page summarises the routine commands and best practices for operating a
miniTRASGO station during a measurement run.

## Starting a run

1. Ensure the DAQ has been initialised (`./startDAQ` in
   `~/gate/trb399sc/`).
2. Confirm that the high voltage is set and gas flow is nominal (see
   [Configuration](configuration.md)).
3. From the same directory, launch data recording:

   ```bash
   ./startRun.sh
   # files written to /media/externalDisk/hlds/
   ```

   The script prints a rolling status message.  Stop the acquisition with
   `CTRL+C`.

4. Data are stored as binary `.hld` files.  Use the `daq_anal` utility to
   inspect contents:

   ```bash
   daq_anal /media/externalDisk/hlds/2026-03-01_0001.hld
   ```

   An empty output indicates a problem; empty files are ignored by the
   processing pipeline.

## Thresholds and trigger rates

- The nominal discriminator threshold is -40 mV; this value is applied by
  `./startDAQ` but can be adjusted manually via
  `~/gate/trb399sc/setThresholds.sh`.
- Check the current count rate online via the Rate.mat file or the CTS web
  panel.  ``Trigger accepted`` counts should roughly equal ``trigger
  asserted`` counts when the system is healthy.
- Self‑trigger (TT2) can be enabled via cron or manually by running the
  trigger script in `~/trbsoft/userscripts/trb399sc/trigger/`.

## File management

- `.hld` files are rotated every hour by default; ensure there is ample
  disk space on `/media/externalDisk` (≥10 GB recommended).
- After a run ends, the analysis pipeline ingests new `.hld` files from
  STAGE 0 (simulation ingestion).  To force an immediate ingestion, run:

  ```bash
  python PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/SIMULATION/ingest_simulated_station_data.py
  ```

- Use `gzip` to compress old `.hld`, `.log`, and `.mat` files for long‑term
  storage; checksums can be calculated with `sha256sum`.

## Checklist before/after data taking

- [ ] HV on and stable.
- [ ] Gas flow ≥ 100 AU.
- [ ] Thresholds set to nominal values.
- [ ] CTS trigger configuration verified.
- [ ] Monitoring scripts (`createReport.sh`) running without errors.
- [ ] Enough disk space available (`df -h` on `/media/externalDisk`).

## Special considerations

- Changing HV during a run may cause the subsequent `.hld` file to contain
  data for two different voltages; split such files manually before processing.
- Mobility of nearby objects (phones, laptops) can introduce noise; clear the
  area around the detector before a long run.

---

_Local preview: run `mkdocs serve` in the `DOCUMENTATION/` root._

