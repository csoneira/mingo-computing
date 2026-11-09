% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/daq/processException.m
% Purpose: processException function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function message2log = processException(exception)
                        

fullMessage = [];
fullMessage = [fullMessage exception.message];

for j = 1:length(exception.stack)
    message_ = ['Error in: ' exception.stack(j).file ' line ' num2str(exception.stack(j).line)];
    fullMessage = [fullMessage ' ' message_];
end

message2log = fullMessage;
 
return