# Codex task: split completed reanalysis into two explicit modes

Repository: `/home/mingo/mingo-computing`

## Objective

Separate the current completed-file reanalysis behavior into two independent configuration options throughout the Stage-1 processing pipeline:

1. **Reprocess files from `COMPLETED_DIRECTORY`** to keep a task flowing over already completed inputs when there is no ordinary work waiting.
2. **Force files from `UNPROCESSED_DIRECTORY` through the task even when the task believes they were already processed**, for example because matching outputs or metadata already exist.

These are different operations and must not be controlled by one combined boolean.

Use clear configuration keys consistently. Recommended names:

```yaml
reprocess_from_completed: false
reprocess_from_unprocessed: false
```

The first key controls eligibility of inputs physically in `COMPLETED_DIRECTORY`. The second controls duplicate/output-exists checks for inputs physically in `UNPROCESSED_DIRECTORY`. Neither key should implicitly enable the other behavior.

## Inspect before editing

Inspect the actual local tree and its current changes before modifying files. Preserve unrelated user changes. Do not reset, clean, discard, or overwrite them.

Audit all relevant selectors and configuration loaders, including:

- Coincidence Stage-1 Task 0 through Task 5 scripts under `PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_1/EVENT_DATA/COIN_TRIGGER/`.
- Self-trigger Task 1 and Task 2 scripts under `.../EVENT_DATA/SELF_TRIGGER/`.
- Their task configs under `PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/SUPPORT/CONFIG_FILES/STAGE_1/EVENT_DATA/STEP_1/`.
- Shared file-selection, status, output-existence, lake/metadata duplicate checks, joined-file selection, and task orchestration code.
- Any station-specific effective-config overlays or runtime configuration paths.

The current code uses `complete_reanalysis` in several task scripts, alongside `file_selection_mode`, `last_file_test`, file-state directories, and output-existence logic. Trace each use; do not mechanically rename the key and assume the semantics are equivalent.

## Required behavior

Preserve the existing task selection modes and their meaning. The new options must work with both `last_file_test` and `file_selection_mode` rather than replacing them.

Selection precedence should preserve normal pipeline flow:

1. Respect QA-only/retry selection restrictions whenever active.
2. Continue to handle valid files already in `PROCESSING_DIRECTORY` according to the existing recovery behavior.
3. Prefer eligible files from `UNPROCESSED_DIRECTORY` as the task does today.
   - With `reprocess_from_unprocessed: false`, preserve existing duplicate/output-exists protections.
   - With `reprocess_from_unprocessed: true`, allow an otherwise eligible unprocessed input to run even if matching output files, metadata/status records, or other existing processed markers are present.
4. Only when ordinary eligible work is exhausted, permit selection from `COMPLETED_DIRECTORY` if and only if `reprocess_from_completed: true`.
5. With `reprocess_from_completed: false`, do not pull a file from `COMPLETED_DIRECTORY` just because forced-unprocessed mode is enabled.

The task must record/log which source state supplied the input (`UNPROCESSED`, `PROCESSING`, or `COMPLETED`) and the effective values of both options. Keep existing filename identity, joined-file, ordering/random/latest selection, station, and QA rules intact.

## Safe output replacement

Forced reprocessing may produce an output whose destination already exists. Inspect the existing write/replace path for every task and preserve the old valid output if a rerun fails before successfully writing its replacement. Reuse existing atomic-write or backup behavior where available. Do not delete prior outputs preemptively, and do not create duplicate outputs under new names unless that is already the task's contract.

Do not change scientific processing, filtering, schemas, output naming, metadata meaning, or cron schedules as part of this change.

## Configuration migration

Add both explicit keys to the checked-in configs for the applicable coincidence and self-trigger tasks.

Migrate existing `complete_reanalysis` values without changing current behavior:

- Existing `complete_reanalysis: true` maps to `reprocess_from_completed: true` and `reprocess_from_unprocessed: false`.
- Existing `complete_reanalysis: false` maps to both new options set to `false`.

Audit any station/runtime overlays before deciding their migration. If backward compatibility is needed for an overlay or external config that still contains only `complete_reanalysis`, support it as a deprecated fallback for `reprocess_from_completed` only; default `reprocess_from_unprocessed` to `false`. If a new key is explicitly present, it takes precedence. Emit a clear deprecation warning only where the legacy key is actually consumed.

Do not enable forced processing of already-processed `UNPROCESSED` files by default. It must require its own explicit true setting.

## Regression tests

Add focused tests using temporary synthetic task directories and lightweight fixtures. Cover at least:

- Both options false: ordinary selection and duplicate protection are unchanged.
- Completed reprocessing true alone: a completed input is selected only after normal eligible work is exhausted.
- Forced unprocessed true alone: an unprocessed input is processed despite an existing matching output/status marker, and no completed input is selected as a consequence.
- Both true: unprocessed work retains priority; completed inputs become eligible after that work is exhausted.
- `last_file_test` and random/latest selection still operate as configured.
- QA-only mode cannot escape its retry list through either new option.
- Joined-file selection does not move an already-processing file twice and preserves the intended source state.
- Re-running over an existing output does not destroy that output if processing fails.
- Every coincidence and self-trigger task reads the new settings from its effective config.
- Legacy `complete_reanalysis` fallback behaves as described if retained.

Avoid importing or executing full production task scripts in tests where that would start processing. Extract or exercise the existing selection helpers safely.

## Validation and operational limits

Run the focused task-selection tests and relevant existing tests. Run Python syntax checks on every modified script. Validate all edited YAML files parse and contain the expected values.

Do not move production files between task directories, modify installed crontab entries, restart services, or launch a production-wide reanalysis as part of implementation. Do not change current production configuration values beyond the explicit behavior-preserving migration above.

Review `git diff --check` and the final diff. Report:

- The two new option names and exact semantics.
- Every task/config path updated.
- How legacy `complete_reanalysis` handling works.
- Tests and checks run.
- Any task whose selector could not safely support the split, with the concrete reason.
- Confirmation that forced-unprocessed mode remains off by default and current completed-reanalysis behavior is preserved.
