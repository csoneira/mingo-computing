# External large-data storage

`external_storage.conf` assigns large optional storage trees to the separate
`/home/data` filesystem:

- Parquet lakes: `/home/data/mingo/PARQUET_LAKES/MINGOxx`
- simulation step intermediates: `/home/data/mingo/SIMULATION_INTERSTEPS`

The in-repository logical paths stay stable and become directory symlinks only
after a verified copy and explicit cutover. Until cutover, the production
pipeline continues using its original in-repository paths. The offload helpers
never change task selection, skip, or reanalysis settings.

The mount was confirmed writable on 2026-11-03 with a small write/read/fsync
probe. The MINGO00–02 lakes (1,635 Parquet files, about 40 GiB) were
SHA256-verified and redirected; the local lake directories are now symlinks
and contain no local Parquet copies. Simulation INTERSTEPS still use the local
path: their guarded relocation refused cutover while simulation scheduler locks
were active. Use the helper READMEs for quiescence checks and cutover steps.
Keep `/home/data` mounted whenever production uses the lakes; mount it before
starting simulation if/when INTERSTEPS are redirected too.
