% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/dc/hadesData2Regular.m
% Purpose: hadesData2Regular function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function  dateRegular = hadesData2Regular(fileName)

yyFromFile    = str2num(fileName(end-10:end-9));
ddFromFile    = str2num(fileName(end-8:end-6));
hourFromFile  = str2num(fileName(end-5:end-4));
mmFromFile    = str2num(fileName(end-3:end-2));
ssFromFile    = str2num(fileName(end-1:end));

[dayOfTheMonth,month] = HADESDate2Date(yyFromFile,ddFromFile);
dateRegular = datenum([str2num(['20' num2str(yyFromFile)]) month dayOfTheMonth  hourFromFile  mmFromFile ssFromFile]);    

end