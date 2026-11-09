% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/utils/IO/selectFilesByTime.m
% Purpose: selectFilesByTime function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function listedFiles = selectFilesByTime(listedFiles,time2Merge)

if time2Merge > 0
    timeFromNames = [];
    for i=1:length(listedFiles)
        timeFromNames(i) = datenum(listedFiles(i).name(1:10));
    end
    
    
    
    I = find(timeFromNames > time2Merge(1));
    
    listedFiles = listedFiles(I);
end
end

