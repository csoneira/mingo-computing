% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/utils/IO/myLoad.m
% Purpose: MyLoad.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

myLoadStatus = 'good';
try
    load([path_ file_]);
catch exception
    %Damaged file or unable to load it because do not exist
    if(strfind(exception.message,'Unable to read file') | strfind(exception.message,'unable to determine file format') | strfind(exception.message,'unable to find file'))
        myLoadStatus = 'noGood';
    else
        myLoadStatus = 'notDefined';
    end
end