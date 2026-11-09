% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/utils/IO/procLsOut.m
% Purpose: procLsOut function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function lsList = procLsOut(lsOutput)

%%% This function should be used with the output of something like 
%%% ls -1
%%% The output of the function give a cell with all file

%%% Check if there are no files
if(strfind(lsOutput,'ls: cannot access') == 1)
    lsList = [];
    return
end

index = find(isstrprop(lsOutput, 'wspace'));

lsList = cell(size(index,2),1);

index = [0, index];

for i=1:(length(index)-1)
    lsList{i} = lsOutput(index(i)+1:index(i+1)-1);
end

return