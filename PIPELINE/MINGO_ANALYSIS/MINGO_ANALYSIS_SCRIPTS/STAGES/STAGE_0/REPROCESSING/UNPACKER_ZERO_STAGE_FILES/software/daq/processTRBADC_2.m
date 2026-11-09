% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/daq/processTRBADC_2.m
% Purpose: processTRBADC_2 function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function Q = processTRBADC_2(fileName,inputPath)



load([inputPath fileName]);
eventsFromTime = size(data,3);
disp(['Loading ' fileName ' with ' num2str(eventsFromTime) ' events.']);


%downSampling  blockSize    Xincr    polarity                      samples4BaseLine  samples4Maximum
%infoADC = {         10,        8,   25e-9,   [ones(48,1)],                 1:3,              7:10};
% infoADC = {         10,        8,   25e-9,   [ones(1,48)],            1:(floor(size(data,1)*(1/3))+1), size(data,1)-(floor(size(data,1)*(1/3))+1):size(data,1)}; plotIt = 0;
%     
%          [Baseline, Q, Qlast, TQ, Pileup1] ...
%              = MM(data,infoADC,plotIt);
Q = data;
return