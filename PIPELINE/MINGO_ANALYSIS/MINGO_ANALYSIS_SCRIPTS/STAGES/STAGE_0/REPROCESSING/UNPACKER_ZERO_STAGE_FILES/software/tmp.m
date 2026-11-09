% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/tmp.m
% Purpose: Tmp.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

for i=1:32
    
   evt = 1:100;ch=1+i;full([(evt)' leadingEpochCounter(evt,ch) leadingCoarseTime(evt,ch)  trailingCoarseTime(evt,ch) (trailingCoarseTime(evt,ch)-leadingCoarseTime(evt,ch))*5])
    i  
    pause
end