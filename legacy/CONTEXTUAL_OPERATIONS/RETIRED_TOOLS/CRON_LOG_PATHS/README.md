# Retired cron log path helper

`ensure_cron_log_paths.sh` parsed the rendered cron schedule to optionally
pre-create log directories and remove empty log files/directories. It had no
active cron or setup caller. The current `cron_run_logged.sh` creates a log
directory lazily only when a job emits output or fails, so this helper is not
needed in the active workflow.
