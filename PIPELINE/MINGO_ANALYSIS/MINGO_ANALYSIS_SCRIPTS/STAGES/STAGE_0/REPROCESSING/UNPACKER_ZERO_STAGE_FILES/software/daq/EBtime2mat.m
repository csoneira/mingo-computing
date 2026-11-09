% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/daq/EBtime2mat.m
% Purpose: EBtime2mat function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function EBtime = EBtime2mat(eventDate,eventTime)
%Process Event Builder time and date extracted from hld file


DD = double(bitand(eventDate,uint32(hex2dec('000000ff'))));
MM = double(bitand(bitshift(eventDate,-8),uint32(hex2dec('000000ff')))) + 1;
YY = num2str(bitshift(eventDate,-16));YY = double(str2num([repmat('20',size(YY,1),1) YY(:,2:3)]));


ss = double(bitand(eventTime,uint32(hex2dec('000000ff'))));
mm = double(bitand(bitshift(eventTime,-8),uint32(hex2dec('000000ff'))));
hh = double(bitand(bitshift(eventTime,-16),uint32(hex2dec('000000ff'))));


EBtime = datenum(YY,MM,DD,hh,mm,ss);
return