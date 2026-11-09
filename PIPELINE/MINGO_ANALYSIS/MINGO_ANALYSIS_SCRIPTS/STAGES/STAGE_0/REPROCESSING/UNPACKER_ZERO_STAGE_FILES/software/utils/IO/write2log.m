% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/utils/IO/write2log.m
% Purpose: write2log function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function write2log(logs,message2log,issue,logType,OS)

for i=1:size(logs,2)
    active    = logs(i).active;
    type      = logs(i).type;
    logPath   = logs(i).localPath;
    if(active && strcmp(logType,type))
        write2LogFile(message2log,issue,logPath);
    end
end
return