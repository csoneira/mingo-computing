# Unused code archive

This directory preserves code that is no longer part of an active execution
path because a current implementation supersedes it. Files are retained for
provenance and can be removed later after review.

## Stage 0 MATLAB snapshots

The nested `PIPELINE/MINGO_ANALYSIS/.../UNPACKER_ZERO_STAGE_FILES/` tree
preserves MATLAB Editor `.asv` autosave snapshots and the former
`lookUpTables_RPC.old.m`. Stage 0 config selects `lookUpTables_RPC.m`; no active
source references the old lookup table. The `.asv` files sit beside current
`.m` implementations and are not MATLAB runtime entry points. Some snapshots
differ from their current counterparts, so they are retained here instead of
deleted.

No active `*_0.m` or `*_2.m` files were moved: Stage 0 dispatch code calls some
of those explicitly. Superseded coin-trigger Step 1 implementations are
preserved in `MINGO_ANALYSIS/STEP_1_TASKS/` as scientific provenance.
