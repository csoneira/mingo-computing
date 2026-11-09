% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/daq/processTRBHEAD.m
% Purpose: processTRBHEAD function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function [triggerType, filePosition,fileNames,EBtime] = processTRBHEAD(fileName,inputPath)

load([inputPath fileName]);
eventsFromTime = size(eventTime,1);
disp(['Loading ' fileName ' with ' num2str(eventsFromTime) ' events.']);

filePosition = (1:eventsFromTime)';
fileNames = repmat(fileName,eventsFromTime,1);
EBtime = EBtime2mat(eventDate,eventTime);

if(~exist('triggerType','var'))%In case triggerType does not exist create a dummy
    triggerType = eventTime*0;
end

return