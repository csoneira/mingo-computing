% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/dc/readLookUpTable.m
% Purpose: readLookUpTable function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function lookUpTable=readLookUpTable(file2Read)


%Read the lookUpTable
%L = readcell(file2Read);
L = csv2Cell(file2Read,'%');

%Check the number of active columns and loop On It
indx = strfind([L{1,:}],'1');

%Export lookUpTable
lookUpTable = L(:,indx);


return
