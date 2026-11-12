# Operations scripts index

This index groups the operations tools by the job an operator is trying to do.
It is a navigation layer over the current tree: **all scripts remain at their
existing paths**. Use the paths below when invoking tools and editing cron or
setup configuration.

The purpose-based groups are also the proposed order for a future physical
reorganization. That move should happen separately, after checking and updating
cron templates, setup/install code, shell helpers, documentation, and any
external operator commands that refer to the old paths.

## Data flow and storage

Tools that move, account for, repair, or archive pipeline data.

| Current location | Responsibility |
| --- | --- |
| `DATA_MAINTENANCE/FILE_FLOW_TRACKER/` | Track files through pipeline states; includes the watcher interface and its engine. |
| `DATA_MAINTENANCE/FIX_METADATA_FILES/` | Repair event metadata files. |
| `DATA_MAINTENANCE/FLUSH_FROM_UNPROCESSED/` | Move eligible files from unprocessed storage into the pipeline flow. |
| `DATA_MAINTENANCE/OFFLOAD_PARQUET_LAKE/` | Offload Parquet lake data; use its documented activation safeguards. |
| `DATA_MAINTENANCE/OFFLOAD_SIM_INTERSTEPS/` | Offload Digital Twin simulation intermediates; relocation is opt-in. |
| `DATA_MAINTENANCE/REMOTE_LOG_BACKUP/` | Back up remote station logs and prune backup history. |
| `DATA_MAINTENANCE/REMOTE_SYNC/` | Synchronize station-side scripts. |

## Host and runtime maintenance

Tools that maintain the analysis host, free retained space, or clean generated
runtime products.

| Current location | Responsibility |
| --- | --- |
| `MAINTENANCE/AUTO_CLEAR_SWAP/` | Clear swap when the host is idle. |
| `MAINTENANCE/CLEANERS/` | Selectively clean generated products and temporary data; includes Parquet lake consistency checks and the large-directory finder. |
| `MAINTENANCE/ERASE_ALL_CRON_LOGS/` | Trim retained cron logs and remove empty log paths. |

## Scheduling and process control

Shared launchers and tools that coordinate scheduled work or recover stuck
processes.

| Current location | Responsibility |
| --- | --- |
| `ORCHESTRATION/CRON_RUN_LOGGED/` | Run scheduled commands and record non-empty output and exit status. |
| `ORCHESTRATION/RESOURCE_GATE/` | Apply shared resource limits around scheduled work. |
| `ORCHESTRATION/SOLVE_STALE_LOCKS/` | Find and resolve stale pipeline locks. |
| `ORCHESTRATION/WATCHDOG_PROCESS_COUNTS/` | Monitor process counts. |
| `ORCHESTRATION/KILL_RUNNING_PROCESSES/` | Manual emergency process termination. |

## Monitoring and operational reports

Tools that inspect pipeline state, execution behavior, or configuration history.

| Current location | Responsibility |
| --- | --- |
| `OBSERVABILITY/AUDIT_PIPELINE_STATES/` | Audit pipeline state, with a shell launcher and Python implementation. |
| `OBSERVABILITY/EXECUTION_TOP_OFFENDERS/` | Report execution resource offenders. |
| `OBSERVABILITY/FOLLOW_COLUMNS/` | Generate column coverage/review reports. |
| `OBSERVABILITY/SEARCH_FOR_ERRORS/` | Search operational logs for errors and tracebacks. |
| `OBSERVABILITY/VERSION_CONTROL/` | Snapshot configuration for change tracking. |

## Notifications and operator interfaces

| Current location | Responsibility |
| --- | --- |
| `NOTIFICATIONS/TELEGRAM_BOT/` | Telegram interface, metadata plotting, bot watchdog, and `/restart_bot` helper. Configuration and credential files in this directory are runtime inputs; do not publish their contents. |
| `NOTIFICATIONS/STATUS_GUI/` | Interactive CSV, simulation, Step 1, and Task 2 status views. These are retained operator tools. |

## Developer and document utilities

| Current location | Responsibility |
| --- | --- |
| `DEVELOPER_TOOLS/` | Repository tree listing (`dirtree`) and script-header standardization. |
| `MISCELLANEOUS_TOOLS/EXPORT_TO_PDF/` | Convert Markdown documents to PDF. This is an operator document utility; its current folder name is a candidate to replace in a future reorganization. |

## Configuration and ownership

- The cron source of truth is `CONTEXTUAL/CONFIG/CONTENTS/cron/analysis_pc.crontab`;
  it is rendered and installed through `CONTEXTUAL/CONFIG/SETUP/`.
- Runtime state and logs belong under `CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/`,
  not beside these source scripts.
- `USAGE_AUDIT.md` records evidence about scheduled callers, tracked callers,
  documented manual tools, and operator decisions. No cron entry should be
  inferred from the presence of a script here.
- `../CRON_REVIEW.md` records the active schedule inventory and candidates for
  consolidation; it is a review document, not a second cron configuration.
- Retired tools and historical operational records are under
  `legacy/CONTEXTUAL_OPERATIONS/`; they are not part of the active workflow.

## Proposed physical ordering

When ready to move paths, use this order as the destination taxonomy:

1. `DATA_FLOW/` — current `DATA_MAINTENANCE/` tools.
2. `HOST_MAINTENANCE/` — current `MAINTENANCE/` tools.
3. `SCHEDULING/` — current `ORCHESTRATION/` tools.
4. `OBSERVABILITY/` — current `OBSERVABILITY/` tools.
5. `OPERATOR_INTERFACES/` — current `NOTIFICATIONS/` tools.
6. `DEVELOPER_TOOLS/` — retain the current developer utilities.
7. `DOCUMENT_UTILITIES/` — current `MISCELLANEOUS_TOOLS/EXPORT_TO_PDF/`.

Before changing any path, inventory references in the cron template, setup
scripts, shell initialization, documentation, and installed command wrappers;
then move one group at a time and verify those references. This index does not
itself authorize or perform those moves.
