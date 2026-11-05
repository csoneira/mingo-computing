# Ancillary Parquet Lake offload

This helper copies station lakes to a different filesystem and, at cutover,
replaces each entire lake directory with a directory symlink. Files beneath that
symlink remain regular files, preserving file-flow tracking's existing
`os.scandir(...).is_file(follow_symlinks=False)` checks. No pipeline skip,
selection, reanalysis or calibration configuration is changed. New pipeline
writes use the external lake automatically; no periodic mover is required.

Default destination: `/home/mingo/data/PARQUET_LAKES/MINGOxx`.
Production alias: `/home/mingo/data -> /home/data/mingo`.
The helper refuses destinations on the source filesystem.

```bash
# Inventory; no lake changes.
python3 CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/DATA_MAINTENANCE/OFFLOAD_PARQUET_LAKE/offload_parquet_lake.py

# Copy/verify while the pipeline continues. Source files remain untouched.
python3 CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/DATA_MAINTENANCE/OFFLOAD_PARQUET_LAKE/offload_parquet_lake.py --apply

# Final cutover ONLY after closing production-enabled, pausing all task launchers,
# and waiting for existing Task-5 writers to finish; restore launchers/gate afterwards.
python3 CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/DATA_MAINTENANCE/OFFLOAD_PARQUET_LAKE/offload_parquet_lake.py --apply --activate
```

The helper refuses activation while production is enabled or a Task-5 script is
running. Closing the production gate alone does not stop existing looped guides:
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

`/home/data` is a separate 916 GB ext4 filesystem on `/dev/sda1`, with about
862 GB available. The original station lakes total approximately 84.1 GiB.
The alias was installed after verifying `/home/mingo/data` was empty.
The copy attempt stopped immediately with EIO creating
`/home/data/mingo/PARQUET_LAKES`. `findmnt -T /home/data/mingo` reported
`rw,relatime,shutdown`. No parquets were copied, removed or redirected; the
production gate and existing analysis processing were not changed. Simulation
remains disabled pending disk diagnostics/repair and successful offload.
Do not run filesystem repairs against the mounted filesystem. Obtain privileged
kernel diagnostics first; this process cannot read the kernel log as mingo.

Tests:
`python3 -m unittest discover -s CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/DATA_MAINTENANCE/OFFLOAD_PARQUET_LAKE/tests -v`
