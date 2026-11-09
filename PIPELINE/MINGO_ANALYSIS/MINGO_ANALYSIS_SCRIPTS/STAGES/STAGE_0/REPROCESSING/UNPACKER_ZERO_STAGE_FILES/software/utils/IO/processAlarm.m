% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/utils/IO/processAlarm.m
% Purpose: processAlarm function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function processAlarm(systemName,device,alarmType,message2log,alarms)


for i=1:size(alarms,2)
    active      =    alarms(i).active;
    type        =    alarms(i).type;
    TO          =    alarms(i).TO;
    
    if active & strcmp(type,alarmType)
            [status, result] = sendbashEmail([systemName '   : ' device ],TO,message2log,'');
    end
end