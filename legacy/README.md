# Legacy and recovery material

- `DATAFLOW_v3/` is the preserved former-name directory. It held only an old bot cron log when moved here.
- `DATAFLOW_v3-precleanup-20261021-090510/` is the pre-cleanup recovery bundle (patches and an untracked-files archive). Treat it as local recovery material; it is excluded by this machine's `.git/info/exclude` and must not be committed or published.
- `/home/mingo/.safe-mingo-computing/` is the active rsync backup mirror. It remains outside the repository; the managed and installed cron entries point there.

These are archival/runtime artifacts, not source trees or Stage-1 test results.
