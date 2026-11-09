% =============================================================================
% DATAFLOW_v3 Script Header v1
% Script: MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/daq/setSemaphore.m
% Purpose: setSemaphore function implementation.
% Owner: DATAFLOW_v3 contributors
% Sign-off: csoneira <csoneira@ucm.es>
% Last Updated: 2026-03-02
% Runtime: octave/matlab
% Usage: Run from MATLAB/Octave entrypoint with expected args/context.
% Inputs: Variables, config files, environment, and/or upstream files.
% Outputs: Variables, files, plots, or logs.
% Notes: Keep behavior configuration-driven and reproducible.
% =============================================================================

function [status, result] = setSemaphore(pathIn,logs,OS)
%
%
%Status = 1 means error 
%result is a coment about the problem



if(~exist([pathIn 'semaphore'],'dir'))%create the semaphore
    try
        [status, result] = system(['mkdir -p ' pathIn  'semaphore/']);
        if status == 1
            message2log = ['Error in the generation of the Semaphore skipping. '];
            disp(message2log);
            write2log(logs,message2log,'   ','syslog',OS);
        end
    catch
        message2log = ['Error in the generation of the Semaphore skipping. (Inside try)'];
        disp(message2log);
        write2log(logs,message2log,'   ','syslog',OS);
        status = 1;
        result = message2log;
    end
else
    message2log = ['Semaphore in place skipping.'];
    disp(message2log);
    write2log(logs,message2log,'   ','syslog',OS);
    status = 1;
    result = message2log;
end






return

