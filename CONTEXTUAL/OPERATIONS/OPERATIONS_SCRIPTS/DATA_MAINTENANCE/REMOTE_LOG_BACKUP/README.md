# Remote Log Backup

The scripts in this directory maintain an append-safe backup for the remote log
trees on `mingo01`, `mingo02`, `mingo03`, and `mingo04`.

This job copies only each station's `/home/rpcuser/logs/` tree into this
analysis PC's ignored runtime directory. It is not an off-site backup and does
not copy HLD data or fetch from CESGA.

The station crontab has a separate CESGA job (`/home/rpcuser/bin/backupCesga.sh`)
that copies `/media/externalDisk/hlds/done/` to
`trasgo@mastercr1.igfae.usc.es:/lustre/Trasgo/mingo01` (the tracked crontab
shows this destination for mingo01). The analysis pipeline separately fetches
reprocessing HLD files from `rpcuser@backuplip:/local/experiments/MINGOS/`.
The repository does not show how CESGA data reaches `backuplip`; the station's
`backupLIP.sh` cron entry is commented out. It also does not define an off-PC
backup destination for this analysis machine's runtime data/products.

Mutable backup data is stored separately under:

`CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/REMOTE_LOG_BACKUP/`

## Layout

- `hosts/<host>/current/`: exact copy of the latest successful backup of `/home/rpcuser/logs`.
- `hosts/<host>/history/<timestamp>/`: old versions and deleted files moved out of `current/` during that run.
- `hosts/<host>/latest`: symlink to `current/`.
- `hosts/<host>/current_manifest.tsv`: inventory of the latest backed-up files.
- `hosts/<host>/run_logs/`: per-run rsync logs.
- `runtime/run_summaries/`: one TSV summary per full backup run.

## Backup and retention behavior

- The runner uses `rsync --backup --backup-dir=... --delete`.
- `current/` stays faithful to the remote tree, including moves into `done/`.
- Anything that would be overwritten or deleted from `current/` is moved into `history/<timestamp>/`.
- If a remote machine becomes empty, its previous logs are moved into `history/` instead of disappearing from the backup.
- After each successful host backup, history is pruned against
  `MINGO_ANALYSIS_SCRIPTS/CONFIG_FILES/config_selection.yaml`: a file is retained
  when its dated filename (or mtime for undated files) falls inside a selected
  station date range, with one calendar month of context before and after.
- Retention fails closed: an unreadable or invalid selection config leaves
  history untouched.

## Usage

Run the backup manually:

```bash
bash /home/mingo/mingo-computing/CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/DATA_MAINTENANCE/REMOTE_LOG_BACKUP/run_log_backup.sh
```

The analysis-PC setup installs the fixed schedule, including the 12-hour
remote-log backup job:

```bash
bash /home/mingo/mingo-computing/CONTEXTUAL/CONFIG/SETUP/setup.sh --apply
```

The schedule is versioned in `CONTEXTUAL/CONFIG/CONTENTS/cron/analysis_pc.crontab`.

## Notes

- The default remote source is `rpcuser@mingo0X:/home/rpcuser/logs/`.
- The runner is locked with `flock`, so overlapping cron executions are skipped.
- For local testing, set `LOG_BACKUP_SOURCE_BASE=/path/to/mock_sources` and create one folder per host under that path.
