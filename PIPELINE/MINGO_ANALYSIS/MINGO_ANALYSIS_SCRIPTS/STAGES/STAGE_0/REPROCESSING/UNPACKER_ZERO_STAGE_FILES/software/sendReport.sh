# =============================================================================
# DATAFLOW_v3 Script Header v1
# Script: PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/sendReport.sh
# Purpose: /usr/local/MATLAB/R2018b/bin/matlab  -nodisplay -nosplash -nodesktop -r "run('/home/alberto/gate/SELADAS1M2/software/unpackingContinuous.m')".
# Owner: DATAFLOW_v3 contributors
# Sign-off: csoneira <csoneira@ucm.es>
# Last Updated: 2026-03-02
# Runtime: bash
# Usage: bash PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/sendReport.sh [options]
# Inputs: CLI args, config files, environment variables, and/or upstream files.
# Outputs: Files, logs, or process-level side effects.
# Notes: Keep behavior configuration-driven and reproducible.
# =============================================================================

#/usr/local/MATLAB/R2018b/bin/matlab  -nodisplay -nosplash -nodesktop -r "run('/home/alberto/gate/SELADAS1M2/software/unpackingContinuous.m')"
octave --no-gui /home/alberto/gate/SELADAS1M2/software/sendReport.m
