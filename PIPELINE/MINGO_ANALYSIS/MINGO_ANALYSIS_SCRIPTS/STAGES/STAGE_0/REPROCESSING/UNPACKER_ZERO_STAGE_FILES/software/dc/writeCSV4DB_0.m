% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/dc/writeCSV4DB_0.m
% Purpose: writeCSV4DB_0 function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function [outputVars] = writeCSV4DB_0(inputVars)

conf            =   inputVars{1};
file2Send       =   inputVars{2};
timeStamp       =   inputVars{3};
varName         =   inputVars{4};
variable        =   inputVars{5};


M = [datevec(timeStamp) variable];

%%%Build the script
fid = fopen(file2Send,'w');
if fid == (-1)
    error('rdf: Could not open file:');
end

count = fprintf(fid,['timestamps, ' varName '\n']);
for i= 1:size(M,1)
    count = fprintf(fid,['%04d-%02d-%02d %02d:%02d:%02d, %012.4f\n'],M(i,:));
    % formatei o print para passar
    % de:   2023 10 26 17 43 59
    % para: 2023-10-26 17:43:59
    % nota: e a mudanca da hora?
end

fclose(fid);

outputVars = 0;
return