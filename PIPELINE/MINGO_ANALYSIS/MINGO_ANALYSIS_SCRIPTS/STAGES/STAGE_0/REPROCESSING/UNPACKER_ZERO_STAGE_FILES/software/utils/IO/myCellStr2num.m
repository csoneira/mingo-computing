% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/utils/IO/myCellStr2num.m
% Purpose: myCellStr2num function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function N = myCellStr2num(cellStr)


N = zeros(length(cellStr),1);
for i=1:length(cellStr)
    if (isnumeric(cellStr{i}))
        N(i) =  cellStr{i};
    else
        N(i) =  str2num(cellStr{i});
    end
end



return