# Ancillary Parquet Lake offload

This helper copies station lakes to a different filesystem and, at cutover,
replaces each entire lake directory with a directory symlink. Files beneath that
symlink remain regular files, preserving file-flow tracking's existing
`os.scandir(...).is_file(follow_symlinks=False)` checks. No pipeline skip,
selection, reanalysis or calibration configuration is changed. New pipeline
writes use the external lake automatically; no periodic mover is required.

The destination is read from `CONTEXTUAL/CONFIG/CONTENTS/storage/external_storage.conf`:
`/home/data/mingo/PARQUET_LAKES/MINGOxx`. The helper refuses destinations on
the source filesystem. `--destination` remains available as an explicit
one-run override.

```bash
# Inventory; no lake changes.
python3 CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/DATA_MAINTENANCE/OFFLOAD_PARQUET_LAKE/offload_parquet_lake.py

# Copy/verify while the pipeline continues. Source files remain untouched.
python3 CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/DATA_MAINTENANCE/OFFLOAD_PARQUET_LAKE/offload_parquet_lake.py --apply

# Final cutover ONLY after closing production-enabled, pausing all task launchers,
# and waiting for existing Task-5 writers to finish; restore launchers/gate afterwards.
python3 CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/DATA_MAINTENANCE/OFFLOAD_PARQUET_LAKE/offload_parquet_lake.py --apply --activate
```

The helper refuses activation while production is enabled or any Stage-1 task
writer is running. Closing the production gate alone does not stop existing looped guides:
the operator must pause them too. Final copying/checking and cutover run only
when writers are quiescent. Copies use destination-local temporary files, fsync,
SHA256 comparison and source signature checks. Successful verification records
are cached against source/destination inode, size and mtime. Unchanged verified
copies can be reused for cutover. External files must remain available and must
not be independently modified.

Linux renameat2(RENAME_EXCHANGE) atomically exchanges the lake directory and its
replacement symlink. There is no missing-lake window. Only then are verified
original files removed. Unexpected entries or changed files cause a refusal.
After an interrupted cutover, inspect the journal and any
`.offload-original-PARQUET_LAKE-*` directory beside the lake. Never remove that
backup blindly: it may hold originals not yet safely released. Unmounting the
external disk makes the offloaded lakes unavailable; do not resume production
with broken lake links.

Runtime cache, exclusive lock and journal:
`CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/STATE/parquet_lake_offload/`.
The helper does not delete external parquets or change cleaner configuration.
The category cleaner currently deliberately avoids directory symlinks; cleanup
of offloaded lake data is a separate, explicit retention decision.

## First production attempt, 2026-10-30

The first attempt stopped with EIO while the disk was failing. On 2026-11-03,
`/home/data` was mounted read-write on its separate ext4 filesystem and a small
write/read/fsync probe passed. MINGO00, MINGO01 and MINGO02 were copied and
SHA256-verified, then their in-repository lake directories were atomically
replaced with symlinks to the external copies. The production gate was briefly
closed, active Stage-1 writers were allowed to finish, and the original run
configuration was restored before the gate was reopened. New lake output for
these stations now lands directly on `/home/data`; no local lake copies remain.

Tests:
`python3 -m unittest discover -s CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/DATA_MAINTENANCE/OFFLOAD_PARQUET_LAKE/tests -v`
