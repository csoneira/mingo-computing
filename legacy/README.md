# Legacy and recovery material

- `DATAFLOW_v3/` is the preserved former-name directory. It held only an old bot cron log when moved here.
- `DATAFLOW_v3-precleanup-20261021-090510/` is the pre-cleanup recovery bundle (patches and an untracked-files archive). Treat it as local recovery material; it is excluded by this machine's `.git/info/exclude` and must not be committed or published.
- `ALL_MINITRASGO_from_fistensor2/` is a local historical dump (about 405 MiB before duplicate pruning) with nested repositories, unique data, and generated results. It is excluded by `.git/info/exclude`; see the [archive review](../DOCUMENTATION/REFERENCE/ALL_MINITRASGO_ARCHIVE_REVIEW.md) before retrieving anything. Do not add the dump wholesale.
- `/home/mingo/.safe-mingo-computing/` is the active rsync backup mirror. It remains outside the repository; the managed and installed cron entries point there.

Everything under `legacy/` is historical or recovery material, not active production code or Stage-1 test output.
