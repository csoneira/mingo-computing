# Analysis PC setup

Run once after cloning on the analysis PC, as the pipeline user:

```bash
git clone https://github.com/csoneira/mingo-computing.git
cd mingo-computing
bash CONTEXTUAL/CONFIG/SETUP/setup.sh --apply
```

`setup.sh` is the only setup and verification command. `--dry-run` shows the
plan without changes; `--check` prints the same PASS/WARN/FAIL report without
installing anything. `--apply` backs up existing machine files, installs the
packages and pinned `.venv`, creates empty runtime directories, integrates a
small shell fragment and tmux launcher, configures the dedicated SSH key,
recovers known public logbooks and a checksum-verified TDC calibration, checks
credentials and sudo, installs cron, then prints the report. It is safe to
run again. Backups are stored in `~/.local/state/dataflow-recovery/`.

The cron schedule is [analysis_pc.crontab](../../../../../CONTEXTUAL/CONFIG/CONTENTS/cron/analysis_pc.crontab).
Setup expands the repository path and adds a managed block to the user's
crontab. It preserves unrelated entries and does not turn individual jobs on
or off based on the current machine state. The per-minute crontab
self-installer from the old schedule is gone. Each job runs with the repository
`.venv` first in `PATH`; `$PYTHON_BIN` points to its interpreter. If core
packages or Python are unusable, the installed cron block stays behind a
closed execution gate and the report says why. Missing remote hosts, data,
or credentials appear in the report but do not change the schedule.

### Run analysis for current station files

The analysis-PC cron template enables the Stage 0 `NEW_FILES` fetchers for
stations 1–4 every 15 minutes and the normal real-data analysis jobs that
consume their output. The fetch selection is controlled by
`PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/SUPPORT/CONFIG_FILES/STAGE_0/NEW_FILES/config_new_files.yaml`:
`new_files_run_matrix.enabled` turns the fetchers on or off, `selection.stations`
chooses stations, and `selection.date_ranges` limits eligible file dates.
Simulation and Stage 0 reprocessing cron jobs are commented out in the
analysis-PC template, so applying the setup schedule runs the current-file
analysis without either workflow. To install a reviewed template change, use
`bash CONTEXTUAL/CONFIG/SETUP/setup.sh --apply`; this also runs the documented setup and
prerequisite checks.

The four station-script deployment commands check the remote user and target
directory and complete a read-only rsync dry-run before any `--delete`
transfer. If the dry-run proposes deletions, the scheduled job stops and logs
the count. Inspect it manually with
`bash CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/DATA_MAINTENANCE/REMOTE_SYNC/sync_station_scripts.sh 1 --dry-run`;
`--allow-delete` is available for a reviewed manual deployment. An offline
station fails only its own job. Other jobs continue.

The [OPERATIONS scripts](../../../../../CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/) handle ongoing
processing and cron-log error collection. `cron_run_logged.sh` writes an
atomic latest-result CSV for each scheduled command under
`CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/CRON_STATUS/`; the existing file-flow tracker
writes data-flow status CSVs under its own runtime directory.
Setup's report is a point-in-time installation report; it is not a recurring
process supervisor. Use `bash CONTEXTUAL/CONFIG/SETUP/setup.sh --check` to inspect the
machine configuration later. The tmux monitor can be opened with
`start-dataflow-tmux` and is started at boot by the managed cron block.

SSH aliases and non-secret endpoints are in [CONTENTS/ssh/config](../../../../../CONTEXTUAL/CONFIG/CONTENTS/ssh/config).
The local key is `~/.ssh/id_ed25519_dataflow` (mode `0600`, no passphrase so
cron can use it). Setup never overwrites it or commits it. Review host-key
fingerprints before first access; enroll its public half interactively as
described in [the SSH guide](../CONTENTS/ssh/README.md). Host-key checking
stays enabled. Station 04 can remain off; its jobs will report connection
failures until it returns. Station computers have separate crontabs that this
analysis-PC setup does not install.

See [the secret manifest](../CONTENTS/secrets/README.md) for Telegram and
Copernicus credentials. They stay outside Git and can be restored later. A
restricted sudo policy allows only `swapoff` and `swapon`; setup validates it
with `visudo` and non-mutating `sudo -n` probes. The missing empirical
TOT-to-charge CSV is a scientific input: simulation uses the documented
linear approximation until the original is recovered. See [AUDIT.md](AUDIT.md)
for other unrecoverable state and its known sources.
