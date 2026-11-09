# Preparing and configuring miniTRASGO

*Last updated: March 2026*

This page describes the procedures and scripts required to bring a
miniTRASGO station online after power‑up or transport.  It is intended for
station operators and newcomers who need to understand the software
components that must be running.

## Overview

1. Verify network/SSH access to the RPC control computer (`rpcuser@minitrasgo…`).
2. Ensure the Data Control System (DCS) daemon and cron jobs are running.
3. Start the TRB3sc data acquisition software (DAQ).
4. Configure the High Voltage (HV) system and environment sensors.
5. Confirm trigger settings via the CTS web interface.

Most of these tasks are automated by the crontab at boot, but manual control
is sometimes required during commissioning or after a crash.

## Data Control System (DCS)

The DCS manages the I2C‑connected hub that reads environmental sensors,
gas‑flow meters and the HV module.  The primary control script is

```
/media/externalDisk/gate/bin/dcs_om.sh
```

This script is invoked by cron every minute; you can also run it interactively
for debugging.  Configuration files and Look‑Up Tables reside under
`~/gate/system/lookUpTables/`.

### Log files

Sensor data are written to daily `.log` files in `~/logs/` (see
[Data section](../data/index.md) for formats).  A post‑run script moves
the previous day’s files into `~/logs/done/`.

## Starting the DAQ

DAQ software lives in `~/gate/trb399sc/` (a symlink from
`/home/rpcuser/userscripts/trb399sc/`).

```bash
cd ~/gate/trb399sc/
./startDAQ        # starts the TRB acquisition system and sets thresholds
                  # also registers a rate‑only logger (Rate.mat)
```

For normal operation you do not need to run `startDAQ` again after reboot;
cron handles that.  To begin recording full events, use

```bash
./startRun.sh    # begins writing .hld files to /media/externalDisk/hlds/
```

Stop a run with `CTRL+C` or by killing the `daq` process.  The `daq_anal`
utility can inspect `.hld` files (see [Measuring](measuring.md) page).

## High Voltage control

HV is adjusted via the command‑line utility at `~/bin/HV/hv`:

```
./hv -b <bus> -I <Ilim> -V <Vset> -on   # turn on with limit and set value
./hv -b <bus> -off                      # turn off
```

Values are in kV for voltage and µA for current.  For real‑time status:

```bash
watch -n 1 ./hv -b 0
```

The recommended operational strategy is to leave the voltage fixed near the
plateau and correct for efficiency changes in software rather than adjusting
HV for every ambient pressure/temperature variation.

## Trigger configuration

Open the CTS web panel at
`http://minitrasgo.fis.ucm.es:1234/cts/cts.htm` and select the desired
trigger type (standard TT1 or script‑driven TT2).  Trigger scripts live in
`~/trbsoft/userscripts/trb399sc/trigger/` and are executed automatically by
cron during self‑trigger tests.

## Crontab overview

The station’s crontab (`crontab -l` as rpcuser) contains entries for:

- DCS polling
- HV/gas-flow checks
- DAQ startup (`startDAQ` and `startRun` wrappers)
- Report generation and email notification
- Remote log archival and backup

Refer to `CONTEXTUAL/CONFIG/CONTENTS/cron/analysis_pc.crontab` in the main repository for the
cluster‑wide schedule; the station crontab mirrors the relevant lines.

## Troubleshooting

*If the DAQ fails to start*:

- Verify `trbnetd` is running (`pgrep -f trbnetd`).
- Check that the Ethernet cable between the RPC control PC and the TRB is
  connected and that the TRB has power.

*If the DCS logs stop updating*:

- Run `dcs_om.sh` manually to see error messages.
- Check I2C bus connectivity with `i2cdetect`.

*HV control errors* usually manifest as `ERROR` messages from `hv`; verify the
bus number and hardware connections.

---

_Local preview: run `mkdocs serve` in the `DOCUMENTATION/` root to see this
page rendered._

